#define _GNU_SOURCE
#include "basic-shared-api.h"

#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

typedef void (*lifecycle_fn)(void);
typedef char *(*string1_fn)(const char *);
typedef char *(*string2_fn)(const char *, const char *);
typedef void (*fail_fn)(void);
typedef void (*free_fn)(char *);

static void fail(const char *what) {
  fprintf(stderr, "FAIL: %s\n", what);
  exit(1);
}

static size_t rss_kib(void) {
  FILE *f = fopen("/proc/self/status", "r");
  if (f == NULL) return 0;
  char line[256];
  size_t result = 0;
  while (fgets(line, sizeof(line), f) != NULL) {
    if (sscanf(line, "VmRSS: %zu kB", &result) == 1) break;
  }
  fclose(f);
  return result;
}

static void *symbol(void *handle, const char *name) {
  dlerror();
  void *value = dlsym(handle, name);
  if (dlerror() != NULL || value == NULL) fail(name);
  return value;
}

int main(int argc, char **argv) {
  if (argc != 2) return 2;
  void *h = dlopen(argv[1], RTLD_NOW | RTLD_LOCAL);
  if (h == NULL) fail(dlerror());
  lifecycle_fn init = (lifecycle_fn)symbol(h, "basic_module_init");
  lifecycle_fn fini = (lifecycle_fn)symbol(h, "basic_module_fini");
  string1_fn upper = (string1_fn)symbol(h, "BASIC_UPPER");
  string1_fn literal = (string1_fn)symbol(h, "BASIC_LITERAL");
  string1_fn echo = (string1_fn)symbol(h, "BASIC_ECHO");
  string1_fn local = (string1_fn)symbol(h, "BASIC_LOCAL");
  string1_fn empty = (string1_fn)symbol(h, "BASIC_EMPTY");
  string1_fn borrowed = (string1_fn)symbol(h, "BASIC_BORROWED");
  string2_fn concat = (string2_fn)symbol(h, "BASIC_CONCAT");
  free_fn basic_string_free_fn = (free_fn)symbol(h, "basic_string_free");
  fail_fn fail_alloc = (fail_fn)symbol(h, "basic_shared_test_fail_next_alloc");
  dlerror();
  if (dlsym(h, "BASIC_NOT_PRESENT") != NULL || dlerror() == NULL)
    fail("missing symbol did not fail");

  init();
  char *a = upper("bonjour");
  char *b = literal("ignored");
  char *c = echo("borrowed argument");
  char *d = local("local value");
  char *e = concat("left", "-right");
  char *f = empty("ignored");
  const char *borrowed_input = "borrowed argument";
  char *g = borrowed(borrowed_input);
  if (!a || strcmp(a, "BONJOUR") || !b || strcmp(b, "literal") || !c
      || strcmp(c, "borrowed argument") || !d || strcmp(d, "LOCAL VALUE")
      || !e || strcmp(e, "left-right") || !f || strcmp(f, "") || !g
      || strcmp(g, borrowed_input))
    fail("string result category/value");
  if (upper(NULL) != NULL || literal(NULL) != NULL || concat("x", NULL) != NULL)
    fail("NULL argument convention");

  /* Results are independent malloc buffers: mutate and free out of order. */
  a[0] = 'b';
  if (strcmp(a, "bONJOUR") || strcmp(c, "borrowed argument"))
    fail("result aliases input or another result");
  free(e);
  free(b);
  free(d);
  free(a);
  free(f);
  basic_string_free_fn(c);
  free(g);

  fail_alloc();
  if (upper("allocation failure") != NULL) fail("allocation failure injection");

  size_t before = rss_kib();
  for (size_t i = 0; i < 10000; i++) {
    char *out = upper("short stress string");
    if (out == NULL || strcmp(out, "SHORT STRESS STRING")) fail("stress call");
    free(out);
  }
  size_t after = rss_kib();
  if (after > before + 16384) fail("unexpected RSS increase over 10,000 calls");

  char *survivor = upper("alive after unload");
  if (survivor == NULL || strcmp(survivor, "ALIVE AFTER UNLOAD")) fail("survivor result");
  fini();
  if (strcmp(survivor, "ALIVE AFTER UNLOAD")) fail("result invalidated by module fini");
  if (dlclose(h) != 0) fail("dlclose");
  if (strcmp(survivor, "ALIVE AFTER UNLOAD")) fail("result invalidated by dlclose");
  free(survivor);

  for (int i = 0; i < 3; i++) {
    h = dlopen(argv[1], RTLD_NOW | RTLD_LOCAL);
    if (h == NULL) fail("reload DSO");
    init = (lifecycle_fn)symbol(h, "basic_module_init");
    fini = (lifecycle_fn)symbol(h, "basic_module_fini");
    upper = (string1_fn)symbol(h, "BASIC_UPPER");
    init();
    char *reload_result = upper("reload");
    if (reload_result == NULL || strcmp(reload_result, "RELOAD")) fail("reload call");
    fini();
    if (dlclose(h) != 0) fail("reload dlclose");
    free(reload_result);
  }

  printf("PASS: string ownership, NULL/failure handling, 10000 calls, RSS %zu -> %zu KiB, free after dlclose\n",
         before, after);
  return 0;
}
