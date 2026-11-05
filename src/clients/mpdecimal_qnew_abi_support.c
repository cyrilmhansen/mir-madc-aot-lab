#include <stdint.h>
#include <stdlib.h>

typedef uint64_t size_t_min;
typedef struct decimal_min {
  uint8_t flags;
  int64_t exp;
  int64_t digits;
  int64_t len;
  int64_t alloc;
  uint64_t *data;
} decimal_min;

int64_t min_alloc = 2;
void *alloc_min(size_t_min count, size_t_min size) {
  if (count != 0 && size > (size_t_min)-1 / count) return NULL;
  return malloc((size_t)(count * size));
}
void free_min(void *ptr) { free(ptr); }

extern decimal_min *qnew_size_min(int64_t words);

int main(void) {
  decimal_min *value = qnew_size_min(2);
  if (value == NULL) return 2;
  free(value->data);
  free(value);
  return 0;
}
