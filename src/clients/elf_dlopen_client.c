#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdio.h>

typedef int (*binary_fn)(int, int);
typedef int (*unary_fn)(int);

int main(int argc, char **argv) {
  if (argc != 2) return 2;
  void *handle = dlopen(argv[1], RTLD_NOW | RTLD_LOCAL);
  if (!handle) { fprintf(stderr, "dlopen: %s\n", dlerror()); return 3; }
  binary_fn add = (binary_fn)dlsym(handle, "lab_add");
  unary_fn scale = (unary_fn)dlsym(handle, "lab_scale");
  int *global = (int *)dlsym(handle, "lab_global_multiplier");
  if (!add || !scale || !global) { fprintf(stderr, "dlsym: %s\n", dlerror()); return 4; }
  int a = add(20, 22), b = scale(7), g = *global;
  if (a != 42 || b != 42 || g != 6) {
    fprintf(stderr, "mismatch: add=%d scale=%d global=%d\n", a, b, g);
    return 5;
  }
  printf("PASS add=%d scale=%d global=%d\n", a, b, g);
  if (dlclose(handle) != 0) { fprintf(stderr, "dlclose: %s\n", dlerror()); return 6; }
  return 0;
}
