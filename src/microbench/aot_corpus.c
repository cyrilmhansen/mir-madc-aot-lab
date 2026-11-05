/* Linux x86-64 MIR native-artifact generator and in-process ET_REL loader. */
#define _GNU_SOURCE
#include "mir.h"
#include "mir-gen.h"
#include "mir-debug.h"

#include <dlfcn.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <sys/stat.h>
#include <sys/resource.h>

static uint64_t now_ns(void) {
  struct timespec ts;
  clock_gettime(CLOCK_MONOTONIC, &ts);
  return (uint64_t)ts.tv_sec * 1000000000ULL + (uint64_t)ts.tv_nsec;
}

static char *read_path(const char *path, size_t *size) {
  FILE *f = fopen(path, "rb");
  long n;
  char *p;
  if (!f || fseek(f, 0, SEEK_END) || (n = ftell(f)) < 0 || fseek(f, 0, SEEK_SET)) {
    if (f) fclose(f);
    return NULL;
  }
  p = (char *)malloc((size_t)n + 1);
  if (!p || fread(p, 1, (size_t)n, f) != (size_t)n) {
    free(p);
    fclose(f);
    return NULL;
  }
  fclose(f);
  p[n] = 0;
  *size = (size_t)n;
  return p;
}

static int write_image(const char *path, void *buf, size_t size) {
  FILE *f = fopen(path, "wb");
  int rc;
  if (!f) return -1;
  rc = fwrite(buf, 1, size, f) == size && fclose(f) == 0 ? 0 : -1;
  return rc;
}

static void *resolver(const char *name, void *env) {
  (void)env;
  return dlsym(RTLD_DEFAULT, name);
}

static int prepare_capture(const char *mir_path, size_t count, int object_mode,
                           MIR_context_t *ctx_out, char **source_out,
                           uint64_t *parse_ns, uint64_t *link_ns,
                           uint64_t *gen_ns) {
  MIR_context_t ctx = MIR_init();
  char *source;
  size_t source_size;
  MIR_module_t module;
  MIR_item_t item;
  size_t generated = 0;
  uint64_t t;
  source = read_path(mir_path, &source_size);
  if (!source) return 2;
  t = now_ns();
  MIR_scan_string(ctx, source);
  *parse_ns = now_ns() - t;
  for (module = DLIST_HEAD(MIR_module_t, *MIR_get_module_list(ctx)); module;
       module = DLIST_NEXT(MIR_module_t, module))
    MIR_load_module(ctx, module);
  MIR_gen_init(ctx);
  if (object_mode) MIR_gen_set_object_mode(ctx, 1);
  t = now_ns();
  MIR_link(ctx, MIR_set_gen_interface, NULL);
  *link_ns = now_ns() - t;
  t = now_ns();
  for (module = DLIST_HEAD(MIR_module_t, *MIR_get_module_list(ctx)); module;
       module = DLIST_NEXT(MIR_module_t, module))
    for (item = DLIST_HEAD(MIR_item_t, module->items); item;
         item = DLIST_NEXT(MIR_item_t, item)) {
      const char *name = item->item_type == MIR_func_item ? MIR_item_name(ctx, item) : NULL;
      if (name && (strncmp(name, "bench_", 6) == 0 || !strcmp(name, "main"))) {
        (void)MIR_gen(ctx, item);
        if (strncmp(name, "bench_", 6) == 0) generated++;
      }
    }
  *gen_ns = now_ns() - t;
  if (generated != count) {
    fprintf(stderr, "expected %zu functions, generated %zu\n", count, generated);
    MIR_gen_finish(ctx);
    MIR_finish(ctx);
    free(source);
    return 3;
  }
  *ctx_out = ctx;
  *source_out = source;
  (void)source_size;
  return 0;
}

static int emit_artifact(const char *kind, const char *mir_path, const char *out,
                         size_t count) {
  MIR_context_t ctx;
  char *source;
  void *buf = NULL;
  size_t size = 0;
  uint64_t parse_ns, link_ns, gen_ns, t, emit_ns;
  MIR_object_exec_params params = {0};
  const char *pie_needed[] = {"libc.so.6"};
  int rc = prepare_capture(mir_path, count, 1, &ctx, &source,
                           &parse_ns, &link_ns, &gen_ns);
  if (rc) return rc;
  t = now_ns();
  if (!strcmp(kind, "object")) {
    rc = MIR_gen_object_emit(ctx, &buf, &size);
  } else {
    params.shared_p = !strcmp(kind, "shared");
    params.pie_p = !strcmp(kind, "pie");
    if (params.pie_p) {
      params.needed = pie_needed;
      params.n_needed = 1;
    }
    rc = MIR_gen_object_emit_executable(ctx, &params, &buf, &size);
  }
  emit_ns = now_ns() - t;
  if (rc || !buf || write_image(out, buf, size)) {
    fprintf(stderr, "MIR native emit failed (%s, rc=%d)\n", kind, rc);
    free(buf);
    free(source);
    MIR_gen_finish(ctx);
    MIR_finish(ctx);
    return 4;
  }
  if (!strcmp(kind, "pie") && chmod(out, 0755) != 0) {
    perror("chmod PIE");
    free(buf);
    free(source);
    MIR_gen_finish(ctx);
    MIR_finish(ctx);
    return 9;
  }
  printf("{\"artifact\":\"%s\",\"functions\":%zu,\"parse_ns\":%" PRIu64
         ",\"link_ns\":%" PRIu64 ",\"jit_or_capture_ns\":%" PRIu64
         ",\"emit_ns\":%" PRIu64 ",\"artifact_bytes\":%zu}\n",
         kind, count, parse_ns, link_ns, gen_ns, emit_ns, size);
  free(buf);
  free(source);
  MIR_gen_finish(ctx);
  MIR_finish(ctx);
  return 0;
}

static int load_object(const char *path, size_t count) {
  char err[512] = {0};
  size_t size = 0, called = 0;
  char *bytes = read_path(path, &size);
  MIR_object_loaded_t loaded;
  uint64_t t, load_ns, resolve_start, resolve_ns, first_start, first_ns = 0;
  int64_t sum = 0;
  struct rusage usage;
  if (!bytes) return 5;
  t = now_ns();
  loaded = MIR_object_load(bytes, size, resolver, NULL, err, sizeof err);
  load_ns = now_ns() - t;
  if (!loaded) {
    fprintf(stderr, "MIR_object_load: %s\n", err);
    free(bytes);
    return 6;
  }
  resolve_start = now_ns();
  first_start = 0;
  for (size_t i = 0; i < count; i++) {
    char name[32];
    int64_t (*fn)(int64_t);
    int64_t x = 17;
    int64_t expected = x * (int64_t)(i + 3) + (int64_t)(i * i);
    snprintf(name, sizeof name, "bench_%05zu", i);
    fn = (int64_t (*)(int64_t))MIR_object_loaded_sym(loaded, name);
    if (!fn) {
      fprintf(stderr, "missing loaded symbol %s\n", name);
      MIR_object_loaded_unload(loaded);
      free(bytes);
      return 7;
    }
    if (i == 0) first_start = now_ns();
    int64_t got = fn(x);
    if (!i) first_ns = now_ns() - first_start;
    if (got != expected) {
      fprintf(stderr, "%s returned %" PRId64 ", expected %" PRId64 "\n", name, got, expected);
      MIR_object_loaded_unload(loaded);
      free(bytes);
      return 8;
    }
    sum += got;
    called++;
  }
  resolve_ns = now_ns() - resolve_start;
  getrusage(RUSAGE_SELF, &usage);
  printf("{\"scenario\":\"elf_object_MIR_object_load\",\"functions\":%zu,"
         "\"load_relocate_ns\":%" PRIu64 ",\"symbol_resolve_and_calls_ns\":%" PRIu64
         ",\"first_call_ns\":%" PRIu64 ",\"verified_calls\":%zu,"
         "\"result_checksum\":%" PRId64 ",\"artifact_bytes\":%zu,"
         "\"minor_faults\":%ld,\"major_faults\":%ld,\"maxrss_kib\":%ld}\n",
         count, load_ns, resolve_ns, first_ns, called, sum, size,
         usage.ru_minflt, usage.ru_majflt, usage.ru_maxrss);
  MIR_object_loaded_unload(loaded);
  free(bytes);
  return 0;
}

int main(int argc, char **argv) {
  if (argc == 6 && !strcmp(argv[1], "emit"))
    return emit_artifact(argv[2], argv[3], argv[4], strtoul(argv[5], NULL, 10));
  if (argc == 4 && !strcmp(argv[1], "load"))
    return load_object(argv[2], strtoul(argv[3], NULL, 10));
  fprintf(stderr, "usage: %s emit {object|shared|pie} input.mir output count | load input.o count\n", argv[0]);
  return 2;
}
