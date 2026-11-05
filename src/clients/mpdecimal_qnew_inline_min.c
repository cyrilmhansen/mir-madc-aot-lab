#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>

typedef struct {
  uint8_t flags;
  int64_t exp;
  int64_t digits;
  int64_t len;
  int64_t alloc;
  uint64_t *data;
} decimal_min;

static int64_t min_alloc = 2;

static inline size_t mul_overflow_min(size_t a, size_t b, size_t *overflow) {
  __uint128_t product = (__uint128_t)a * (__uint128_t)b;
  *overflow = (size_t)(product >> 64);
  return (size_t)product;
}

static inline void *alloc_min(size_t count, size_t size) {
  size_t req, overflow;
  req = mul_overflow_min(count, size, &overflow);
  if (overflow) return NULL;
  return malloc(req);
}

static decimal_min *qnew_size_min(int64_t words) {
  decimal_min *result;

  words = words < min_alloc ? min_alloc : words;
  result = alloc_min(1, sizeof *result);
  if (result == NULL) return NULL;
  result->data = alloc_min((size_t)words, sizeof *result->data);
  if (result->data == NULL) {
    free(result);
    return NULL;
  }
  result->flags = 0;
  result->exp = 0;
  result->digits = 0;
  result->len = 0;
  result->alloc = words;
  return result;
}

int main(void) {
  decimal_min *result = qnew_size_min(2);
  if (result == NULL) return 2;
  free(result->data);
  free(result);
  return 0;
}
