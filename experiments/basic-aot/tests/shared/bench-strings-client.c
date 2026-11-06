#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

typedef void (*lifecycle_fn)(void);
typedef char *(*upper_fn)(const char *);

static uint64_t ns_now(void) {
  struct timespec t;
  clock_gettime(CLOCK_MONOTONIC, &t);
  return (uint64_t)t.tv_sec * 1000000000 + (uint64_t)t.tv_nsec;
}

int main(int argc, char **argv) {
  if (argc != 3) return 2;
  size_t count = strtoull(argv[2], NULL, 10);
  void *h = dlopen(argv[1], RTLD_NOW | RTLD_LOCAL);
  if (h == NULL) return 3;
  lifecycle_fn init = (lifecycle_fn)dlsym(h, "basic_module_init");
  lifecycle_fn fini = (lifecycle_fn)dlsym(h, "basic_module_fini");
  upper_fn upper = (upper_fn)dlsym(h, "BASIC_UPPER");
  if (!init || !fini || !upper) return 4;
  init();
  const char *input = "measure string wrapper";
  volatile size_t checksum = 0;

  uint64_t start = ns_now();
  for (size_t i = 0; i < count; i++) {
    char *s = upper(input);
    if (s == NULL) return 5;
    checksum += (unsigned char)s[0];
    free(s);
  }
  uint64_t wrapper_elapsed = ns_now() - start;

  size_t len = strlen(input) + 1;
  start = ns_now();
  for (size_t i = 0; i < count; i++) {
    char *s = malloc(len);
    if (s == NULL) return 6;
    memcpy(s, input, len);
    checksum += (unsigned char)s[0];
    free(s);
  }
  uint64_t malloc_elapsed = ns_now() - start;

  start = ns_now();
  for (size_t i = 0; i < count; i++) {
    char *s = malloc(len);
    if (s == NULL) return 7;
    for (size_t j = 0; j + 1 < len; j++) {
      unsigned char c = (unsigned char)input[j];
      s[j] = c >= 'a' && c <= 'z' ? (char)(c - 'a' + 'A') : (char)c;
    }
    s[len - 1] = '\0';
    checksum += (unsigned char)s[0];
    free(s);
  }
  uint64_t c_elapsed = ns_now() - start;
  fini();
  dlclose(h);
  printf("{\"iterations\":%zu,\"basic_upper_ns\":%.3f,\"malloc_copy_free_ns\":%.3f,\"c_upper_malloc_free_ns\":%.3f,\"checksum\":%zu}\n",
         count, (double)wrapper_elapsed / count, (double)malloc_elapsed / count,
         (double)c_elapsed / count, (size_t)checksum);
  return 0;
}
