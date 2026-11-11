/* Independent C ABI client for selected Cycle43 MIR object exports. */
#include <stdint.h>
#include <stdio.h>
#include <string.h>

extern int64_t cfg_diamond(int64_t, int64_t);
extern int64_t mem_store_reload64(void *, int64_t, int64_t);

int main(void) {
  _Alignas(16) unsigned char data[32];
  int64_t got;
  memset(data, 0xA5, sizeof data);
  if (cfg_diamond(-3, 0) != 3 || cfg_diamond(2, 0) != 12) return 2;
  got = mem_store_reload64(data + 8, INT64_C(0x1122334455667788), 0);
  if (got != INT64_C(0x1122334455667788)) return 3;
  if (data[7] != 0xA5 || data[16] != 0xA5) return 4;
  puts("AOT ABI outputs and surrounding bytes verified");
  return 0;
}
