#include "basic-shared-api.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(void) {
  basic_module_init();
  char *s = BASIC_UPPER("bonjour");
  if (s == NULL || strcmp(s, "BONJOUR")) return 1;
  free(s);
  basic_module_fini();
  puts("PASS: direct link string wrapper");
  return 0;
}
