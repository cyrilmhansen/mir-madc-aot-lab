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
#define MAX_ARRAYS 32u
#define MAX_ARRAY_ELEMENTS 256u
#define MAX_TOTAL_ARRAY_ELEMENTS 4096u
#define MAX_STATEMENTS 8192u
#define MAX_EXPR_DEPTH 256u
#define MAX_CONTROL_DEPTH 16u
#define MAX_LOOP_ITERATIONS 10000u
#define MAX_STRING_BYTES 4096u
#define MAX_TOTAL_STRING_BYTES (256u * 1024u)

enum {
  EX_CONST = 1, EX_LOCAL = 2, EX_RESULT = 3, EX_ADD = 4, EX_SUB = 5,
  EX_MUL = 6, EX_DIV = 7, EX_NEG = 8, EX_CALL = 9, EX_ARRAY = 10,
  EX_EQ = 11, EX_NE = 12, EX_LT = 13, EX_LE = 14, EX_GT = 15, EX_GE = 16,
  EX_STRING = 17
};

enum { ST_ASSIGN = 0, ST_IF = 1, ST_FOR = 2 };

typedef struct Expr Expr;
struct Expr {
  uint8_t kind;
  double value;
  uint32_t slot;
  uint32_t callee;
  uint32_t nargs;
  Expr **args;
  uint32_t array;
  char *string;
  uint32_t string_length;
  Expr *left;
  Expr *right;
};

typedef struct Statement Statement;
struct Statement {
  uint8_t kind;
  uint8_t target_kind;
  uint32_t slot;
  Expr *index;
  Expr *value;
  Expr *condition;
  Expr *start;
  Expr *end;
  Expr *step;
  uint32_t iteration_limit;
  uint32_t nthen;
  uint32_t nelse;
  uint32_t nbody;
  Statement *then_body;
  Statement *else_body;
  Statement *body;
};

typedef struct {
  uint32_t lower;
  uint32_t upper;
  uint8_t is_string;
  MIR_reg_t *elements;
  MIR_reg_t base;
  int memory_backed;
  int shared;
  uint32_t shared_slot;
  MIR_item_t shared_item;
} Array;

static int use_memory_arrays;
static struct Function *active_function;
static size_t total_string_bytes;

typedef struct Function {
  uint32_t nargs;
  uint32_t nlocals;
  uint32_t narrays;
  uint32_t nstatements;
  uint8_t return_string;
  uint8_t *slot_types;
  Array *arrays;
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
  free(expr->string);
  free(expr);
}

static void free_statements(Statement *statements, uint32_t count) {
  if (statements == NULL) return;
  for (uint32_t i = 0; i < count; i++) {
    Statement *statement = &statements[i];
    free_expr(statement->index); free_expr(statement->value);
    free_expr(statement->condition); free_expr(statement->start);
    free_expr(statement->end); free_expr(statement->step);
    free_statements(statement->then_body, statement->nthen);
    free_statements(statement->else_body, statement->nelse);
    free_statements(statement->body, statement->nbody);
  }
  free(statements);
}

static void free_functions(Function *functions, uint32_t nfunctions) {
  if (functions == NULL) return;
  for (uint32_t i = 0; i < nfunctions; i++) {
    if (functions[i].arrays != NULL) {
      for (uint32_t j = 0; j < functions[i].narrays; j++)
        free(functions[i].arrays[j].elements);
      free(functions[i].arrays);
    }
    free(functions[i].slot_types);
    free_statements(functions[i].statements, functions[i].nstatements);
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

static int valid_utf8(const unsigned char *s, size_t n) {
  size_t i = 0;
  while (i < n) {
    unsigned char c = s[i++];
    if (c < 0x80) continue;
    unsigned need = c >= 0xC2 && c <= 0xDF ? 1 : c >= 0xE0 && c <= 0xEF ? 2 : c >= 0xF0 && c <= 0xF4 ? 3 : 99;
    if (need == 99 || i + need > n) return 0;
    unsigned char a = s[i];
    if ((c == 0xE0 && a < 0xA0) || (c == 0xED && a >= 0xA0) ||
        (c == 0xF0 && a < 0x90) || (c == 0xF4 && a >= 0x90)) return 0;
    for (unsigned j = 0; j < need; j++) if ((s[i++] & 0xC0) != 0x80) return 0;
  }
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

static Expr *read_expr(Reader *reader, uint32_t depth, uint32_t narrays) {
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
  case EX_STRING: {
    if (!read_u32(reader, &expr->string_length) || expr->string_length > MAX_STRING_BYTES ||
        expr->string_length > reader->length - reader->offset) {
      reader->error = "invalid string literal length"; goto fail;
    }
    expr->string = malloc((size_t)expr->string_length + 1);
    if (expr->string == NULL) { reader->error = "out of memory reading string"; goto fail; }
    if (!read_bytes(reader, expr->string, expr->string_length)) goto fail;
    if (memchr(expr->string, 0, expr->string_length) != NULL || !valid_utf8((unsigned char *)expr->string, expr->string_length)) {
      reader->error = "string literal is not valid NUL-free UTF-8"; goto fail;
    }
    if (total_string_bytes > MAX_TOTAL_STRING_BYTES - expr->string_length - 1) {
      reader->error = "aggregate string storage exceeds worker limit"; goto fail;
    }
    total_string_bytes += expr->string_length + 1;
    expr->string[expr->string_length] = 0;
    break;
  }
  case EX_CONST:
    if (!read_double(reader, &expr->value)) goto fail;
    if (!isfinite(expr->value)) {
      reader->error = "non-finite numeric constant";
      goto fail;
    }
    break;
  case EX_LOCAL:
    if (!read_u32(reader, &expr->slot)) goto fail;
    break;
  case EX_RESULT:
    break;
  case EX_NEG:
    expr->left = read_expr(reader, depth + 1, narrays);
    if (expr->left == NULL) goto fail;
    break;
  case EX_ADD: case EX_SUB: case EX_MUL: case EX_DIV:
  case EX_EQ: case EX_NE: case EX_LT: case EX_LE: case EX_GT: case EX_GE:
    expr->left = read_expr(reader, depth + 1, narrays);
    expr->right = read_expr(reader, depth + 1, narrays);
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
      expr->args[i] = read_expr(reader, depth + 1, narrays);
      if (expr->args[i] == NULL) goto fail;
    }
    break;
  case EX_ARRAY:
    if (!read_u32(reader, &expr->array) || expr->array >= narrays) {
      reader->error = "invalid array expression reference";
      goto fail;
    }
    expr->left = read_expr(reader, depth + 1, narrays);
    if (expr->left == NULL) goto fail;
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

/* Validate cross-function and slot references only after all function
   signatures have been read. A malformed worker payload must never turn an
   unchecked function index into an out-of-bounds read during MIR lowering. */
static int validate_expr(const Expr *expr, const Function *functions,
                         uint32_t nfunctions, uint32_t current_slots) {
  if (expr == NULL) return 0;
  switch (expr->kind) {
  case EX_CONST: case EX_RESULT: case EX_STRING:
    return 1;
  case EX_LOCAL:
    return expr->slot < current_slots;
  case EX_NEG:
    return validate_expr(expr->left, functions, nfunctions, current_slots);
  case EX_ADD: case EX_SUB: case EX_MUL: case EX_DIV:
  case EX_EQ: case EX_NE: case EX_LT: case EX_LE: case EX_GT: case EX_GE:
    return validate_expr(expr->left, functions, nfunctions, current_slots) &&
           validate_expr(expr->right, functions, nfunctions, current_slots);
  case EX_CALL:
    if (expr->callee >= nfunctions ||
        expr->nargs != functions[expr->callee].nargs) return 0;
    for (uint32_t i = 0; i < expr->nargs; i++)
      if (!validate_expr(expr->args[i], functions, nfunctions, current_slots)) return 0;
    return 1;
  case EX_ARRAY:
    return expr->array < 32 &&
           validate_expr(expr->left, functions, nfunctions, current_slots);
  default:
    return 0;
  }
}

static int read_statement(Reader *reader, Statement *statement, uint32_t narrays,
                         uint32_t depth, uint32_t *statement_total) {
  if (depth > MAX_CONTROL_DEPTH || ++*statement_total > MAX_STATEMENTS) {
    reader->error = "control-flow nesting or statement limit exceeded";
    return 0;
  }
  uint8_t reserved[2];
  if (!read_u8(reader, &statement->kind) || !read_u8(reader, &statement->target_kind) ||
      !read_bytes(reader, reserved, sizeof(reserved)) || !read_u32(reader, &statement->slot))
    return 0;
  if (statement->kind == ST_ASSIGN) {
    if (statement->target_kind > 2 ||
        (statement->target_kind == 1 && statement->slot != 0)) {
      reader->error = "invalid assignment target kind";
      return 0;
    }
    if (statement->target_kind == 2) {
      statement->index = read_expr(reader, 0, narrays);
      if (statement->index == NULL) return 0;
    }
    statement->value = read_expr(reader, 0, narrays);
    return statement->value != NULL;
  }
  if (statement->kind == ST_IF) {
    if (statement->target_kind != 0 || statement->slot != 0) {
      reader->error = "invalid IF statement header";
      return 0;
    }
    statement->condition = read_expr(reader, 0, narrays);
    if (statement->condition == NULL || !read_u32(reader, &statement->nthen) ||
        statement->nthen > MAX_STATEMENTS) return 0;
    statement->then_body = calloc(statement->nthen == 0 ? 1 : statement->nthen,
                                  sizeof(*statement->then_body));
    if (statement->then_body == NULL) { reader->error = "out of memory reading IF block"; return 0; }
    for (uint32_t i = 0; i < statement->nthen; i++)
      if (!read_statement(reader, &statement->then_body[i], narrays, depth + 1, statement_total)) return 0;
    if (!read_u32(reader, &statement->nelse) || statement->nelse > MAX_STATEMENTS) return 0;
    statement->else_body = calloc(statement->nelse == 0 ? 1 : statement->nelse,
                                  sizeof(*statement->else_body));
    if (statement->else_body == NULL) { reader->error = "out of memory reading ELSE block"; return 0; }
    for (uint32_t i = 0; i < statement->nelse; i++)
      if (!read_statement(reader, &statement->else_body[i], narrays, depth + 1, statement_total)) return 0;
    return 1;
  }
  if (statement->kind == ST_FOR) {
    if (statement->target_kind != 0) {
      reader->error = "invalid bounded FOR record";
      return 0;
    }
    statement->start = read_expr(reader, 0, narrays);
    statement->end = read_expr(reader, 0, narrays);
    statement->step = read_expr(reader, 0, narrays);
    if (statement->start == NULL || statement->end == NULL || statement->step == NULL ||
        statement->start->kind != EX_CONST || statement->end->kind != EX_CONST ||
        statement->step->kind != EX_CONST || !isfinite(statement->start->value) ||
        !isfinite(statement->end->value) || !isfinite(statement->step->value) ||
        statement->step->value == 0.0 || !read_u32(reader, &statement->iteration_limit) ||
        statement->iteration_limit == 0 || statement->iteration_limit > MAX_LOOP_ITERATIONS ||
        !read_u32(reader, &statement->nbody) ||
        statement->nbody > MAX_STATEMENTS) {
      reader->error = "invalid static FOR bounds or body";
      return 0;
    }
    if (statement->slot >= MAX_LOCALS + MAX_ARGS) {
      reader->error = "invalid FOR variable slot";
      return 0;
    }
    statement->body = calloc(statement->nbody == 0 ? 1 : statement->nbody,
                             sizeof(*statement->body));
    if (statement->body == NULL) { reader->error = "out of memory reading FOR body"; return 0; }
    for (uint32_t i = 0; i < statement->nbody; i++)
      if (!read_statement(reader, &statement->body[i], narrays, depth + 1, statement_total)) return 0;
    return 1;
  }
  reader->error = "unknown structured statement opcode";
  return 0;
}

static int validate_statement(const Statement *statement, const Function *functions,
                              uint32_t nfunctions, uint32_t nargs, uint32_t nslots, uint32_t narrays,
                              uint32_t depth) {
  if (depth > MAX_CONTROL_DEPTH) return 0;
  if (statement->kind == ST_ASSIGN) {
    if ((statement->target_kind == 0 && statement->slot >= nslots) ||
        (statement->target_kind == 2 && (statement->slot >= narrays || statement->index == NULL)) ||
        (statement->index != NULL && !validate_expr(statement->index, functions, nfunctions, nslots)) ||
        !validate_expr(statement->value, functions, nfunctions, nslots)) return 0;
    return 1;
  }
  if (statement->kind == ST_IF) {
    if (!validate_expr(statement->condition, functions, nfunctions, nslots)) return 0;
    for (uint32_t i = 0; i < statement->nthen; i++)
      if (!validate_statement(&statement->then_body[i], functions, nfunctions, nargs, nslots, narrays, depth + 1)) return 0;
    for (uint32_t i = 0; i < statement->nelse; i++)
      if (!validate_statement(&statement->else_body[i], functions, nfunctions, nargs, nslots, narrays, depth + 1)) return 0;
    return 1;
  }
  if (statement->kind == ST_FOR) {
    if (statement->slot < nargs || statement->slot >= nslots || !isfinite(statement->start->value) ||
        !isfinite(statement->end->value) || !isfinite(statement->step->value) ||
        statement->step->value == 0.0) return 0;
    for (uint32_t i = 0; i < statement->nbody; i++)
      if (!validate_statement(&statement->body[i], functions, nfunctions, nargs, nslots, narrays, depth + 1)) return 0;
    return 1;
  }
  return 0;
}

static int expression_string_type(const Expr *expr, const Function *function,
                                  const Function *functions, uint32_t nfunctions) {
  if (expr == NULL) return -1;
  switch (expr->kind) {
  case EX_STRING: return 1;
  case EX_CONST: return 0;
  case EX_RESULT: return function->return_string ? 1 : 0;
  case EX_LOCAL: return expr->slot < function->nargs + function->nlocals &&
      function->slot_types != NULL ? function->slot_types[expr->slot] : 0;
  case EX_ARRAY: return expr->array < function->narrays ? function->arrays[expr->array].is_string : -1;
  case EX_CALL:
    if (expr->callee >= nfunctions || functions[expr->callee].return_string) return -1;
    for (uint32_t i = 0; i < expr->nargs; i++)
      if (expression_string_type(expr->args[i], function, functions, nfunctions) != 0) return -1;
    return 0;
  case EX_NEG:
    return expression_string_type(expr->left, function, functions, nfunctions) == 0 ? 0 : -1;
  case EX_ADD: case EX_SUB: case EX_MUL: case EX_DIV:
  case EX_EQ: case EX_NE: case EX_LT: case EX_LE: case EX_GT: case EX_GE:
    return expression_string_type(expr->left, function, functions, nfunctions) == 0 &&
           expression_string_type(expr->right, function, functions, nfunctions) == 0 ? 0 : -1;
  default: return -1;
  }
}

static int validate_statement_types(const Statement *st, const Function *fn,
                                    const Function *functions, uint32_t nfunctions,
                                    uint32_t depth) {
  if (depth > MAX_CONTROL_DEPTH) return 0;
  if (st->kind == ST_ASSIGN) {
    int expected = st->target_kind == 1 ? fn->return_string :
                   st->target_kind == 2 ? fn->arrays[st->slot].is_string :
                   fn->slot_types != NULL ? fn->slot_types[st->slot] : 0;
    if (st->target_kind == 2 && expression_string_type(st->index, fn, functions, nfunctions) != 0) return 0;
    return expression_string_type(st->value, fn, functions, nfunctions) == expected;
  }
  if (st->kind == ST_IF) {
    if (expression_string_type(st->condition, fn, functions, nfunctions) != 0) return 0;
    for (uint32_t i = 0; i < st->nthen; i++) if (!validate_statement_types(&st->then_body[i], fn, functions, nfunctions, depth + 1)) return 0;
    for (uint32_t i = 0; i < st->nelse; i++) if (!validate_statement_types(&st->else_body[i], fn, functions, nfunctions, depth + 1)) return 0;
    return 1;
  }
  if (st->kind == ST_FOR) {
    if (st->start->kind != EX_CONST || st->end->kind != EX_CONST || st->step->kind != EX_CONST) return 0;
    for (uint32_t i = 0; i < st->nbody; i++) if (!validate_statement_types(&st->body[i], fn, functions, nfunctions, depth + 1)) return 0;
    return 1;
  }
  return 0;
}

static Function *read_projection(const uint8_t *data, size_t length,
                                 uint32_t *engine, uint32_t *target,
                                 uint32_t *nfunctions, uint32_t *call_argc,
                                 double call_args[MAX_ARGS], const char **error) {
  Reader reader = {data, length, 0, NULL};
  total_string_bytes = 0;
  uint8_t magic[4];
  uint32_t version;
  if (!read_bytes(&reader, magic, sizeof(magic)) ||
      (memcmp(magic, "BWM1", 4) != 0 && memcmp(magic, "BWM2", 4) != 0 &&
       memcmp(magic, "BWM3", 4) != 0 && memcmp(magic, "BWM4", 4) != 0 &&
       memcmp(magic, "BWM5", 4) != 0) ||
      !read_u32(&reader, &version) || !read_u32(&reader, engine) ||
      !read_u32(&reader, target) || !read_u32(&reader, nfunctions)) {
    *error = reader.error != NULL ? reader.error : "invalid binary projection header";
    return NULL;
  }
  int version5 = memcmp(magic, "BWM5", 4) == 0;
  int version4 = memcmp(magic, "BWM4", 4) == 0 || version5;
  int version3 = memcmp(magic, "BWM3", 4) == 0 || version4;
  int version2 = memcmp(magic, "BWM2", 4) == 0 || version3;
  if (version != (version5 ? 5u : version4 ? 4u : version3 ? 3u : version2 ? 2u : 1u) || *engine > 1 || *nfunctions == 0 || *nfunctions > MAX_FUNCTIONS ||
      *target >= *nfunctions) {
    *error = "unsupported binary projection header values";
    return NULL;
  }
  Function *functions = calloc(*nfunctions, sizeof(*functions));
  if (functions == NULL) {
    *error = "out of memory reading functions";
    return NULL;
  }
  uint32_t statement_total = 0;
  for (uint32_t i = 0; i < *nfunctions; i++) {
    Function *function = &functions[i];
    if (!read_u32(&reader, &function->nargs) || !read_u32(&reader, &function->nlocals)) goto fail;
    if (version2) {
      if (!read_u32(&reader, &function->narrays)) goto fail;
    }
    if (!read_u32(&reader, &function->nstatements)) goto fail;
    if (version4) {
      uint32_t return_type;
      if (!read_u32(&reader, &return_type) || return_type > 1) goto fail;
      function->return_string = (uint8_t)return_type;
      size_t slot_count = (size_t)function->nargs + function->nlocals;
      function->slot_types = calloc(slot_count == 0 ? 1 : slot_count, 1);
      if (function->slot_types == NULL) { reader.error = "out of memory reading slot types"; goto fail; }
      for (size_t k = 0; k < slot_count; k++) {
        if (!read_u8(&reader, &function->slot_types[k]) || function->slot_types[k] > 1 ||
            (k < function->nargs && function->slot_types[k] != 0)) {
          reader.error = "invalid local or argument type"; goto fail;
        }
      }
    }
    if (function->nargs > MAX_ARGS || function->nlocals > MAX_LOCALS ||
        function->narrays > MAX_ARRAYS ||
        function->nstatements > MAX_STATEMENTS) {
      reader.error = "function exceeds supported MIR worker limits";
      goto fail;
    }
    if (function->narrays != 0) {
      function->arrays = calloc(function->narrays, sizeof(*function->arrays));
      if (function->arrays == NULL) { reader.error = "out of memory reading arrays"; goto fail; }
      uint32_t total_elements = 0;
      for (uint32_t j = 0; j < function->narrays; j++) {
        Array *array = &function->arrays[j];
        if (!read_u32(&reader, &array->lower) || !read_u32(&reader, &array->upper)) goto fail;
        if (version4 && (!read_u8(&reader, &array->is_string) || array->is_string > 1)) { reader.error = "invalid array element type"; goto fail; }
        if (version5) {
          uint8_t shared_flag = 0;
          if (!read_u8(&reader, &shared_flag) || shared_flag > 1 ||
              !read_u32(&reader, &array->shared_slot) ||
              (shared_flag && array->shared_slot >= MAX_ARRAYS) ||
              (!shared_flag && array->shared_slot != UINT32_MAX)) {
            reader.error = "invalid shared-array metadata"; goto fail;
          }
          array->shared = shared_flag;
        }
        if (array->lower != 0 || array->upper >= MAX_ARRAY_ELEMENTS) {
          reader.error = "array bounds exceed supported fixed numeric-array limits";
          goto fail;
        }
        total_elements += array->upper - array->lower + 1;
        if (total_elements > MAX_TOTAL_ARRAY_ELEMENTS) {
          reader.error = "function exceeds supported total array capacity";
          goto fail;
        }
      }
    }
    function->statements = calloc(function->nstatements == 0 ? 1 : function->nstatements,
                                  sizeof(*function->statements));
    if (function->statements == NULL) {
      reader.error = "out of memory reading statements";
      goto fail;
    }
    for (uint32_t j = 0; j < function->nstatements; j++) {
      Statement *statement = &function->statements[j];
      if (version3) {
        if (!read_statement(&reader, statement, function->narrays, 0, &statement_total)) goto fail;
        continue;
      }
      if (!read_u8(&reader, &statement->target_kind)) goto fail;
      reader.offset += 3; /* reserved bytes */
      if (reader.offset > reader.length || !read_u32(&reader, &statement->slot)) goto fail;
      if (statement->target_kind > 2 ||
          (statement->target_kind == 0 && statement->slot >= function->nargs + function->nlocals)) {
        reader.error = "invalid assignment target slot";
        goto fail;
      }
      if (statement->target_kind == 2 && statement->slot >= function->narrays) {
        reader.error = "invalid array assignment target";
        goto fail;
      }
      if (statement->target_kind == 2) {
        statement->index = read_expr(&reader, 0, function->narrays);
        if (statement->index == NULL) goto fail;
      }
      statement->value = read_expr(&reader, 0, function->narrays);
      if (statement->value == NULL) goto fail;
    }
  }
  if (version5) {
    uint32_t expected_shared = 0;
    for (uint32_t j = 0; j < functions[0].narrays; j++) {
      Array *array = &functions[0].arrays[j];
      if (array->shared) {
        if (array->shared_slot != expected_shared++) {
          reader.error = "shared arrays must use dense declaration-order slots"; goto fail;
        }
      }
    }
    for (uint32_t i = 0; i < *nfunctions; i++) {
      uint8_t seen[MAX_ARRAYS] = {0};
      uint32_t count = 0;
      for (uint32_t j = 0; j < functions[i].narrays; j++) {
        Array *array = &functions[i].arrays[j];
        if (!array->shared) continue;
        if (array->shared_slot >= expected_shared || seen[array->shared_slot]++) {
          reader.error = "invalid or duplicate shared-array slot"; goto fail;
        }
        Array *reference = NULL;
        for (uint32_t k = 0; k < functions[0].narrays; k++)
          if (functions[0].arrays[k].shared && functions[0].arrays[k].shared_slot == array->shared_slot)
            reference = &functions[0].arrays[k];
        if (reference == NULL || reference->upper != array->upper || reference->is_string != array->is_string) {
          reader.error = "shared-array declarations disagree across functions"; goto fail;
        }
        count++;
      }
      if (count != expected_shared) {
        reader.error = "each function must carry the complete shared-array table"; goto fail;
      }
    }
  }
  for (uint32_t i = 0; i < *nfunctions; i++) {
    Function *function = &functions[i];
    uint32_t slots = function->nargs + function->nlocals;
    for (uint32_t j = 0; j < function->nstatements; j++) {
      Statement *statement = &function->statements[j];
      int valid = version3
          ? validate_statement(statement, functions, *nfunctions, function->nargs, slots, function->narrays, 0)
          : ((statement->index == NULL || validate_expr(statement->index, functions, *nfunctions, slots)) &&
             validate_expr(statement->value, functions, *nfunctions, slots));
      if (!valid || !validate_statement_types(statement, function, functions, *nfunctions, 0)) {
        reader.error = "invalid function, local, array, value type, or control-flow reference in projection";
        goto fail;
      }
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

static MIR_reg_t new_temp_t(MIR_context_t ctx, MIR_func_t function, uint32_t *counter, MIR_type_t type) {
  char name[40]; snprintf(name, sizeof(name), "tmp_%u", (*counter)++);
  return MIR_new_func_reg(ctx, function, type == MIR_T_P ? MIR_T_I64 : type, name);
}
static MIR_reg_t new_temp(MIR_context_t ctx, MIR_func_t function, uint32_t *counter) {
  return new_temp_t(ctx, function, counter, MIR_T_D);
}

static void emit_double_move(MIR_context_t ctx, MIR_item_t item, MIR_reg_t dst, MIR_op_t src) {
  MIR_append_insn(ctx, item, MIR_new_insn(ctx, MIR_DMOV, MIR_new_reg_op(ctx, dst), src));
}

static MIR_reg_t lower_expr(MIR_context_t, MIR_item_t, MIR_reg_t *, MIR_reg_t,
                            MIR_reg_t, MIR_item_t *, MIR_item_t *, uint32_t,
                            Array *, uint32_t, MIR_label_t *, const Expr *, uint32_t *);
static int lower_statement(MIR_context_t, MIR_item_t, const Statement *, MIR_reg_t *,
                           MIR_reg_t, MIR_reg_t, MIR_item_t *, MIR_item_t *, uint32_t,
                           Array *, uint32_t, MIR_label_t *, MIR_label_t *, uint32_t *, uint32_t);

static MIR_reg_t lower_checked_index(MIR_context_t ctx, MIR_item_t item, MIR_reg_t *slots,
                                     MIR_reg_t result_reg, MIR_reg_t error_reg,
                                     MIR_item_t *protos, MIR_item_t *forwards,
                                     uint32_t slot_count, Array *arrays, uint32_t narrays,
                                     MIR_label_t *bounds_bad, const Expr *index_expr,
                                     uint32_t array_slot, uint32_t *temp_counter) {
  (void) error_reg;
  if (array_slot >= narrays) return 0;
  MIR_reg_t raw = lower_expr(ctx, item, slots, result_reg, error_reg, protos, forwards,
                             slot_count, arrays, narrays, bounds_bad, index_expr, temp_counter);
  if (raw == 0) return 0;
  if (*bounds_bad == NULL) *bounds_bad = MIR_new_label(ctx);
  MIR_func_t function = item->u.func;
  char index_name[40];
  snprintf(index_name, sizeof(index_name), "array_index_%u", (*temp_counter)++);
  MIR_reg_t index = MIR_new_func_reg(ctx, function, MIR_T_I64, index_name);
  MIR_append_insn(ctx, item, MIR_new_insn(ctx, MIR_DBNE, MIR_new_label_op(ctx, *bounds_bad),
                                          MIR_new_reg_op(ctx, raw), MIR_new_reg_op(ctx, raw)));
  MIR_append_insn(ctx, item, MIR_new_insn(ctx, MIR_DBLT, MIR_new_label_op(ctx, *bounds_bad),
                                          MIR_new_reg_op(ctx, raw), MIR_new_double_op(ctx, -1.0)));
  MIR_append_insn(ctx, item, MIR_new_insn(ctx, MIR_DBGE, MIR_new_label_op(ctx, *bounds_bad),
                                          MIR_new_reg_op(ctx, raw),
                                          MIR_new_double_op(ctx, (double) arrays[array_slot].upper + 1.0)));
  MIR_append_insn(ctx, item, MIR_new_insn(ctx, MIR_D2I, MIR_new_reg_op(ctx, index),
                                          MIR_new_reg_op(ctx, raw)));
  /* The floating precheck intentionally allows fractions such as -0.5 that
     truncate to slot zero. Check the converted integer too: exactly -1.0
     truncates to -1 and must never form an address before the array base. */
  MIR_append_insn(ctx, item, MIR_new_insn(ctx, MIR_BLT, MIR_new_label_op(ctx, *bounds_bad),
                                          MIR_new_reg_op(ctx, index),
                                          MIR_new_int_op(ctx, arrays[array_slot].lower)));
  MIR_append_insn(ctx, item, MIR_new_insn(ctx, MIR_BGT, MIR_new_label_op(ctx, *bounds_bad),
                                          MIR_new_reg_op(ctx, index),
                                          MIR_new_int_op(ctx, arrays[array_slot].upper)));
  return index;
}

static int lower_array_store(MIR_context_t ctx, MIR_item_t item, Array *array,
                             MIR_reg_t index, MIR_reg_t value) {
  if (array->memory_backed) {
    MIR_append_insn(ctx, item, MIR_new_insn(ctx, array->is_string ? MIR_MOV : MIR_DMOV,
        MIR_new_mem_op(ctx, array->is_string ? MIR_T_P : MIR_T_D, 0, array->base, index, 8), MIR_new_reg_op(ctx, value)));
    return 1;
  }
  uint32_t capacity = array->upper - array->lower + 1;
  MIR_label_t done = MIR_new_label(ctx);
  MIR_label_t *cases = calloc(capacity, sizeof(*cases));
  if (cases == NULL) return 0;
  for (uint32_t i = 0; i < capacity; i++) {
    cases[i] = MIR_new_label(ctx);
    MIR_append_insn(ctx, item, MIR_new_insn(ctx, MIR_BEQ, MIR_new_label_op(ctx, cases[i]),
                                            MIR_new_reg_op(ctx, index),
                                            MIR_new_int_op(ctx, (int64_t) i)));
  }
  MIR_label_t bad = MIR_new_label(ctx);
  MIR_append_insn(ctx, item, MIR_new_insn(ctx, MIR_JMP, MIR_new_label_op(ctx, bad)));
  for (uint32_t i = 0; i < capacity; i++) {
    MIR_append_insn(ctx, item, cases[i]);
    emit_double_move(ctx, item, array->elements[i], MIR_new_reg_op(ctx, value));
    MIR_append_insn(ctx, item, MIR_new_insn(ctx, MIR_JMP, MIR_new_label_op(ctx, done)));
  }
  MIR_append_insn(ctx, item, bad);
  MIR_append_insn(ctx, item, MIR_new_insn(ctx, MIR_JMP, MIR_new_label_op(ctx, done)));
  MIR_append_insn(ctx, item, done);
  free(cases);
  return 1;
}

static int constant_array_index(const Expr *expr, const Array *array, uint32_t *slot) {
  if (expr == NULL || expr->kind != EX_CONST || !isfinite(expr->value)) return 0;
  double raw = expr->value;
  if (raw <= -1.0 || raw >= (double) array->upper + 1.0) return 0;
  int64_t index = (int64_t) raw; /* historical BASIC converts by truncating toward zero */
  if (index < (int64_t) array->lower || index > (int64_t) array->upper) return 0;
  *slot = (uint32_t) index;
  return 1;
}

static MIR_reg_t lower_expr(MIR_context_t ctx, MIR_item_t item, MIR_reg_t *slots,
                            MIR_reg_t result_reg, MIR_reg_t error_reg, MIR_item_t *protos,
                            MIR_item_t *forwards, uint32_t slot_count, Array *arrays,
                            uint32_t narrays, MIR_label_t *bounds_bad, const Expr *expr,
                            uint32_t *temp_counter) {
  MIR_func_t function = item->u.func;
  MIR_reg_t dst;
  switch (expr->kind) {
  case EX_STRING: {
    dst = new_temp_t(ctx, function, temp_counter, MIR_T_P);
    MIR_append_insn(ctx, item, MIR_new_insn(ctx, MIR_MOV, MIR_new_reg_op(ctx, dst), MIR_new_int_op(ctx, (int64_t)(intptr_t)expr->string)));
    return dst;
  }
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
    MIR_reg_t operand = lower_expr(ctx, item, slots, result_reg, error_reg, protos, forwards,
                                   slot_count, arrays, narrays, bounds_bad, expr->left, temp_counter);
    dst = new_temp(ctx, function, temp_counter);
    MIR_append_insn(ctx, item, MIR_new_insn(ctx, MIR_DNEG, MIR_new_reg_op(ctx, dst),
                                            MIR_new_reg_op(ctx, operand)));
    return dst;
  }
  case EX_ADD: case EX_SUB: case EX_MUL: case EX_DIV: {
    MIR_reg_t left = lower_expr(ctx, item, slots, result_reg, error_reg, protos, forwards,
                                slot_count, arrays, narrays, bounds_bad, expr->left, temp_counter);
    MIR_reg_t right = lower_expr(ctx, item, slots, result_reg, error_reg, protos, forwards,
                                 slot_count, arrays, narrays, bounds_bad, expr->right, temp_counter);
    MIR_insn_code_t code = expr->kind == EX_ADD ? MIR_DADD : expr->kind == EX_SUB ? MIR_DSUB :
                           expr->kind == EX_MUL ? MIR_DMUL : MIR_DDIV;
    dst = new_temp(ctx, function, temp_counter);
    MIR_append_insn(ctx, item, MIR_new_insn(ctx, code, MIR_new_reg_op(ctx, dst),
                                            MIR_new_reg_op(ctx, left), MIR_new_reg_op(ctx, right)));
    return dst;
  }
  case EX_EQ: case EX_NE: case EX_LT: case EX_LE: case EX_GT: case EX_GE: {
    MIR_reg_t left = lower_expr(ctx, item, slots, result_reg, error_reg, protos, forwards,
                                slot_count, arrays, narrays, bounds_bad, expr->left, temp_counter);
    MIR_reg_t right = lower_expr(ctx, item, slots, result_reg, error_reg, protos, forwards,
                                 slot_count, arrays, narrays, bounds_bad, expr->right, temp_counter);
    MIR_insn_code_t code = expr->kind == EX_EQ ? MIR_DBEQ : expr->kind == EX_NE ? MIR_DBNE :
                           expr->kind == EX_LT ? MIR_DBLT : expr->kind == EX_LE ? MIR_DBLE :
                           expr->kind == EX_GT ? MIR_DBGT : MIR_DBGE;
    MIR_label_t yes = MIR_new_label(ctx), done = MIR_new_label(ctx);
    dst = new_temp(ctx, function, temp_counter);
    MIR_append_insn(ctx, item, MIR_new_insn(ctx, code, MIR_new_label_op(ctx, yes),
        MIR_new_reg_op(ctx, left), MIR_new_reg_op(ctx, right)));
    emit_double_move(ctx, item, dst, MIR_new_double_op(ctx, 0.0));
    MIR_append_insn(ctx, item, MIR_new_insn(ctx, MIR_JMP, MIR_new_label_op(ctx, done)));
    MIR_append_insn(ctx, item, yes);
    emit_double_move(ctx, item, dst, MIR_new_double_op(ctx, 1.0));
    MIR_append_insn(ctx, item, done);
    return dst;
  }
  case EX_CALL: {
    MIR_op_t call_ops[4 + MAX_ARGS];
    if (expr->callee >= MAX_FUNCTIONS || expr->nargs > MAX_ARGS) return 0;
    dst = new_temp(ctx, function, temp_counter);
    call_ops[0] = MIR_new_ref_op(ctx, protos[expr->callee]);
    call_ops[1] = MIR_new_ref_op(ctx, forwards[expr->callee]);
    call_ops[2] = MIR_new_reg_op(ctx, dst);
    for (uint32_t i = 0; i < expr->nargs; i++) {
      MIR_reg_t arg = lower_expr(ctx, item, slots, result_reg, error_reg, protos, forwards,
                                 slot_count, arrays, narrays, bounds_bad, expr->args[i], temp_counter);
      call_ops[3 + i] = MIR_new_reg_op(ctx, arg);
    }
    call_ops[3 + expr->nargs] = MIR_new_reg_op(ctx, error_reg);
    MIR_append_insn(ctx, item, MIR_new_insn_arr(ctx, MIR_CALL, 4 + expr->nargs, call_ops));
    return dst;
  }
  case EX_ARRAY: {
    if (expr->array >= narrays) return 0;
    uint32_t constant_slot;
    if (constant_array_index(expr->left, &arrays[expr->array], &constant_slot)) {
      if (!arrays[expr->array].memory_backed)
        return arrays[expr->array].elements[constant_slot];
      dst = new_temp_t(ctx, function, temp_counter, arrays[expr->array].is_string ? MIR_T_P : MIR_T_D);
      MIR_append_insn(ctx, item, MIR_new_insn(ctx, arrays[expr->array].is_string ? MIR_MOV : MIR_DMOV, MIR_new_reg_op(ctx, dst),
          MIR_new_mem_op(ctx, arrays[expr->array].is_string ? MIR_T_P : MIR_T_D, (int64_t) constant_slot * 8,
                         arrays[expr->array].base, 0, 1)));
      return dst;
    }
    MIR_reg_t index = lower_checked_index(ctx, item, slots, result_reg, error_reg,
        protos, forwards, slot_count, arrays, narrays, bounds_bad, expr->left,
        expr->array, temp_counter);
    if (index == 0) return 0;
    dst = new_temp_t(ctx, function, temp_counter, arrays[expr->array].is_string ? MIR_T_P : MIR_T_D);
    if (arrays[expr->array].memory_backed) {
      MIR_append_insn(ctx, item, MIR_new_insn(ctx, arrays[expr->array].is_string ? MIR_MOV : MIR_DMOV,
          MIR_new_reg_op(ctx, dst), MIR_new_mem_op(ctx, arrays[expr->array].is_string ? MIR_T_P : MIR_T_D,
          0, arrays[expr->array].base, index, 8)));
      return dst;
    }
    MIR_label_t done = MIR_new_label(ctx);
    MIR_label_t *cases = calloc(arrays[expr->array].upper - arrays[expr->array].lower + 1,
                                sizeof(*cases));
    if (cases == NULL) return 0;
    uint32_t capacity = arrays[expr->array].upper - arrays[expr->array].lower + 1;
    for (uint32_t i = 0; i < capacity; i++) {
      cases[i] = MIR_new_label(ctx);
      MIR_append_insn(ctx, item, MIR_new_insn(ctx, MIR_BEQ, MIR_new_label_op(ctx, cases[i]),
                                              MIR_new_reg_op(ctx, index),
                                              MIR_new_int_op(ctx, (int64_t) i)));
    }
    MIR_append_insn(ctx, item, MIR_new_insn(ctx, MIR_JMP, MIR_new_label_op(ctx, *bounds_bad)));
    for (uint32_t i = 0; i < capacity; i++) {
      MIR_append_insn(ctx, item, cases[i]);
      emit_double_move(ctx, item, dst, MIR_new_reg_op(ctx, arrays[expr->array].elements[i]));
      MIR_append_insn(ctx, item, MIR_new_insn(ctx, MIR_JMP, MIR_new_label_op(ctx, done)));
    }
    MIR_append_insn(ctx, item, done);
    free(cases);
    return dst;
  }
  default:
    return 0;
  }
}

static int lower_statement(MIR_context_t ctx, MIR_item_t item, const Statement *statement,
                           MIR_reg_t *slots, MIR_reg_t result_reg, MIR_reg_t error_reg,
                           MIR_item_t *protos, MIR_item_t *forwards, uint32_t slot_count,
                           Array *arrays, uint32_t narrays, MIR_label_t *bounds_bad,
                           MIR_label_t *loop_bad, uint32_t *temp_counter, uint32_t depth) {
  if (depth > MAX_CONTROL_DEPTH) return 0;
  if (statement->kind == ST_ASSIGN) {
    MIR_reg_t value = lower_expr(ctx, item, slots, result_reg, error_reg, protos, forwards,
        slot_count, arrays, narrays, bounds_bad, statement->value, temp_counter);
    if (value == 0) return 0;
    if (statement->target_kind == 2) {
      Array *array = &arrays[statement->slot];
      uint32_t constant_slot;
      if (constant_array_index(statement->index, array, &constant_slot)) {
        if (array->memory_backed)
          MIR_append_insn(ctx, item, MIR_new_insn(ctx, array->is_string ? MIR_MOV : MIR_DMOV,
              MIR_new_mem_op(ctx, array->is_string ? MIR_T_P : MIR_T_D, (int64_t) constant_slot * 8, array->base, 0, 1),
              MIR_new_reg_op(ctx, value)));
        else
          emit_double_move(ctx, item, array->elements[constant_slot], MIR_new_reg_op(ctx, value));
        return 1;
      }
      MIR_reg_t index = lower_checked_index(ctx, item, slots, result_reg, error_reg,
          protos, forwards, slot_count, arrays, narrays, bounds_bad,
          statement->index, statement->slot, temp_counter);
      return index != 0 && lower_array_store(ctx, item, array, index, value);
    }
    MIR_reg_t destination = statement->target_kind == 1 ? result_reg : slots[statement->slot];
    if (destination == 0) return 0;
    int is_string = statement->target_kind == 1 ? active_function->return_string :
                    active_function->slot_types != NULL && active_function->slot_types[statement->slot];
    MIR_append_insn(ctx, item, MIR_new_insn(ctx, is_string ? MIR_MOV : MIR_DMOV,
        MIR_new_reg_op(ctx, destination), MIR_new_reg_op(ctx, value)));
    return 1;
  }
  if (statement->kind == ST_IF) {
    MIR_reg_t condition = lower_expr(ctx, item, slots, result_reg, error_reg, protos, forwards,
        slot_count, arrays, narrays, bounds_bad, statement->condition, temp_counter);
    if (condition == 0) return 0;
    MIR_label_t otherwise = MIR_new_label(ctx), done = MIR_new_label(ctx);
    MIR_append_insn(ctx, item, MIR_new_insn(ctx, MIR_DBEQ, MIR_new_label_op(ctx, otherwise),
        MIR_new_reg_op(ctx, condition), MIR_new_double_op(ctx, 0.0)));
    for (uint32_t i = 0; i < statement->nthen; i++)
      if (!lower_statement(ctx, item, &statement->then_body[i], slots, result_reg, error_reg,
          protos, forwards, slot_count, arrays, narrays, bounds_bad, loop_bad,
          temp_counter, depth + 1)) return 0;
    MIR_append_insn(ctx, item, MIR_new_insn(ctx, MIR_JMP, MIR_new_label_op(ctx, done)));
    MIR_append_insn(ctx, item, otherwise);
    for (uint32_t i = 0; i < statement->nelse; i++)
      if (!lower_statement(ctx, item, &statement->else_body[i], slots, result_reg, error_reg,
          protos, forwards, slot_count, arrays, narrays, bounds_bad, loop_bad,
          temp_counter, depth + 1)) return 0;
    MIR_append_insn(ctx, item, done);
    return 1;
  }
  if (statement->kind == ST_FOR) {
    if (statement->slot >= slot_count || slots[statement->slot] == 0) return 0;
    MIR_reg_t start = lower_expr(ctx, item, slots, result_reg, error_reg, protos, forwards,
        slot_count, arrays, narrays, bounds_bad, statement->start, temp_counter);
    MIR_reg_t end = lower_expr(ctx, item, slots, result_reg, error_reg, protos, forwards,
        slot_count, arrays, narrays, bounds_bad, statement->end, temp_counter);
    MIR_reg_t step = lower_expr(ctx, item, slots, result_reg, error_reg, protos, forwards,
        slot_count, arrays, narrays, bounds_bad, statement->step, temp_counter);
    if (start == 0 || end == 0 || step == 0) return 0;
    emit_double_move(ctx, item, slots[statement->slot], MIR_new_reg_op(ctx, start));
    char counter_name[48];
    snprintf(counter_name, sizeof(counter_name), "loop_count_%u", (*temp_counter)++);
    MIR_reg_t counter = MIR_new_func_reg(ctx, item->u.func, MIR_T_I64, counter_name);
    MIR_append_insn(ctx, item, MIR_new_insn(ctx, MIR_MOV, MIR_new_reg_op(ctx, counter), MIR_new_int_op(ctx, 0)));
    MIR_label_t top = MIR_new_label(ctx), done = MIR_new_label(ctx);
    if (*loop_bad == NULL) *loop_bad = MIR_new_label(ctx);
    MIR_append_insn(ctx, item, top);
    MIR_insn_code_t finish = statement->step->value > 0.0 ? MIR_DBGT : MIR_DBLT;
    MIR_append_insn(ctx, item, MIR_new_insn(ctx, finish, MIR_new_label_op(ctx, done),
        MIR_new_reg_op(ctx, slots[statement->slot]), MIR_new_reg_op(ctx, end)));
    MIR_append_insn(ctx, item, MIR_new_insn(ctx, MIR_BGE, MIR_new_label_op(ctx, *loop_bad),
        MIR_new_reg_op(ctx, counter), MIR_new_int_op(ctx, statement->iteration_limit)));
    for (uint32_t i = 0; i < statement->nbody; i++)
      if (!lower_statement(ctx, item, &statement->body[i], slots, result_reg, error_reg,
          protos, forwards, slot_count, arrays, narrays, bounds_bad, loop_bad,
          temp_counter, depth + 1)) return 0;
    MIR_append_insn(ctx, item, MIR_new_insn(ctx, MIR_DADD, MIR_new_reg_op(ctx, slots[statement->slot]),
        MIR_new_reg_op(ctx, slots[statement->slot]), MIR_new_reg_op(ctx, step)));
    MIR_append_insn(ctx, item, MIR_new_insn(ctx, MIR_ADD, MIR_new_reg_op(ctx, counter),
        MIR_new_reg_op(ctx, counter), MIR_new_int_op(ctx, 1)));
    MIR_append_insn(ctx, item, MIR_new_insn(ctx, MIR_JMP, MIR_new_label_op(ctx, top)));
    MIR_append_insn(ctx, item, done);
    return 1;
  }
  return 0;
}

static double call_native(void *address, uint32_t argc, const double *a, uint32_t *error_status) {
  switch (argc) {
  case 0: return ((double (*)(void *))address)(error_status);
  case 1: return ((double (*)(double, void *))address)(a[0], error_status);
  case 2: return ((double (*)(double, double, void *))address)(a[0], a[1], error_status);
  case 3: return ((double (*)(double, double, double, void *))address)(a[0], a[1], a[2], error_status);
  case 4: return ((double (*)(double, double, double, double, void *))address)(a[0], a[1], a[2], a[3], error_status);
  case 5: return ((double (*)(double, double, double, double, double, void *))address)(a[0], a[1], a[2], a[3], a[4], error_status);
  case 6: return ((double (*)(double, double, double, double, double, double, void *))address)(a[0], a[1], a[2], a[3], a[4], a[5], error_status);
  default: return NAN;
  }
}

static const char *call_native_string(void *address, uint32_t argc, const double *a, uint32_t *error_status) {
  switch (argc) {
  case 0: return ((const char *(*)(void *))address)(error_status);
  case 1: return ((const char *(*)(double, void *))address)(a[0], error_status);
  case 2: return ((const char *(*)(double, double, void *))address)(a[0], a[1], error_status);
  case 3: return ((const char *(*)(double, double, double, void *))address)(a[0], a[1], a[2], error_status);
  case 4: return ((const char *(*)(double, double, double, double, void *))address)(a[0], a[1], a[2], a[3], error_status);
  case 5: return ((const char *(*)(double, double, double, double, double, void *))address)(a[0], a[1], a[2], a[3], a[4], error_status);
  case 6: return ((const char *(*)(double, double, double, double, double, double, void *))address)(a[0], a[1], a[2], a[3], a[4], a[5], error_status);
  default: return NULL;
  }
}

static void report_error(const char *code, const char *message) {
  printf("{\"ok\":false,\"code\":\"%s\",\"message\":\"%s\"}\n", code, message);
}

static char *json_escape_string(const char *value, size_t length) {
  if (length > (SIZE_MAX - 1) / 6) return NULL;
  char *escaped = malloc(length * 6 + 1);
  if (escaped == NULL) return NULL;
  size_t out = 0;
  for (size_t i = 0; i < length; i++) {
    unsigned char c = (unsigned char)value[i];
    if (c == '\\' || c == '"') escaped[out++] = '\\';
    if (c < 0x20) {
      static const char hex[] = "0123456789abcdef";
      escaped[out++] = '\\'; escaped[out++] = 'u';
      escaped[out++] = '0'; escaped[out++] = '0';
      escaped[out++] = hex[c >> 4]; escaped[out++] = hex[c & 15];
    } else escaped[out++] = (char)c;
  }
  escaped[out] = 0;
  return escaped;
}

static double monotonic_ms(void) {
  struct timespec ts;
  if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0) return 0.0;
  return (double)ts.tv_sec * 1000.0 + (double)ts.tv_nsec / 1000000.0;
}

static uint8_t *read_stdin(size_t *size, int persistent) {
  if (persistent) {
    uint8_t header[4];
    if (fread(header, 1, sizeof(header), stdin) != sizeof(header)) return NULL;
    uint32_t length = (uint32_t)header[0] | ((uint32_t)header[1] << 8) |
                      ((uint32_t)header[2] << 16) | ((uint32_t)header[3] << 24);
    if (length == 0 || length > MAX_INPUT) return NULL;
    uint8_t *data = malloc(length);
    if (data == NULL) return NULL;
    if (fread(data, 1, length, stdin) != length) { free(data); return NULL; }
    *size = length;
    return data;
  }
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

static int read_exact(FILE *f, void *buffer, size_t length) {
  size_t offset = 0;
  while (offset < length) {
    size_t n = fread((uint8_t *)buffer + offset, 1, length - offset, f);
    if (n == 0) return 0;
    offset += n;
  }
  return 1;
}

static uint32_t load_u32_le(const uint8_t *p) {
  return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
         ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

/* Persistent protocol: each request is a u32 length followed by
   opcode:u8, request_id:u32, function_slot:u32, argc:u32, argc*f64.
   Shutdown is opcode 2 and contains only opcode + request_id. */
static int persistent_request(uint32_t *request_id, uint32_t *target,
                              uint32_t *argc, double args[MAX_ARGS]) {
  uint8_t header[4];
  if (!read_exact(stdin, header, sizeof(header))) return 0;
  uint32_t length = load_u32_le(header);
  if (length < 5 || length > 1 + 12 + MAX_ARGS * 8) return -1;
  uint8_t frame[1 + 12 + MAX_ARGS * 8];
  if (!read_exact(stdin, frame, length)) return -1;
  uint8_t opcode = frame[0];
  *request_id = load_u32_le(frame + 1);
  if (opcode == 2) return length == 5 ? 2 : -1;
  if (opcode != 1 || length < 13) return -1;
  *target = load_u32_le(frame + 5);
  *argc = load_u32_le(frame + 9);
  if (*argc > MAX_ARGS || length != 13 + *argc * 8) return -1;
  for (uint32_t i = 0; i < *argc; i++) {
    uint64_t bits = 0;
    for (unsigned b = 0; b < 8; b++) bits |= (uint64_t)frame[13 + i * 8 + b] << (b * 8);
    memcpy(&args[i], &bits, sizeof(bits));
    if (!isfinite(args[i])) return -1;
  }
  return 1;
}

static int persistent_call(MIR_context_t ctx, MIR_item_t *items, void **addresses,
                           uint32_t engine, Function *functions, uint32_t nfunctions,
                           uint32_t request_id, uint32_t target, uint32_t argc,
                           const double args[MAX_ARGS]) {
  if (target >= nfunctions || argc != functions[target].nargs ||
      functions[target].return_string) {
    printf("{\"ok\":false,\"request_id\":%u,\"code\":\"INVALID_CALL\",\"message\":\"persistent worker accepts numeric calls with matching arity\"}\n", request_id);
    fflush(stdout);
    return 1;
  }
  uint32_t error_status = 0;
  double result = 0;
  if (engine == 0) {
    MIR_val_t values[MAX_ARGS + 1], results[1];
    for (uint32_t i = 0; i < argc; i++) values[i].d = args[i];
    values[argc].a = &error_status;
    MIR_interp_arr(ctx, items[target], results, argc + 1, values);
    result = results[0].d;
  } else {
    result = call_native(addresses[target], argc, args, &error_status);
  }
  if (error_status != 0 || !isfinite(result)) {
    const char *code = error_status == 1 ? "ARRAY_BOUNDS" : error_status == 2 ? "LOOP_LIMIT" : "NON_FINITE_RESULT";
    printf("{\"ok\":false,\"request_id\":%u,\"code\":\"%s\",\"message\":\"persistent MIR call failed\"}\n", request_id, code);
  } else {
    printf("{\"ok\":true,\"request_id\":%u,\"result_type\":\"double\",\"result_hex\":\"%a\"}\n", request_id, result);
  }
  fflush(stdout);
  return 1;
}

int main(void) {
  int persistent = getenv("BASIC_WORKSPACE_PERSISTENT") != NULL;
  void **persistent_addresses = NULL;
  int persistent_gen_initialized = 0;
  const char *memory_mode = getenv("BASIC_WORKSPACE_MEMORY_ARRAYS");
  /* Prefer bounded stack storage by default. Set =0 to force the historical
     per-cell register/dispatch lowering for comparison and regression tests. */
  use_memory_arrays = memory_mode == NULL || strcmp(memory_mode, "0") != 0;
  size_t input_size = 0;
  uint8_t *input = read_stdin(&input_size, persistent);
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
  uint32_t mir_build_count = 0, mir_link_count = 0;
  MIR_context_t ctx = MIR_init();
  if (ctx == NULL) {
    free_functions(functions, nfunctions);
    report_error("MIR_INIT_FAILED", "MIR_init returned NULL");
    return 0;
  }
  MIR_module_t module = MIR_new_module(ctx, "basic_workspace_projection");
  MIR_item_t shared_data[MAX_ARRAYS] = {0};
  if (module != NULL) {
    for (uint32_t i = 0; i < nfunctions; i++) {
      for (uint32_t j = 0; j < functions[i].narrays; j++) {
        Array *array = &functions[i].arrays[j];
        if (!array->shared) continue;
        uint32_t slot = array->shared_slot;
        if (slot >= MAX_ARRAYS) { module = NULL; break; }
        uint32_t capacity = array->upper - array->lower + 1;
        if (shared_data[slot] == NULL) {
          char state_name[48];
          snprintf(state_name, sizeof(state_name), "bw_shared_array_%u", slot);
          shared_data[slot] = MIR_new_bss(ctx, state_name, (size_t)capacity * 8);
          if (shared_data[slot] == NULL) { module = NULL; break; }
        } else {
          for (uint32_t k = 0; k < i; k++) {
            for (uint32_t m = 0; m < functions[k].narrays; m++) {
              Array *prior = &functions[k].arrays[m];
              if (prior->shared && prior->shared_slot == slot &&
                  (prior->upper != array->upper || prior->is_string != array->is_string)) {
                module = NULL;
              }
            }
          }
        }
      }
      if (module == NULL) break;
    }
    for (uint32_t slot = 0; slot < MAX_ARRAYS; slot++) {
      if (shared_data[slot] != NULL) {
        for (uint32_t missing = 0; missing < slot; missing++)
          if (shared_data[missing] == NULL) module = NULL;
      }
    }
  }
  MIR_item_t *protos = calloc(nfunctions, sizeof(*protos));
  MIR_item_t *forwards = calloc(nfunctions, sizeof(*forwards));
  MIR_item_t *items = calloc(nfunctions, sizeof(*items));
  MIR_var_t *vars = calloc((size_t)nfunctions * (MAX_ARGS + 1), sizeof(*vars));
  char (*names)[MAX_ARGS + 1][32] = calloc(nfunctions, sizeof(*names));
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
    result_types[i] = functions[i].return_string ? MIR_T_P : MIR_T_D;
    MIR_var_t *function_vars = vars + (size_t)i * (MAX_ARGS + 1);
    for (uint32_t j = 0; j < functions[i].nargs; j++) {
      snprintf(names[i][j], sizeof(names[i][j]), "arg_%u_%u", i, j);
      function_vars[j].type = MIR_T_D;
      function_vars[j].name = names[i][j];
      function_vars[j].size = 0;
    }
    snprintf(names[i][functions[i].nargs], sizeof(names[i][functions[i].nargs]), "bw_error_%u", i);
    function_vars[functions[i].nargs].type = MIR_T_P;
    function_vars[functions[i].nargs].name = names[i][functions[i].nargs];
    function_vars[functions[i].nargs].size = 0;
    protos[i] = MIR_new_proto_arr(ctx, proto_name, 1, &result_types[i],
                                  functions[i].nargs + 1, function_vars);
    forwards[i] = MIR_new_forward(ctx, function_name);
    if (protos[i] == NULL || forwards[i] == NULL) { failed = 1; break; }
  }

  for (uint32_t i = 0; !failed && i < nfunctions; i++) {
    char function_name[48];
    snprintf(function_name, sizeof(function_name), "bw_func_%u", i);
    MIR_var_t *function_vars = vars + (size_t)i * (MAX_ARGS + 1);
    items[i] = MIR_new_func_arr(ctx, function_name, 1, &result_types[i],
                                functions[i].nargs + 1, function_vars);
    if (items[i] == NULL) { failed = 1; break; }
    MIR_func_t mir_func = items[i]->u.func;
    active_function = &functions[i];
    uint32_t slot_count = functions[i].nargs + functions[i].nlocals;
    MIR_reg_t *slots = calloc(slot_count == 0 ? 1 : slot_count, sizeof(*slots));
    if (slots == NULL) { failed = 1; break; }
    for (uint32_t j = 0; j < functions[i].nargs; j++)
      slots[j] = MIR_reg(ctx, names[i][j], mir_func);
    MIR_reg_t error_reg = MIR_reg(ctx, names[i][functions[i].nargs], mir_func);
    uint32_t temp_counter = 0;
    for (uint32_t j = 0; j < functions[i].nlocals; j++) {
      char local_name[48];
      snprintf(local_name, sizeof(local_name), "local_%u", j);
      MIR_type_t type = functions[i].slot_types != NULL && functions[i].slot_types[functions[i].nargs + j] ? MIR_T_P : MIR_T_D;
      slots[functions[i].nargs + j] = MIR_new_func_reg(ctx, mir_func, type == MIR_T_P ? MIR_T_I64 : type, local_name);
      if (type == MIR_T_P) MIR_append_insn(ctx, items[i], MIR_new_insn(ctx, MIR_MOV,
          MIR_new_reg_op(ctx, slots[functions[i].nargs + j]), MIR_new_int_op(ctx, (int64_t)(intptr_t)"" )));
      else emit_double_move(ctx, items[i], slots[functions[i].nargs + j], MIR_new_double_op(ctx, 0.0));
    }
    for (uint32_t j = 0; j < functions[i].narrays; j++) {
      Array *array = &functions[i].arrays[j];
      uint32_t capacity = array->upper - array->lower + 1;
      array->memory_backed = array->shared || use_memory_arrays || array->is_string;
      if (array->shared) {
        char array_name[48];
        snprintf(array_name, sizeof(array_name), "shared_array_%u", j);
        array->base = MIR_new_func_reg(ctx, mir_func, MIR_T_I64, array_name);
        if (array->base == 0 || array->shared_slot >= MAX_ARRAYS ||
            shared_data[array->shared_slot] == NULL) { failed = 1; break; }
        MIR_append_insn(ctx, items[i], MIR_new_insn(ctx, MIR_MOV,
            MIR_new_reg_op(ctx, array->base), MIR_new_ref_op(ctx, shared_data[array->shared_slot])));
        continue;
      }
      if (array->memory_backed) {
        char array_name[48];
        snprintf(array_name, sizeof(array_name), "array_mem_%u", j);
        /* MIR's ALLOCA result is an integer-typed address register. */
        array->base = MIR_new_func_reg(ctx, mir_func, MIR_T_I64, array_name);
        if (array->base == 0) { failed = 1; break; }
        /* MIR_ALLOCA is placed at function entry and uses a checked,
           compile-time byte count. All indexed accesses are bounds-checked
           before this private stack storage is addressed. */
        MIR_prepend_insn(ctx, items[i], MIR_new_insn(ctx, MIR_ALLOCA,
            MIR_new_reg_op(ctx, array->base), MIR_new_int_op(ctx, (int64_t) capacity * 8)));
        for (uint32_t k = 0; k < capacity; k++)
          MIR_append_insn(ctx, items[i], MIR_new_insn(ctx, array->is_string ? MIR_MOV : MIR_DMOV,
              MIR_new_mem_op(ctx, array->is_string ? MIR_T_P : MIR_T_D, (int64_t) k * 8, array->base, 0, 1),
              array->is_string ? MIR_new_int_op(ctx, (int64_t)(intptr_t)"" ) : MIR_new_double_op(ctx, 0.0)));
      } else {
        array->elements = calloc(capacity, sizeof(*array->elements));
        if (array->elements == NULL) { failed = 1; break; }
        for (uint32_t k = 0; k < capacity; k++) {
          char array_name[48];
          snprintf(array_name, sizeof(array_name), "array_%u_%u", j, k);
          array->elements[k] = MIR_new_func_reg(ctx, mir_func, MIR_T_D, array_name);
          emit_double_move(ctx, items[i], array->elements[k], MIR_new_double_op(ctx, 0.0));
        }
      }
    }
    if (failed) { free(slots); break; }
    MIR_reg_t return_reg = MIR_new_func_reg(ctx, mir_func, functions[i].return_string ? MIR_T_I64 : MIR_T_D, "basic_result");
    if (functions[i].return_string) MIR_append_insn(ctx, items[i], MIR_new_insn(ctx, MIR_MOV,
        MIR_new_reg_op(ctx, return_reg), MIR_new_int_op(ctx, (int64_t)(intptr_t)"" )));
    else emit_double_move(ctx, items[i], return_reg, MIR_new_double_op(ctx, 0.0));
    MIR_label_t bounds_bad = NULL, loop_bad = NULL;
    for (uint32_t j = 0; j < functions[i].nstatements; j++) {
      Statement *statement = &functions[i].statements[j];
      if (!lower_statement(ctx, items[i], statement, slots, return_reg, error_reg,
          protos, forwards, slot_count, functions[i].arrays, functions[i].narrays,
          &bounds_bad, &loop_bad, &temp_counter, 0)) { failed = 1; break; }
    }
    if (!failed) {
      if (bounds_bad != NULL || loop_bad != NULL) {
        MIR_label_t normal_exit = MIR_new_label(ctx);
        MIR_append_insn(ctx, items[i], MIR_new_insn(ctx, MIR_JMP, MIR_new_label_op(ctx, normal_exit)));
        if (bounds_bad != NULL) {
          MIR_append_insn(ctx, items[i], bounds_bad);
          MIR_append_insn(ctx, items[i], MIR_new_insn(ctx, MIR_MOV,
              MIR_new_mem_op(ctx, MIR_T_I32, 0, error_reg, 0, 1), MIR_new_int_op(ctx, 1)));
          MIR_append_insn(ctx, items[i], MIR_new_ret_insn(ctx, 1, functions[i].return_string ? MIR_new_int_op(ctx, (int64_t)(intptr_t)"" ) : MIR_new_double_op(ctx, NAN)));
        }
        if (loop_bad != NULL) {
          MIR_append_insn(ctx, items[i], loop_bad);
          MIR_append_insn(ctx, items[i], MIR_new_insn(ctx, MIR_MOV,
              MIR_new_mem_op(ctx, MIR_T_I32, 0, error_reg, 0, 1), MIR_new_int_op(ctx, 2)));
          MIR_append_insn(ctx, items[i], MIR_new_ret_insn(ctx, 1, functions[i].return_string ? MIR_new_int_op(ctx, (int64_t)(intptr_t)"" ) : MIR_new_double_op(ctx, NAN)));
        }
        MIR_append_insn(ctx, items[i], normal_exit);
      }
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
  mir_build_count++;
  build_ms = monotonic_ms() - build_started;
  if (getenv("BASIC_WORKSPACE_MIR_DUMP") != NULL) MIR_output(ctx, stderr);
  double result = 0.0;
  const char *string_result = NULL;
  uint32_t worker_error = 0;
  if (persistent) {
    double link_started_persistent = monotonic_ms();
    if (engine == 0) {
      MIR_link(ctx, MIR_set_interp_interface, NULL);
      mir_link_count++;
    } else {
      MIR_gen_init(ctx);
      persistent_gen_initialized = 1;
      MIR_link(ctx, MIR_set_gen_interface, NULL);
      mir_link_count++;
      persistent_addresses = calloc(nfunctions, sizeof(*persistent_addresses));
      if (persistent_addresses == NULL) {
        report_error("OUT_OF_MEMORY", "could not allocate persistent function table");
        goto cleanup;
      }
      double persistent_jit_started = monotonic_ms();
      for (uint32_t i = 0; i < nfunctions; i++) {
        persistent_addresses[i] = MIR_gen(ctx, items[i]);
        if (persistent_addresses[i] == NULL) {
          report_error("MIR_JIT_FAILED", "MIR_gen failed while preparing persistent module");
          goto cleanup;
        }
      }
      jit_compile_ms = monotonic_ms() - persistent_jit_started;
    }
    link_ms = monotonic_ms() - link_started_persistent;
    printf("{\"ready\":true,\"functions\":%u,\"engine\":\"%s\",\"mir_build_count\":%u,\"mir_link_count\":%u,\"timings_ms\":{\"mir_build\":%.6f,\"link\":%.6f,\"jit_compile\":%.6f}}\n",
           nfunctions, engine == 0 ? "interp" : "jit", mir_build_count,
           mir_link_count, build_ms, link_ms, jit_compile_ms);
    fflush(stdout);
    for (;;) {
      uint32_t request_id = 0, requested_target = 0, requested_argc = 0;
      double requested_args[MAX_ARGS] = {0};
      int request = persistent_request(&request_id, &requested_target,
                                       &requested_argc, requested_args);
      if (request == 0) break;
      if (request == 2) {
        printf("{\"ok\":true,\"request_id\":%u,\"shutdown\":true}\n", request_id);
        fflush(stdout);
        break;
      }
      if (request < 0) {
        printf("{\"ok\":false,\"request_id\":0,\"code\":\"INVALID_FRAME\",\"message\":\"malformed or oversized persistent request\"}\n");
        fflush(stdout);
        break;
      }
      persistent_call(ctx, items, persistent_addresses, engine, functions,
                      nfunctions, request_id, requested_target,
                      requested_argc, requested_args);
    }
    goto cleanup;
  }
  double link_started = monotonic_ms();
  if (engine == 0) {
    MIR_link(ctx, MIR_set_interp_interface, NULL);
    mir_link_count++;
    link_ms = monotonic_ms() - link_started;
    MIR_val_t values[MAX_ARGS + 1], results[1];
    for (uint32_t i = 0; i < argc; i++) values[i].d = args[i];
    values[argc].a = &worker_error;
    double invoke_started = monotonic_ms();
    MIR_interp_arr(ctx, items[target], results, argc + 1, values);
    invoke_ms = monotonic_ms() - invoke_started;
    if (functions[target].return_string) string_result = (const char *)results[0].a;
    else result = results[0].d;
  } else {
    MIR_gen_init(ctx);
    MIR_link(ctx, MIR_set_gen_interface, NULL);
    mir_link_count++;
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
    if (functions[target].return_string) string_result = call_native_string(address, argc, args, &worker_error);
    else result = call_native(address, argc, args, &worker_error);
    invoke_ms = monotonic_ms() - invoke_started;
    MIR_gen_finish(ctx);
  }
  if (worker_error == 1) {
    report_error("ARRAY_BOUNDS", "numeric array index is outside its declared bounds");
  } else if (worker_error == 2) {
    report_error("LOOP_LIMIT", "bounded FOR exceeded its runtime iteration limit");
  } else if (!functions[target].return_string && !isfinite(result)) {
    report_error("NON_FINITE_RESULT", "execution produced a non-finite double result");
  } else if (functions[target].return_string && string_result == NULL) {
    report_error("INVALID_STRING_RESULT", "MIR returned a null string pointer");
  } else {
    struct rusage usage;
    long maxrss_kib = getrusage(RUSAGE_SELF, &usage) == 0 ? usage.ru_maxrss : -1;
    if (functions[target].return_string) {
      double copy_started = monotonic_ms();
      size_t n = strnlen(string_result, MAX_STRING_BYTES + 1);
      if (n > MAX_STRING_BYTES || !valid_utf8((const unsigned char *)string_result, n)) {
        report_error("INVALID_STRING_RESULT", "MIR returned an invalid or oversized string");
        goto cleanup;
      }
      char *escaped = json_escape_string(string_result, n);
      if (escaped == NULL) { report_error("OUT_OF_MEMORY", "could not copy string result to JSON"); goto cleanup; }
      double result_copy_ms = monotonic_ms() - copy_started;
      printf("{\"ok\":true,\"result_type\":\"string\",\"result_length\":%zu,\"result\":\"%s\",\"timings_ms\":{\"mir_build\":%.6f,\"link\":%.6f,\"jit_compile\":%.6f,\"invoke\":%.6f,\"result_copy_json\":%.6f},\"maxrss_kib\":%ld}\n",
             n, escaped, build_ms, link_ms, jit_compile_ms, invoke_ms, result_copy_ms, maxrss_kib);
      free(escaped);
    } else {
      printf("{\"ok\":true,\"result_type\":\"double\",\"result_hex\":\"%a\",\"timings_ms\":{\"mir_build\":%.6f,\"link\":%.6f,\"jit_compile\":%.6f,\"invoke\":%.6f},\"maxrss_kib\":%ld}\n",
             result, build_ms, link_ms, jit_compile_ms, invoke_ms, maxrss_kib);
    }
  }

cleanup:
  if (persistent_gen_initialized) MIR_gen_finish(ctx);
  MIR_finish(ctx);
  free_functions(functions, nfunctions);
  free(protos);
  free(forwards);
  free(items);
  free(vars);
  free(names);
  free(result_types);
  free(persistent_addresses);
  return 0;
}
