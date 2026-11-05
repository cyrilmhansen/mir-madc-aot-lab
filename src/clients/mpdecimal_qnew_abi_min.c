#include <stddef.h>
#include <stdint.h>

typedef int64_t ssize_t_min;
typedef uint64_t size_t_min;
typedef struct {
  uint8_t flags;
  int64_t exp;
  int64_t digits;
  int64_t len;
  int64_t alloc;
  uint64_t *data;
} decimal_min;

extern int64_t min_alloc;
extern void *alloc_min(size_t_min count, size_t_min size);
extern void free_min(void *ptr);

decimal_min *qnew_size_min(ssize_t_min words) {
  decimal_min *result;

  words = words < min_alloc ? min_alloc : words;
  result = alloc_min(1, sizeof *result);
  if (result == NULL) return NULL;
  result->data = alloc_min((size_t_min)words, sizeof *result->data);
  if (result->data == NULL) {
    free_min(result);
    return NULL;
  }
  result->flags = 0;
  result->exp = 0;
  result->digits = 0;
  result->len = 0;
  result->alloc = words;
  return result;
}
