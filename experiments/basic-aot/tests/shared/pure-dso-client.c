#define _GNU_SOURCE
#include <dlfcn.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>

typedef double (*unary_fn)(double);
typedef double (*binary_fn)(double, double);

int main(int argc, char **argv) {
  if (argc != 2) return 2;
  void *handle = dlopen(argv[1], RTLD_NOW | RTLD_LOCAL);
  if (handle == NULL) { fprintf(stderr, "%s\n", dlerror()); return 3; }
  unary_fn square = (unary_fn)dlsym(handle, "SQUARE");
  binary_fn add = (binary_fn)dlsym(handle, "ADD");
  if (square == NULL || add == NULL
      || fabs(square(-2.5) - 6.25) > 1e-12 || fabs(add(1.25, 2.0) - 3.25) > 1e-12
      || fabs(add(-1.0, -2.5) + 3.5) > 1e-12) return 4;
  if (dlclose(handle) != 0) return 5;
  puts("PASS: direct MIR shared image exports callable pure BASIC functions");
  return 0;
}
