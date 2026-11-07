#include "mir.h"
#include "mir-gen.h"

#include <math.h>
#include <stdint.h>
#include <sys/resource.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define MAX_INPUT (16u * 1024u * 1024u)
#define MAX_FUNCTIONS 128u
#define MAX_ARGS 6u
#define MAX_LOCALS 512u
#define MAX_STATEMENTS 8192u
#define MAX_EXPR_DEPTH 256u

enum {
  EX_CONST = 1, EX_LOCAL = 2, EX_RESULT = 3, EX_ADD = 4, EX_SUB = 5,
  EX_MUL = 6, EX_DIV = 7, EX_NEG = 8, EX_CALL = 9
};

typedef struct Expr Expr;
struct Expr {
  uint8_t kind;
  double value;
  uint32_t slot;
  uint32_t callee;
  uint32_t nargs;
  Expr **args;
  Expr *left;
  Expr *right;
};

typedef struct {
  uint8_t target_kind;
  uint32_t slot;
  Expr *value;
} Statement;

typedef struct {
  uint32_t nargs;
  uint32_t nlocals;
  uint32_t nstatements;
  Statement *statements;
} Function;

typedef struct {
  const uint8_t *data;
  size_t length;
  size_t offset;
  const char *error;
} Reader;

static void free_expr(Expr *expr) {
  if (expr == NULL) return;
  free_expr(expr->left);
  free_expr(expr->right);
  for (uint32_t i = 0; i < expr->nargs; i++) free_expr(expr->args[i]);
  free(expr->args);
  free(expr);
}

static void free_functions(Function *functions, uint32_t nfunctions) {
  if (functions == NULL) return;
  for (uint32_t i = 0; i < nfunctions; i++) {
    for (uint32_t j = 0; j < functions[i].nstatements; j++)
      free_expr(functions[i].statements[j].value);
    free(functions[i].statements);
  }
  free(functions);
}

static int read_bytes(Reader *reader, void *out, size_t size) {
  if (size > reader->length - reader->offset) {
    reader->error = "truncated binary projection";
    return 0;
  }
  memcpy(out, reader->data + reader->offset, size);
  reader->offset += size;
  return 1;
}

static int read_u8(Reader *reader, uint8_t *out) { return read_bytes(reader, out, sizeof(*out)); }

static int read_u32(Reader *reader, uint32_t *out) {
  uint8_t b[4];
  if (!read_bytes(reader, b, sizeof(b))) return 0;
  *out = (uint32_t)b[0] | ((uint32_t)b[1] << 8) | ((uint32_t)b[2] << 16) | ((uint32_t)b[3] << 24);
  return 1;
}

static int read_double(Reader *reader, double *out) {
  uint8_t b[8];
  uint64_t bits = 0;
  if (!read_bytes(reader, b, sizeof(b))) return 0;
  for (unsigned i = 0; i < 8; i++) bits |= (uint64_t)b[i] << (i * 8);
  memcpy(out, &bits, sizeof(bits));
  return 1;
}

static Expr *read_expr(Reader *reader, uint32_t depth) {
  if (depth > MAX_EXPR_DEPTH) {
    reader->error = "expression nesting limit exceeded";
    return NULL;
  }
  Expr *expr = calloc(1, sizeof(*expr));
  if (expr == NULL) {
    reader->error = "out of memory reading expression";
    return NULL;
  }
  if (!read_u8(reader, &expr->kind)) goto fail;
  switch (expr->kind) {
  case EX_CONST:
    if (!read_double(reader, &expr->value)) goto fail;
    break;
  case EX_LOCAL:
    if (!read_u32(reader, &expr->slot)) goto fail;
    break;
  case EX_RESULT:
    break;
  case EX_NEG:
    expr->left = read_expr(reader, depth + 1);
    if (expr->left == NULL) goto fail;
    break;
  case EX_ADD: case EX_SUB: case EX_MUL: case EX_DIV:
    expr->left = read_expr(reader, depth + 1);
    expr->right = read_expr(reader, depth + 1);
    if (expr->left == NULL || expr->right == NULL) goto fail;
    break;
  case EX_CALL:
    if (!read_u32(reader, &expr->callee) || !read_u32(reader, &expr->nargs)) goto fail;
    if (expr->nargs > MAX_ARGS) {
      reader->error = "function call exceeds supported argument limit";
      goto fail;
    }
    expr->args = calloc(expr->nargs == 0 ? 1 : expr->nargs, sizeof(*expr->args));
    if (expr->args == NULL) {
      reader->error = "out of memory reading function call";
      goto fail;
    }
    for (uint32_t i = 0; i < expr->nargs; i++) {
      expr->args[i] = read_expr(reader, depth + 1);
      if (expr->args[i] == NULL) goto fail;
    }
    break;
  default:
    reader->error = "unknown expression opcode";
    goto fail;
  }
  return expr;
fail:
  free_expr(expr);
  return NULL;
}

static Function *read_projection(const uint8_t *data, size_t length,
                                 uint32_t *engine, uint32_t *target,
                                 uint32_t *nfunctions, uint32_t *call_argc,
                                 double call_args[MAX_ARGS], const char **error) {
  Reader reader = {data, length, 0, NULL};
  uint8_t magic[4];
  uint32_t version;
  if (!read_bytes(&reader, magic, sizeof(magic)) || memcmp(magic, "BWM1", 4) != 0 ||
      !read_u32(&reader, &version) || !read_u32(&reader, engine) ||
      !read_u32(&reader, target) || !read_u32(&reader, nfunctions)) {
    *error = reader.error != NULL ? reader.error : "invalid binary projection header";
    return NULL;
  }
  if (version != 1 || *engine > 1 || *nfunctions == 0 || *nfunctions > MAX_FUNCTIONS ||
      *target >= *nfunctions) {
    *error = "unsupported binary projection header values";
    return NULL;
  }
  Function *functions = calloc(*nfunctions, sizeof(*functions));
  if (functions == NULL) {
    *error = "out of memory reading functions";
    return NULL;
  }
  for (uint32_t i = 0; i < *nfunctions; i++) {
    Function *function = &functions[i];
    if (!read_u32(&reader, &function->nargs) || !read_u32(&reader, &function->nlocals) ||
        !read_u32(&reader, &function->nstatements)) goto fail;
    if (function->nargs > MAX_ARGS || function->nlocals > MAX_LOCALS ||
        function->nstatements > MAX_STATEMENTS) {
      reader.error = "function exceeds supported MIR worker limits";
      goto fail;
    }
    function->statements = calloc(function->nstatements == 0 ? 1 : function->nstatements,
                                  sizeof(*function->statements));
    if (function->statements == NULL) {
      reader.error = "out of memory reading statements";
      goto fail;
    }
    for (uint32_t j = 0; j < function->nstatements; j++) {
      Statement *statement = &function->statements[j];
      if (!read_u8(&reader, &statement->target_kind)) goto fail;
      reader.offset += 3; /* reserved bytes */
      if (reader.offset > reader.length || !read_u32(&reader, &statement->slot)) goto fail;
      if (statement->target_kind > 1 ||
          (statement->target_kind == 0 && statement->slot >= function->nargs + function->nlocals)) {
        reader.error = "invalid assignment target slot";
        goto fail;
      }
      statement->value = read_expr(&reader, 0);
      if (statement->value == NULL) goto fail;
    }
  }
  uint32_t payload_target;
  if (!read_u32(&reader, &payload_target) || !read_u32(&reader, call_argc)) goto fail;
  if (payload_target != *target || *call_argc != functions[*target].nargs || *call_argc > MAX_ARGS) {
    reader.error = "call target or argument count does not match compiled function";
    goto fail;
  }
  for (uint32_t i = 0; i < *call_argc; i++)
    if (!read_double(&reader, &call_args[i])) goto fail;
  if (reader.offset != reader.length) {
    reader.error = "trailing bytes in binary projection";
    goto fail;
  }
  return functions;
fail:
  *error = reader.error != NULL ? reader.error : "truncated binary projection";
  free_functions(functions, *nfunctions);
  return NULL;
}

static MIR_reg_t new_temp(MIR_context_t ctx, MIR_func_t function, uint32_t *counter) {
  char name[40];
  snprintf(name, sizeof(name), "tmp_%u", (*counter)++);
  return MIR_new_func_reg(ctx, function, MIR_T_D, name);
}

static void emit_double_move(MIR_context_t ctx, MIR_item_t item, MIR_reg_t dst, MIR_op_t src) {
  MIR_append_insn(ctx, item, MIR_new_insn(ctx, MIR_DMOV, MIR_new_reg_op(ctx, dst), src));
}

static MIR_reg_t lower_expr(MIR_context_t ctx, MIR_item_t item, MIR_reg_t *slots,
                            MIR_reg_t result_reg, MIR_item_t *protos,
                            MIR_item_t *forwards, uint32_t slot_count, const Expr *expr,
                            uint32_t *temp_counter) {
  MIR_func_t function = item->u.func;
  MIR_reg_t dst;
  switch (expr->kind) {
  case EX_CONST:
    dst = new_temp(ctx, function, temp_counter);
    emit_double_move(ctx, item, dst, MIR_new_double_op(ctx, expr->value));
    return dst;
  case EX_LOCAL:
    if (expr->slot >= slot_count) return 0;
    return slots[expr->slot];
  case EX_RESULT:
    return result_reg;
  case EX_NEG: {
    MIR_reg_t operand = lower_expr(ctx, item, slots, result_reg, protos, forwards,
                                   slot_count, expr->left, temp_counter);
    dst = new_temp(ctx, function, temp_counter);
    MIR_append_insn(ctx, item, MIR_new_insn(ctx, MIR_DNEG, MIR_new_reg_op(ctx, dst),
                                            MIR_new_reg_op(ctx, operand)));
    return dst;
  }
  case EX_ADD: case EX_SUB: case EX_MUL: case EX_DIV: {
    MIR_reg_t left = lower_expr(ctx, item, slots, result_reg, protos, forwards,
                                slot_count, expr->left, temp_counter);
    MIR_reg_t right = lower_expr(ctx, item, slots, result_reg, protos, forwards,
                                 slot_count, expr->right, temp_counter);
    MIR_insn_code_t code = expr->kind == EX_ADD ? MIR_DADD : expr->kind == EX_SUB ? MIR_DSUB :
                           expr->kind == EX_MUL ? MIR_DMUL : MIR_DDIV;
    dst = new_temp(ctx, function, temp_counter);
    MIR_append_insn(ctx, item, MIR_new_insn(ctx, code, MIR_new_reg_op(ctx, dst),
                                            MIR_new_reg_op(ctx, left), MIR_new_reg_op(ctx, right)));
    return dst;
  }
  case EX_CALL: {
    MIR_op_t call_ops[3 + MAX_ARGS];
    if (expr->callee >= MAX_FUNCTIONS || expr->nargs > MAX_ARGS) return 0;
    dst = new_temp(ctx, function, temp_counter);
    call_ops[0] = MIR_new_ref_op(ctx, protos[expr->callee]);
    call_ops[1] = MIR_new_ref_op(ctx, forwards[expr->callee]);
    call_ops[2] = MIR_new_reg_op(ctx, dst);
    for (uint32_t i = 0; i < expr->nargs; i++) {
      MIR_reg_t arg = lower_expr(ctx, item, slots, result_reg, protos, forwards,
                                 slot_count, expr->args[i], temp_counter);
      call_ops[3 + i] = MIR_new_reg_op(ctx, arg);
    }
    MIR_append_insn(ctx, item, MIR_new_insn_arr(ctx, MIR_CALL, 3 + expr->nargs, call_ops));
    return dst;
  }
  default:
    return 0;
  }
}

static double call_native(void *address, uint32_t argc, const double *a) {
  switch (argc) {
  case 0: return ((double (*)(void))address)();
  case 1: return ((double (*)(double))address)(a[0]);
  case 2: return ((double (*)(double, double))address)(a[0], a[1]);
  case 3: return ((double (*)(double, double, double))address)(a[0], a[1], a[2]);
  case 4: return ((double (*)(double, double, double, double))address)(a[0], a[1], a[2], a[3]);
  case 5: return ((double (*)(double, double, double, double, double))address)(a[0], a[1], a[2], a[3], a[4]);
  case 6: return ((double (*)(double, double, double, double, double, double))address)(a[0], a[1], a[2], a[3], a[4], a[5]);
  default: return NAN;
  }
}

static void report_error(const char *code, const char *message) {
  printf("{\"ok\":false,\"code\":\"%s\",\"message\":\"%s\"}\n", code, message);
}

static double monotonic_ms(void) {
  struct timespec ts;
  if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0) return 0.0;
  return (double)ts.tv_sec * 1000.0 + (double)ts.tv_nsec / 1000000.0;
}

static uint8_t *read_stdin(size_t *size) {
  size_t capacity = 4096;
  uint8_t *data = malloc(capacity);
  if (data == NULL) return NULL;
  *size = 0;
  for (;;) {
    if (*size == capacity) {
      if (capacity >= MAX_INPUT) { free(data); return NULL; }
      size_t next = capacity * 2;
      if (next > MAX_INPUT) next = MAX_INPUT;
      uint8_t *grown = realloc(data, next);
      if (grown == NULL) { free(data); return NULL; }
      data = grown;
      capacity = next;
    }
    size_t n = fread(data + *size, 1, capacity - *size, stdin);
    *size += n;
    if (n == 0) {
      if (ferror(stdin)) { free(data); return NULL; }
      break;
    }
  }
  return data;
}

int main(void) {
  size_t input_size = 0;
  uint8_t *input = read_stdin(&input_size);
  if (input == NULL) {
    report_error("INVALID_PROJECTION", "could not read projection or input exceeded worker limit");
    return 0;
  }
  uint32_t engine = 0, target = 0, nfunctions = 0, argc = 0;
  double args[MAX_ARGS] = {0};
  const char *parse_error = NULL;
  Function *functions = read_projection(input, input_size, &engine, &target,
                                        &nfunctions, &argc, args, &parse_error);
  free(input);
  if (functions == NULL) {
    report_error("INVALID_PROJECTION", parse_error != NULL ? parse_error : "invalid projection");
    return 0;
  }

  double build_started = monotonic_ms();
  double build_ms = 0.0, link_ms = 0.0, jit_compile_ms = 0.0, invoke_ms = 0.0;
  MIR_context_t ctx = MIR_init();
  if (ctx == NULL) {
    free_functions(functions, nfunctions);
    report_error("MIR_INIT_FAILED", "MIR_init returned NULL");
    return 0;
  }
  MIR_module_t module = MIR_new_module(ctx, "basic_workspace_projection");
  MIR_item_t *protos = calloc(nfunctions, sizeof(*protos));
  MIR_item_t *forwards = calloc(nfunctions, sizeof(*forwards));
  MIR_item_t *items = calloc(nfunctions, sizeof(*items));
  MIR_var_t *vars = calloc((size_t)nfunctions * MAX_ARGS, sizeof(*vars));
  char (*names)[MAX_ARGS][32] = calloc(nfunctions, sizeof(*names));
  MIR_type_t *result_types = calloc(nfunctions, sizeof(*result_types));
  int failed = module == NULL || protos == NULL || forwards == NULL || items == NULL ||
               vars == NULL || names == NULL || result_types == NULL;
  if (failed) {
    report_error("MIR_BUILD_FAILED", "out of memory preparing MIR functions");
    goto cleanup;
  }

  for (uint32_t i = 0; i < nfunctions; i++) {
    char function_name[48], proto_name[52];
    snprintf(function_name, sizeof(function_name), "bw_func_%u", i);
    snprintf(proto_name, sizeof(proto_name), "bw_func_%u_p", i);
    result_types[i] = MIR_T_D;
    MIR_var_t *function_vars = vars + (size_t)i * MAX_ARGS;
    for (uint32_t j = 0; j < functions[i].nargs; j++) {
      snprintf(names[i][j], sizeof(names[i][j]), "arg_%u_%u", i, j);
      function_vars[j].type = MIR_T_D;
      function_vars[j].name = names[i][j];
      function_vars[j].size = 0;
    }
    protos[i] = MIR_new_proto_arr(ctx, proto_name, 1, &result_types[i],
                                  functions[i].nargs, function_vars);
    forwards[i] = MIR_new_forward(ctx, function_name);
    if (protos[i] == NULL || forwards[i] == NULL) { failed = 1; break; }
  }

  for (uint32_t i = 0; !failed && i < nfunctions; i++) {
    char function_name[48];
    snprintf(function_name, sizeof(function_name), "bw_func_%u", i);
    MIR_var_t *function_vars = vars + (size_t)i * MAX_ARGS;
    items[i] = MIR_new_func_arr(ctx, function_name, 1, &result_types[i],
                                functions[i].nargs, function_vars);
    if (items[i] == NULL) { failed = 1; break; }
    MIR_func_t mir_func = items[i]->u.func;
    uint32_t slot_count = functions[i].nargs + functions[i].nlocals;
    MIR_reg_t *slots = calloc(slot_count == 0 ? 1 : slot_count, sizeof(*slots));
    if (slots == NULL) { failed = 1; break; }
    for (uint32_t j = 0; j < functions[i].nargs; j++)
      slots[j] = MIR_reg(ctx, names[i][j], mir_func);
    uint32_t temp_counter = 0;
    for (uint32_t j = 0; j < functions[i].nlocals; j++) {
      char local_name[48];
      snprintf(local_name, sizeof(local_name), "local_%u", j);
      slots[functions[i].nargs + j] = MIR_new_func_reg(ctx, mir_func, MIR_T_D, local_name);
      emit_double_move(ctx, items[i], slots[functions[i].nargs + j], MIR_new_double_op(ctx, 0.0));
    }
    MIR_reg_t return_reg = MIR_new_func_reg(ctx, mir_func, MIR_T_D, "basic_result");
    emit_double_move(ctx, items[i], return_reg, MIR_new_double_op(ctx, 0.0));
    for (uint32_t j = 0; j < functions[i].nstatements; j++) {
      Statement *statement = &functions[i].statements[j];
      MIR_reg_t value = lower_expr(ctx, items[i], slots, return_reg, protos, forwards,
                                   slot_count, statement->value, &temp_counter);
      MIR_reg_t destination = statement->target_kind == 1 ? return_reg : slots[statement->slot];
      if (value == 0 || destination == 0) { failed = 1; break; }
      MIR_append_insn(ctx, items[i], MIR_new_insn(ctx, MIR_DMOV, MIR_new_reg_op(ctx, destination),
                                                  MIR_new_reg_op(ctx, value)));
    }
    if (!failed) {
      MIR_append_insn(ctx, items[i], MIR_new_ret_insn(ctx, 1, MIR_new_reg_op(ctx, return_reg)));
      MIR_finish_func(ctx);
    }
    free(slots);
  }

  if (failed) {
    report_error("MIR_BUILD_FAILED", "MIR API rejected the structured function projection");
    goto cleanup;
  }
  MIR_finish_module(ctx);
  MIR_load_module(ctx, module);
  build_ms = monotonic_ms() - build_started;
  if (getenv("BASIC_WORKSPACE_MIR_DUMP") != NULL) MIR_output(ctx, stderr);
  double result = 0.0;
  double link_started = monotonic_ms();
  if (engine == 0) {
    MIR_link(ctx, MIR_set_interp_interface, NULL);
    link_ms = monotonic_ms() - link_started;
    MIR_val_t values[MAX_ARGS], results[1];
    for (uint32_t i = 0; i < argc; i++) values[i].d = args[i];
    double invoke_started = monotonic_ms();
    MIR_interp_arr(ctx, items[target], results, argc, values);
    invoke_ms = monotonic_ms() - invoke_started;
    result = results[0].d;
  } else {
    MIR_gen_init(ctx);
    MIR_link(ctx, MIR_set_gen_interface, NULL);
    link_ms = monotonic_ms() - link_started;
    double jit_started = monotonic_ms();
    void *address = MIR_gen(ctx, items[target]);
    jit_compile_ms = monotonic_ms() - jit_started;
    if (address == NULL) {
      MIR_gen_finish(ctx);
      report_error("MIR_JIT_FAILED", "MIR_gen returned NULL");
      goto cleanup;
    }
    double invoke_started = monotonic_ms();
    result = call_native(address, argc, args);
    invoke_ms = monotonic_ms() - invoke_started;
    MIR_gen_finish(ctx);
  }
  if (!isfinite(result)) {
    report_error("NON_FINITE_RESULT", "execution produced a non-finite double result");
  } else {
    struct rusage usage;
    long maxrss_kib = getrusage(RUSAGE_SELF, &usage) == 0 ? usage.ru_maxrss : -1;
    printf("{\"ok\":true,\"result_hex\":\"%a\",\"timings_ms\":{\"mir_build\":%.6f,\"link\":%.6f,\"jit_compile\":%.6f,\"invoke\":%.6f},\"maxrss_kib\":%ld}\n",
           result, build_ms, link_ms, jit_compile_ms, invoke_ms, maxrss_kib);
  }

cleanup:
  free_functions(functions, nfunctions);
  free(protos);
  free(forwards);
  free(items);
  free(vars);
  free(names);
  free(result_types);
  MIR_finish(ctx);
  return 0;
}
