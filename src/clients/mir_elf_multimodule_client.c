#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>

typedef int64_t (*unary_fn)(int64_t);

int main(int argc, char **argv) {
  void *handle;
  unary_fn result, plus3;
  int64_t *factor;
  int64_t got;
  int ok;
  if (argc != 2) return 2;
  handle = dlopen(argv[1], RTLD_NOW | RTLD_LOCAL);
  if (!handle) { fprintf(stderr, "dlopen: %s\n", dlerror()); return 3; }
  result = (unary_fn)dlsym(handle, "demo_result");
  plus3 = (unary_fn)dlsym(handle, "demo_plus3");
  factor = (int64_t *)dlsym(handle, "demo_factor");
  if (!result || !plus3 || !factor) { fprintf(stderr, "dlsym: %s\n", dlerror()); return 4; }
  got = result(-8);
  printf("path=dlopen result=%lld plus3=%lld factor=%lld\n",
         (long long)got, (long long)plus3(-8), (long long)*factor);
  ok = got == 30 && plus3(-8) == -5 && *factor == 6;
  if (dlclose(handle) != 0) { fprintf(stderr, "dlclose: %s\n", dlerror()); return 5; }
  return ok ? 0 : 6;
}
