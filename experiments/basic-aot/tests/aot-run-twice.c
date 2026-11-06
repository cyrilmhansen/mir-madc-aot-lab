#include <stdint.h>

extern int64_t basic_program_main(void);

int main(void) {
  if (basic_program_main() != 0) return 1;
  if (basic_program_main() != 0) return 2;
  return 0;
}
