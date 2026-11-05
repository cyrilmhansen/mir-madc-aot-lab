/* Standalone MIR C API smoke test. No MADC frontend or libmadc is linked. */
#include "mir.h"
#include "mir-gen.h"

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <sys/resource.h>

static const char *program =
  "m_a: module\n"
  "  export plus3\n"
  "plus3: func i64, i64:x\n"
  "  add x, x, 3\n"
  "  ret x\n"
  "  endfunc\n"
  "  endmodule\n"
  "m_b: module\n"
  "  export result\n"
  "  import plus3, labs\n"
  "p_plus3: proto i64, i64:x\n"
  "p_labs: proto i64, i64:x\n"
  "result: func i64, i64:x\n"
  "  local i64:t\n"
  "  call p_plus3, plus3, t, x\n"
  "  call p_labs, labs, t, t\n"
  "  ret t\n"
  "  endfunc\n"
  "  endmodule\n";

static MIR_item_t find_item(MIR_context_t ctx, const char *name) {
  MIR_module_t module;
  MIR_item_t item;
  for (module = DLIST_HEAD(MIR_module_t, *MIR_get_module_list(ctx)); module;
       module = DLIST_NEXT(MIR_module_t, module))
    for (item = DLIST_HEAD(MIR_item_t, module->items); item;
         item = DLIST_NEXT(MIR_item_t, item)) {
      const char *item_name = MIR_item_name(ctx, item);
      if (item->item_type == MIR_func_item && item_name
          && strcmp(item_name, name) == 0)
        return item;
    }
  return NULL;
}

static int run_context(MIR_context_t ctx, int write_ir, const char *ir_path) {
  MIR_module_t module;
  MIR_item_t item;
  int64_t (*result_fn)(int64_t);

  if (write_ir) {
    FILE *f = fopen(ir_path, "wb");
    if (!f) return 10;
    MIR_write(ctx, f);
    if (fclose(f) != 0) return 11;
  }
  for (module = DLIST_HEAD(MIR_module_t, *MIR_get_module_list(ctx)); module;
       module = DLIST_NEXT(MIR_module_t, module))
    MIR_load_module(ctx, module);
  MIR_load_external(ctx, "labs", labs);
  MIR_gen_init(ctx);
  MIR_link(ctx, MIR_set_gen_interface, NULL);
  item = find_item(ctx, "plus3");
  if (!item) return 12;
  (void)MIR_gen(ctx, item);
  item = find_item(ctx, "result");
  if (!item || item->item_type != MIR_func_item) return 13;
  (void)MIR_gen(ctx, item);
  result_fn = (int64_t (*)(int64_t))item->addr;
  if (!result_fn || result_fn(-8) != 5) return 14;
  MIR_gen_finish(ctx);
  return 0;
}

static uint64_t now_ns(void) {
  struct timespec ts;
  if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0) return 0;
  return (uint64_t)ts.tv_sec * 1000000000ULL + (uint64_t)ts.tv_nsec;
}

static char *read_file(const char *path, size_t *size_out) {
  FILE *f = fopen(path, "rb");
  long n;
  char *buf;
  if (!f || fseek(f, 0, SEEK_END) != 0 || (n = ftell(f)) < 0
      || fseek(f, 0, SEEK_SET) != 0) {
    if (f) fclose(f);
    return NULL;
  }
  buf = (char *)malloc((size_t)n + 1);
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

static int run_corpus(const char *path, size_t expected_count, int binary_p,
                      int write_binary_p, const char *binary_path) {
  MIR_context_t ctx = MIR_init();
  MIR_module_t module;
  MIR_item_t item;
  char *contents = NULL;
  size_t contents_size = 0, function_count = 0, called = 0;
  uint64_t parse_start = now_ns(), parse_ns, link_start, link_ns;
  uint64_t gen_start, gen_ns, first_start, first_ns, run_start, run_ns;
  int64_t sum = 0;
  struct rusage usage;
  long maxrss_bytes;
  if (binary_p) {
    FILE *f = fopen(path, "rb");
    if (!f) { MIR_finish(ctx); return 31; }
    MIR_read(ctx, f);
    fclose(f);
  } else {
    contents = read_file(path, &contents_size);
    if (!contents) { MIR_finish(ctx); return 32; }
    MIR_scan_string(ctx, contents);
  }
  parse_ns = now_ns() - parse_start;
  if (write_binary_p) {
    FILE *f = fopen(binary_path, "wb");
    if (!f) { free(contents); MIR_finish(ctx); return 33; }
    MIR_write(ctx, f);
    if (fclose(f) != 0) { free(contents); MIR_finish(ctx); return 34; }
  }
  for (module = DLIST_HEAD(MIR_module_t, *MIR_get_module_list(ctx)); module;
       module = DLIST_NEXT(MIR_module_t, module))
    MIR_load_module(ctx, module);
  MIR_gen_init(ctx);
  link_start = now_ns();
  MIR_link(ctx, MIR_set_gen_interface, NULL);
  link_ns = now_ns() - link_start;
  gen_start = now_ns();
  for (module = DLIST_HEAD(MIR_module_t, *MIR_get_module_list(ctx)); module;
       module = DLIST_NEXT(MIR_module_t, module))
    for (item = DLIST_HEAD(MIR_item_t, module->items); item;
         item = DLIST_NEXT(MIR_item_t, item))
      if (item->item_type == MIR_func_item) {
        const char *name = MIR_item_name(ctx, item);
        if (name && strncmp(name, "bench_", 6) == 0) {
          (void)MIR_gen(ctx, item);
          function_count++;
        }
      }
  gen_ns = now_ns() - gen_start;
  if (function_count != expected_count) {
    fprintf(stderr, "expected %lu benchmark functions, parsed %lu\n",
            (unsigned long)expected_count, (unsigned long)function_count);
    free(contents); MIR_gen_finish(ctx); MIR_finish(ctx); return 35;
  }
  first_start = now_ns();
  run_start = first_start;
  for (module = DLIST_HEAD(MIR_module_t, *MIR_get_module_list(ctx)); module;
       module = DLIST_NEXT(MIR_module_t, module))
    for (item = DLIST_HEAD(MIR_item_t, module->items); item;
         item = DLIST_NEXT(MIR_item_t, item))
      if (item->item_type == MIR_func_item) {
        const char *name = MIR_item_name(ctx, item);
        if (name && strncmp(name, "bench_", 6) == 0) {
          size_t idx = (size_t)strtoul(name + 6, NULL, 10);
          int64_t x = 17;
          int64_t expected = x * (int64_t)(idx + 3) + (int64_t)(idx * idx);
          int64_t actual = ((int64_t (*)(int64_t))item->addr)(x);
          if (called == 0) first_ns = now_ns() - first_start;
          if (actual != expected) {
            fprintf(stderr, "%s returned %lld, expected %lld\n", name,
                    (long long)actual, (long long)expected);
            free(contents); MIR_gen_finish(ctx); MIR_finish(ctx); return 36;
          }
          sum += actual;
          called++;
        }
      }
  run_ns = now_ns() - run_start;
  if (called == 0) first_ns = 0;
  if (getrusage(RUSAGE_SELF, &usage) != 0) memset(&usage, 0, sizeof usage);
#if defined(__APPLE__)
  maxrss_bytes = usage.ru_maxrss;
#else
  maxrss_bytes = usage.ru_maxrss * 1024L;
#endif
  printf("{\"functions\":%lu,\"parse_ns\":%llu,\"link_ns\":%llu,"
         "\"jit_ns\":%llu,\"first_call_ns\":%llu,\"calls_ns\":%llu,"
         "\"verified_calls\":%lu,\"result_checksum\":%lld,\"input_bytes\":%lu,"
         "\"user_cpu_us\":%llu,\"system_cpu_us\":%llu,\"minor_faults\":%ld,"
         "\"major_faults\":%ld,\"maxrss_bytes\":%ld}\n",
         (unsigned long)function_count, (unsigned long long)parse_ns,
         (unsigned long long)link_ns, (unsigned long long)gen_ns,
         (unsigned long long)first_ns, (unsigned long long)run_ns,
         (unsigned long)called, (long long)sum, (unsigned long)contents_size,
         (unsigned long long)usage.ru_utime.tv_sec * 1000000ULL
           + (unsigned long long)usage.ru_utime.tv_usec,
         (unsigned long long)usage.ru_stime.tv_sec * 1000000ULL
           + (unsigned long long)usage.ru_stime.tv_usec,
         usage.ru_minflt, usage.ru_majflt, maxrss_bytes);
  free(contents);
  MIR_gen_finish(ctx);
  MIR_finish(ctx);
  return 0;
}

int main(int argc, char **argv) {
  MIR_context_t ctx;
  int rc;
  if (argc == 4 && strcmp(argv[1], "corpus-text") == 0)
    return run_corpus(argv[2], (size_t)strtoul(argv[3], NULL, 10), 0, 0, NULL);
  if (argc == 4 && strcmp(argv[1], "corpus-bmir") == 0)
    return run_corpus(argv[2], (size_t)strtoul(argv[3], NULL, 10), 1, 0, NULL);
  if (argc == 5 && strcmp(argv[1], "write-ir") == 0)
    return run_corpus(argv[2], (size_t)strtoul(argv[3], NULL, 10), 0, 1,
                      argv[4]);
  if (argc == 3 && strcmp(argv[1], "read") == 0) {
    FILE *f = fopen(argv[2], "rb");
    if (!f) return 20;
    ctx = MIR_init();
    MIR_read(ctx, f);
    fclose(f);
  } else {
    ctx = MIR_init();
    MIR_scan_string(ctx, program);
  }
  rc = run_context(ctx, argc >= 2 && strcmp(argv[1], "write") == 0,
                   argc > 2 ? argv[2] : "program.bmir");
  MIR_finish(ctx);
  if (rc != 0) {
    fprintf(stderr, "libmir smoke failed: %d\n", rc);
    return rc;
  }
  puts("libmir JIT result: 5 (verified)");
  return 0;
}
