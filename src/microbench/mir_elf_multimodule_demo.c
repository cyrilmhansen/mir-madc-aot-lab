/* Functional MIR ELF demonstration: two modules, exported functions/data,
   an external libc call, and the five persistence/execution paths. */
#define _GNU_SOURCE
#include "mir.h"
#include "mir-gen.h"
#include "mir-debug.h"

#include <dlfcn.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

#define APPEND(f, insn) MIR_append_insn(ctx, (f), (insn))

static MIR_item_t build_program(MIR_context_t ctx) {
  MIR_type_t ret_type = MIR_T_I64;
  int64_t factor = 6;
  MIR_module_t first = MIR_new_module(ctx, "demo_math");
  MIR_item_t factor_data = MIR_new_data(ctx, "demo_factor", MIR_T_I64, 1, &factor);
  MIR_item_t plus3 = MIR_new_func(ctx, "demo_plus3", 1, &ret_type, 1,
                                  MIR_T_I64, "x");
  MIR_reg_t x = MIR_reg(ctx, "x", plus3->u.func);
  MIR_reg_t r = MIR_new_func_reg(ctx, plus3->u.func, MIR_T_I64, "r");
  APPEND(plus3, MIR_new_insn(ctx, MIR_ADD, MIR_new_reg_op(ctx, r),
                             MIR_new_reg_op(ctx, x), MIR_new_int_op(ctx, 3)));
  APPEND(plus3, MIR_new_ret_insn(ctx, 1, MIR_new_reg_op(ctx, r)));
  MIR_finish_func(ctx);
  MIR_new_export(ctx, "demo_plus3");
  MIR_new_export(ctx, "demo_factor");
  MIR_finish_module(ctx);

  MIR_module_t second = MIR_new_module(ctx, "demo_api");
  MIR_item_t plus3_import = MIR_new_import(ctx, "demo_plus3");
  MIR_item_t factor_import = MIR_new_import(ctx, "demo_factor");
  MIR_item_t labs_import = MIR_new_import(ctx, "labs");
  MIR_item_t plus3_proto = MIR_new_proto(ctx, "demo_plus3_proto", 1, &ret_type,
                                         1, MIR_T_I64, "x");
  MIR_item_t labs_proto = MIR_new_proto(ctx, "labs_proto", 1, &ret_type,
                                        1, MIR_T_I64, "x");
  MIR_item_t result = MIR_new_func(ctx, "demo_result", 1, &ret_type, 1,
                                   MIR_T_I64, "x");
  MIR_reg_t in = MIR_reg(ctx, "x", result->u.func);
  MIR_reg_t addr = MIR_new_func_reg(ctx, result->u.func, MIR_T_I64, "addr");
  MIR_reg_t value = MIR_new_func_reg(ctx, result->u.func, MIR_T_I64, "value");
  MIR_reg_t scale = MIR_new_func_reg(ctx, result->u.func, MIR_T_I64, "scale");
  APPEND(result, MIR_new_call_insn(ctx, 4, MIR_new_ref_op(ctx, plus3_proto),
                                   MIR_new_ref_op(ctx, plus3_import),
                                   MIR_new_reg_op(ctx, value), MIR_new_reg_op(ctx, in)));
  APPEND(result, MIR_new_insn(ctx, MIR_MOV, MIR_new_reg_op(ctx, addr),
                              MIR_new_ref_op(ctx, factor_import)));
  APPEND(result, MIR_new_insn(ctx, MIR_MOV, MIR_new_reg_op(ctx, scale),
                              MIR_new_mem_op(ctx, MIR_T_I64, 0, addr, 0, 0)));
  APPEND(result, MIR_new_insn(ctx, MIR_MUL, MIR_new_reg_op(ctx, value),
                              MIR_new_reg_op(ctx, value), MIR_new_reg_op(ctx, scale)));
  APPEND(result, MIR_new_call_insn(ctx, 4, MIR_new_ref_op(ctx, labs_proto),
                                   MIR_new_ref_op(ctx, labs_import),
                                   MIR_new_reg_op(ctx, value), MIR_new_reg_op(ctx, value)));
  APPEND(result, MIR_new_ret_insn(ctx, 1, MIR_new_reg_op(ctx, value)));
  MIR_finish_func(ctx);
  MIR_new_export(ctx, "demo_result");

  MIR_item_t main_item = MIR_new_func(ctx, "main", 1, &ret_type, 0);
  MIR_reg_t main_result = MIR_new_func_reg(ctx, main_item->u.func, MIR_T_I64, "r");
  APPEND(main_item, MIR_new_call_insn(ctx, 4, MIR_new_ref_op(ctx, plus3_proto),
                                      MIR_new_ref_op(ctx, result),
                                      MIR_new_reg_op(ctx, main_result),
                                      MIR_new_int_op(ctx, -8)));
  APPEND(main_item, MIR_new_ret_insn(ctx, 1, MIR_new_reg_op(ctx, main_result)));
  MIR_finish_func(ctx);
  MIR_new_export(ctx, "main");
  MIR_finish_module(ctx);
  (void)second;
  (void)first;
  (void)factor_data;
  return result;
}

static char *read_file(const char *path, size_t *size_out) {
  FILE *f = fopen(path, "rb");
  long n;
  char *buf;
  if (!f || fseek(f, 0, SEEK_END) || (n = ftell(f)) < 0 || fseek(f, 0, SEEK_SET)) {
    if (f) fclose(f);
    return NULL;
  }
  buf = malloc((size_t)n + 1);
  if (!buf || fread(buf, 1, (size_t)n, f) != (size_t)n) {
    free(buf);
    fclose(f);
    return NULL;
  }
  fclose(f);
  buf[n] = '\0';
  *size_out = (size_t)n;
  return buf;
}

static MIR_context_t read_ir(const char *path, int binary_p) {
  MIR_context_t ctx = MIR_init();
  if (binary_p) {
    FILE *f = fopen(path, "rb");
    if (!f) return NULL;
    MIR_read(ctx, f);
    fclose(f);
  } else {
    size_t n;
    char *text = read_file(path, &n);
    if (!text) return NULL;
    MIR_scan_string(ctx, text);
    free(text);
  }
  return ctx;
}

static MIR_item_t find_item(MIR_context_t ctx, const char *name) {
  MIR_module_t m;
  MIR_item_t item;
  for (m = DLIST_HEAD(MIR_module_t, *MIR_get_module_list(ctx)); m;
       m = DLIST_NEXT(MIR_module_t, m))
    for (item = DLIST_HEAD(MIR_item_t, m->items); item;
         item = DLIST_NEXT(MIR_item_t, item))
      if (item->item_type == MIR_func_item && !strcmp(MIR_item_name(ctx, item), name))
        return item;
  return NULL;
}

static void load_and_link(MIR_context_t ctx, int object_mode) {
  MIR_module_t m;
  for (m = DLIST_HEAD(MIR_module_t, *MIR_get_module_list(ctx)); m;
       m = DLIST_NEXT(MIR_module_t, m))
    MIR_load_module(ctx, m);
  MIR_load_external(ctx, "labs", labs);
  MIR_gen_init(ctx);
  if (object_mode) MIR_gen_set_object_mode(ctx, 1);
  MIR_link(ctx, MIR_set_gen_interface, NULL);
}

static int jit_run(const char *path, int binary_p) {
  MIR_context_t ctx = read_ir(path, binary_p);
  MIR_module_t m;
  MIR_item_t item;
  int64_t got;
  if (!ctx) return 2;
  load_and_link(ctx, 0);
  /* Generate all functions eagerly before the first call. */
  for (m = DLIST_HEAD(MIR_module_t, *MIR_get_module_list(ctx)); m;
       m = DLIST_NEXT(MIR_module_t, m))
    for (item = DLIST_HEAD(MIR_item_t, m->items); item;
         item = DLIST_NEXT(MIR_item_t, item))
      if (item->item_type == MIR_func_item) (void)MIR_gen(ctx, item);
  item = find_item(ctx, "demo_result");
  got = ((int64_t (*)(int64_t))item->addr)(-8);
  printf("path=%s result=%" PRId64 "\n", binary_p ? "bmir-jit" : "text-jit", got);
  MIR_gen_finish(ctx);
  MIR_finish(ctx);
  return got == 30 ? 0 : 3;
}

static int emit(const char *kind, const char *input, const char *output) {
  MIR_context_t ctx = read_ir(input, 0);
  MIR_module_t m;
  MIR_item_t item;
  MIR_object_exec_params params = {0};
  void *buf = NULL;
  size_t size = 0;
  const char *needed[] = {"libc.so.6"};
  int rc;
  if (!ctx) return 2;
  load_and_link(ctx, 1);
  for (m = DLIST_HEAD(MIR_module_t, *MIR_get_module_list(ctx)); m;
       m = DLIST_NEXT(MIR_module_t, m))
    for (item = DLIST_HEAD(MIR_item_t, m->items); item;
         item = DLIST_NEXT(MIR_item_t, item))
      if (item->item_type == MIR_func_item) (void)MIR_gen(ctx, item);
  if (!strcmp(kind, "object")) {
    rc = MIR_gen_object_emit(ctx, &buf, &size);
  } else {
    params.shared_p = !strcmp(kind, "shared");
    params.pie_p = !strcmp(kind, "pie");
    params.needed = needed;
    params.n_needed = 1;
    rc = MIR_gen_object_emit_executable(ctx, &params, &buf, &size);
  }
  if (rc || !buf) return 4;
  FILE *f = fopen(output, "wb");
  if (!f || fwrite(buf, 1, size, f) != size || fclose(f) != 0) return 5;
  if (!strcmp(kind, "pie") && chmod(output, 0755) != 0) return 6;
  printf("artifact=%s bytes=%zu\n", kind, size);
  free(buf);
  MIR_gen_finish(ctx);
  MIR_finish(ctx);
  return 0;
}

static void *resolver(const char *name, void *env) {
  (void)env;
  void *address = dlsym(RTLD_DEFAULT, name);
  fprintf(stderr, "resolve %s -> %p\n", name, address);
  return address;
}

static int load_object(const char *path) {
  size_t n;
  char *bytes = read_file(path, &n);
  char err[512] = {0};
  MIR_object_loaded_t loaded;
  int64_t (*result)(int64_t);
  int64_t (*plus3)(int64_t);
  int64_t *factor;
  int64_t got;
  int64_t plus3_got;
  int ok;
  if (!bytes) return 2;
  loaded = MIR_object_load(bytes, n, resolver, NULL, err, sizeof err);
  if (!loaded) { fprintf(stderr, "MIR_object_load: %s\n", err); free(bytes); return 3; }
  result = (int64_t (*)(int64_t))MIR_object_loaded_sym(loaded, "demo_result");
  plus3 = (int64_t (*)(int64_t))MIR_object_loaded_sym(loaded, "demo_plus3");
  factor = (int64_t *)MIR_object_loaded_sym(loaded, "demo_factor");
  fprintf(stderr, "loaded result=%p plus3=%p factor=%p labs=%p\n",
          (void *)result, (void *)plus3, (void *)factor, dlsym(RTLD_DEFAULT, "labs"));
  if (plus3) fprintf(stderr, "plus3(-8)=%" PRId64 "\n", plus3(-8));
  got = result ? result(-8) : -1;
  plus3_got = plus3 ? plus3(-8) : -1;
  printf("path=object-load result=%" PRId64 " plus3=%" PRId64 " factor=%" PRId64 "\n",
         got, plus3_got, factor ? *factor : -1);
  ok = got == 30 && plus3_got == -5 && factor && *factor == 6;
  MIR_object_loaded_unload(loaded);
  free(bytes);
  return ok ? 0 : 4;
}

int main(int argc, char **argv) {
  if (argc == 4 && !strcmp(argv[1], "generate")) {
    MIR_context_t ctx = MIR_init();
    FILE *text, *binary;
    build_program(ctx);
    text = fopen(argv[2], "w");
    binary = fopen(argv[3], "wb");
    if (!text || !binary) return 2;
    MIR_output(ctx, text);
    MIR_write(ctx, binary);
    fclose(text);
    fclose(binary);
    MIR_finish(ctx);
    return 0;
  }
  if (argc == 3 && !strcmp(argv[1], "jit-text")) return jit_run(argv[2], 0);
  if (argc == 3 && !strcmp(argv[1], "jit-bmir")) return jit_run(argv[2], 1);
  if (argc == 5 && !strcmp(argv[1], "emit")) return emit(argv[2], argv[3], argv[4]);
  if (argc == 3 && !strcmp(argv[1], "load")) return load_object(argv[2]);
  fprintf(stderr, "usage: %s generate text.mir program.bmir | jit-text file | jit-bmir file | emit object|shared|pie text.mir output | load file.o\n", argv[0]);
  return 1;
}
