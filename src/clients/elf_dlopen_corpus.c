#define _GNU_SOURCE
#include <dlfcn.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <sys/resource.h>

static uint64_t now_ns(void) {
  struct timespec ts;
  clock_gettime(CLOCK_MONOTONIC, &ts);
  return (uint64_t)ts.tv_sec * 1000000000ULL + (uint64_t)ts.tv_nsec;
}

int main(int argc, char **argv) {
  if (argc != 3) return 2;
  const char *path = argv[1];
  size_t count = strtoul(argv[2], NULL, 10);
  uint64_t t = now_ns();
  void *handle = dlopen(path, RTLD_NOW | RTLD_LOCAL);
  uint64_t open_ns = now_ns() - t;
  if (!handle) { fprintf(stderr, "dlopen: %s\n", dlerror()); return 3; }
  uint64_t resolve_start = now_ns(), first_ns = 0;
  size_t calls = 0;
  int64_t checksum = 0;
  for (size_t i = 0; i < count; i++) {
    char name[32];
    snprintf(name, sizeof name, "bench_%05zu", i);
    dlerror();
    int64_t (*fn)(int64_t) = (int64_t (*)(int64_t))dlsym(handle, name);
    const char *error = dlerror();
    if (error || !fn) { fprintf(stderr, "dlsym %s: %s\n", name, error ? error : "missing"); return 4; }
    int64_t x = 17;
    int64_t expected = x * (int64_t)(i + 3) + (int64_t)(i * i);
    if (i == 0) t = now_ns();
    int64_t got = fn(x);
    if (i == 0) first_ns = now_ns() - t;
    if (got != expected) { fprintf(stderr, "%s returned %" PRId64 ", expected %" PRId64 "\n", name, got, expected); return 5; }
    checksum += got;
    calls++;
  }
  uint64_t resolve_call_ns = now_ns() - resolve_start;
  struct rusage usage;
  getrusage(RUSAGE_SELF, &usage);
  t = now_ns();
  if (dlclose(handle) != 0) { fprintf(stderr, "dlclose: %s\n", dlerror()); return 6; }
  uint64_t close_ns = now_ns() - t;
  printf("{\"scenario\":\"elf_shared_dlopen\",\"functions\":%zu,\"dlopen_ns\":%" PRIu64
         ",\"resolve_and_call_ns\":%" PRIu64 ",\"first_call_ns\":%" PRIu64
         ",\"dlclose_ns\":%" PRIu64 ",\"verified_calls\":%zu,"
         "\"result_checksum\":%" PRId64 ",\"minor_faults\":%ld,"
         "\"major_faults\":%ld,\"maxrss_kib\":%ld}\n",
         count, open_ns, resolve_call_ns, first_ns, close_ns, calls,
         checksum, usage.ru_minflt, usage.ru_majflt, usage.ru_maxrss);
  return 0;
}
