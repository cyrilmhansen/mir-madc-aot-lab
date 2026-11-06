#include "basic_num.h"

#include <stdio.h>
#include <string.h>

basic_num_t EXT_ADD(basic_num_t a, basic_num_t b) { return a + b; }
basic_num_t EXT_MIX(basic_num_t a, const char *s) { return a + strlen(s); }

static char echo_buf[128];
char *ext_echo(const char *s) __asm__("EXT_ECHO$");
char *ext_echo(const char *s) {
  snprintf(echo_buf, sizeof(echo_buf), "echo:%s", s);
  return echo_buf;
}

void EXT_PRINT(basic_num_t x) { printf("num:%.0f\n", x); }
void EXT_STR_PRINT(const char *s) { printf("str:%s\n", s); }
basic_num_t EXT_LATE(basic_num_t x) { return x + 7; }
void EXT_LATE_PROC(const char *s) { printf("late:%s\n", s); }
