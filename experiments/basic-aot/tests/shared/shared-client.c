#define _GNU_SOURCE
#include <dlfcn.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#ifdef BASIC_DEMO_DIRECT
extern double SQUARE(double);
extern double ADD(double, double);
extern double STRLEN(const char *);
extern void REPORT(double);
#endif

typedef double (*square_fn)(double);
typedef double (*add_fn)(double, double);
typedef double (*strlen_fn)(const char *);
typedef void (*report_fn)(double);
typedef void (*lifecycle_fn)(void);

static int close_enough(double a, double b) { return fabs(a - b) < 1e-12; }

#ifndef BASIC_DEMO_DIRECT
static double elapsed_ns(struct timespec a, struct timespec b) {
  return (b.tv_sec - a.tv_sec) * 1e9 + (b.tv_nsec - a.tv_nsec);
}

static double call_c_square(double x) __attribute__((noinline));
static double call_c_square(double x) { return x * x; }

static int check_values(square_fn square, add_fn add, strlen_fn str_len) {
  const double xs[] = {0.0, 2.5, -3.0, -0.125, 1234.5};
  for (size_t i = 0; i < sizeof(xs) / sizeof(xs[0]); i++)
    if (!close_enough(square(xs[i]), xs[i] * xs[i])) return 0;
  if (!close_enough(add(0.0, 0.0), 0.0)
      || !close_enough(add(-1.25, 4.5), 3.25)
      || !close_enough(add(-2.0, -3.5), -5.5)
      || !close_enough(str_len("BASIC"), 5.0)
      || !close_enough(str_len(""), 0.0)) return 0;
  return 1;
}
#endif

#ifndef BASIC_DEMO_DIRECT
static int run_dynamic(const char *path, uint64_t iterations) {
  struct timespec t0, t1, t2, t3, t4, t5;
  clock_gettime(CLOCK_MONOTONIC, &t0);
  void *handle = dlopen(path, RTLD_NOW | RTLD_LOCAL);
  clock_gettime(CLOCK_MONOTONIC, &t1);
  if (handle == NULL) { fprintf(stderr, "dlopen: %s\n", dlerror()); return 2; }

  dlerror();
  square_fn square = (square_fn)dlsym(handle, "SQUARE");
  const char *sym_error = dlerror();
  add_fn add = (add_fn)dlsym(handle, "ADD");
  strlen_fn str_len = (strlen_fn)dlsym(handle, "STRLEN");
  report_fn report = (report_fn)dlsym(handle, "REPORT");
  lifecycle_fn init = (lifecycle_fn)dlsym(handle, "basic_module_init");
  lifecycle_fn fini = (lifecycle_fn)dlsym(handle, "basic_module_fini");
  clock_gettime(CLOCK_MONOTONIC, &t2);
  if (sym_error != NULL || square == NULL || add == NULL || str_len == NULL || report == NULL
      || init == NULL || fini == NULL) {
    fprintf(stderr, "dlsym failed: %s\n", sym_error ? sym_error : dlerror());
    dlclose(handle);
    return 3;
  }
  init();
  dlerror();
  void *missing = dlsym(handle, "BASIC_SYMBOL_THAT_DOES_NOT_EXIST");
  const char *missing_error = dlerror();
  if (missing != NULL || missing_error == NULL) {
    fprintf(stderr, "missing dlsym was not rejected\n");
    dlclose(handle);
    return 4;
  }
  if (!check_values(square, add, str_len)) {
    fprintf(stderr, "shared BASIC function returned an incorrect result\n");
    dlclose(handle);
    return 5;
  }
  report(12.5);

  if (iterations != 0) {
    volatile double basic_sum = 0.0, c_sum = 0.0;
    square_fn c_square = call_c_square;
    clock_gettime(CLOCK_MONOTONIC, &t2);
    for (uint64_t i = 0; i < 10000; i++) (void)dlsym(handle, "SQUARE");
    clock_gettime(CLOCK_MONOTONIC, &t3);
    for (uint64_t i = 0; i < iterations; i++) basic_sum += square((double)(i % 101) * 0.5);
    clock_gettime(CLOCK_MONOTONIC, &t4);
    for (uint64_t i = 0; i < iterations; i++) c_sum += c_square((double)(i % 101) * 0.5);
    clock_gettime(CLOCK_MONOTONIC, &t5);
    if (!close_enough(basic_sum, c_sum)) return 6;
    printf("dlopen_ns=%.0f\ndlsym_ns_each=%.2f\nbasic_call_ns_each=%.3f\nc_call_ns_each=%.3f\n",
           elapsed_ns(t0, t1), elapsed_ns(t2, t3) / 10000.0,
           elapsed_ns(t3, t4) / (double)iterations,
           elapsed_ns(t4, t5) / (double)iterations);
    clock_gettime(CLOCK_MONOTONIC, &t0);
    fini();
    if (dlclose(handle) != 0) { fprintf(stderr, "dlclose failed\n"); return 7; }
    clock_gettime(CLOCK_MONOTONIC, &t1);
    printf("dlclose_ns=%.0f\n", elapsed_ns(t0, t1));
    return 0;
  }

  clock_gettime(CLOCK_MONOTONIC, &t3);
  fini();
  if (dlclose(handle) != 0) { fprintf(stderr, "dlclose failed\n"); return 7; }
  clock_gettime(CLOCK_MONOTONIC, &t4);
  /* Repeat map/unmap and direct calls to catch module-lifetime state leaks. */
  for (int i = 0; i < 3; i++) {
    handle = dlopen(path, RTLD_NOW | RTLD_LOCAL);
    if (handle == NULL) { fprintf(stderr, "reload dlopen: %s\n", dlerror()); return 8; }
    init = (lifecycle_fn)dlsym(handle, "basic_module_init");
    fini = (lifecycle_fn)dlsym(handle, "basic_module_fini");
    square = (square_fn)dlsym(handle, "SQUARE");
    if (init == NULL || fini == NULL || square == NULL) return 9;
    init();
    if (!close_enough(square(-4.25), 18.0625)) return 9;
    fini();
    if (dlclose(handle) != 0) return 10;
  }
  puts("PASS: dlopen/dlsym/dlclose, reload, numeric ABI and string input");
  (void)t3; (void)t4;
  return 0;
}
#endif

int main(int argc, char **argv) {
#ifdef BASIC_DEMO_DIRECT
  (void)argc; (void)argv;
  if (!close_enough(SQUARE(-2.5), 6.25) || !close_enough(ADD(1.25, 2.0), 3.25)
      || !close_enough(STRLEN("C ABI"), 5.0)) return 1;
  REPORT(12.5);
  puts("PASS: direct ELF link to BASIC exports");
  return 0;
#else
  if (argc < 2 || argc > 3) {
    fprintf(stderr, "usage: %s library.so [iterations]\n", argv[0]);
    return 2;
  }
  return run_dynamic(argv[1], argc == 3 ? strtoull(argv[2], NULL, 10) : 0);
#endif
}
