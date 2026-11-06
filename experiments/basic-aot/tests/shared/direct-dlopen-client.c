#define _GNU_SOURCE
#include <dlfcn.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef double (*square_fn)(double);
typedef char *(*upper_fn)(const char *);
typedef void (*lifecycle_fn)(void);

static void *symbol(void *handle, const char *name) {
  dlerror();
  void *result = dlsym(handle, name);
  const char *error = dlerror();
  return error == NULL ? result : NULL;
}

int main(int argc, char **argv) {
  if (argc != 2) return 2;
  void *handle = dlopen(argv[1], RTLD_NOW | RTLD_LOCAL);
  if (handle == NULL) {
    fprintf(stderr, "dlopen: %s\n", dlerror());
    return 3;
  }
  square_fn square = (square_fn)symbol(handle, "SQUARE");
  upper_fn upper = (upper_fn)symbol(handle, "BASIC_UPPER");
  lifecycle_fn init = (lifecycle_fn)symbol(handle, "basic_module_init");
  lifecycle_fn fini = (lifecycle_fn)symbol(handle, "basic_module_fini");
  if (square == NULL || upper == NULL || init == NULL || fini == NULL
      || symbol(handle, "UPPERTEST$") != NULL || fabs(square(-2.5) - 6.25) > 1e-14)
    return 4;
  init();
  char *owned = upper("bonjour");
  if (owned == NULL || strcmp(owned, "BONJOUR") != 0) return 5;
  fini();
  if (dlclose(handle) != 0) return 6;
  if (strcmp(owned, "BONJOUR") != 0) return 7;
  free(owned);
  puts("PASS: direct MIR DSO RTLD_NOW|RTLD_LOCAL, hidden internals, owned result after dlclose");
  return 0;
}
