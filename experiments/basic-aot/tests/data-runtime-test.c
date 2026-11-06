#include "basic_num.h"

#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

extern void basic_data_init(void);
extern void basic_data_add_num(basic_num_t);
extern void basic_data_add_str(const char *);
extern void basic_data_fini(void);
extern void basic_restore(void);
extern basic_num_t basic_read(void);
extern char *basic_read_str(void);
extern void basic_free(char *);
extern void *basic_data_items;
extern size_t basic_data_len;
extern size_t basic_data_pos;

int main(void) {
  char source[] = "owned copy";
  basic_data_init();
  if (basic_data_items != NULL || basic_data_len != 0 || basic_data_pos != 0) return 1;
  basic_data_add_num(12.5);
  basic_data_add_str(source);
  source[0] = 'X';
  if (basic_data_items == NULL || basic_data_len != 2 || basic_data_pos != 0) return 2;
  if (basic_read() != 12.5 || basic_data_pos != 1) return 3;
  char *text = basic_read_str();
  if (text == NULL || strcmp(text, "owned copy") != 0 || basic_data_pos != 2) return 4;
  basic_free(text);
  basic_restore();
  if (basic_data_pos != 0 || basic_read() != 12.5) return 5;
  basic_data_fini();
  if (basic_data_items != NULL || basic_data_len != 0 || basic_data_pos != 0) return 6;
  basic_data_init();
  if (basic_data_items != NULL || basic_data_len != 0 || basic_data_pos != 0) return 7;
  basic_data_fini();
  puts("PASS: runtime DATA ownership, reads, RESTORE and reset");
  return 0;
}
