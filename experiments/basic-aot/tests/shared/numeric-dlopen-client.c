#define _GNU_SOURCE
#include <dlfcn.h>
#include <math.h>
#include <stdio.h>

typedef double (*square_fn)(double);
typedef double (*add_fn)(double, double);

int main(int argc, char **argv) {
  if (argc != 2) return 2;
  void *handle = dlopen(argv[1], RTLD_NOW | RTLD_LOCAL);
  if (handle == NULL) {
    fprintf(stderr, "dlopen: %s\n", dlerror());
    return 3;
  }
  square_fn square = (square_fn)dlsym(handle, "SQUARE");
  add_fn add = (add_fn)dlsym(handle, "ADD");
  if (square == NULL || add == NULL || dlsym(handle, "main") != NULL
      || fabs(square(-0.125) - 0.015625) > 1e-14
      || fabs(add(1.25, -0.5) - 0.75) > 1e-14)
    return 4;
  if (dlclose(handle) != 0) return 5;
  puts("PASS: numeric-only MIR ET_DYN RTLD_NOW|RTLD_LOCAL");
  return 0;
}
