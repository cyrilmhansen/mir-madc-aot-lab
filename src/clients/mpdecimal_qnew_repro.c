#include <stdio.h>

#include "mpdecimal.h"

int main(void) {
  mpd_t *value = mpd_qnew();
  printf("mpd_qnew=%s\n", value == NULL ? "NULL" : "non-NULL");
  if (value == NULL) {
    return 2;
  }
  mpd_del(value);
  return 0;
}
