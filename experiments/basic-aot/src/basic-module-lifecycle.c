#include "basic_pool.h"

#include <stddef.h>

#define BASIC_MODULE_POOL_BYTES (1024U * 1024U)

extern void basic_runtime_fini(void);

static int initialized;

/* Shared BASIC modules have no implicit constructor. Clients opt into the
   BASIC runtime state only when calling exported functions that need it. */
void basic_module_init(void) {
  if (!initialized) {
    basic_pool_init(BASIC_MODULE_POOL_BYTES);
    initialized = 1;
  }
}

void basic_module_fini(void) {
  if (initialized) {
    basic_runtime_fini();
    initialized = 0;
  }
}
