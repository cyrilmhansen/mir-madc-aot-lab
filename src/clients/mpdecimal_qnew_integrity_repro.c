#include <stdio.h>

#include "mpdecimal.h"

int
main(void)
{
    mpd_t *value = mpd_qnew();
    if (value == NULL) {
        puts("mpd_qnew=NULL");
        return 2;
    }
    if (value->flags != 0 || value->exp != 0 || value->digits != 0 ||
        value->len != 0 || value->alloc < MPD_MINALLOC_MIN ||
        value->data == NULL) {
        puts("mpd_qnew=invalid-structure");
        mpd_del(value);
        return 3;
    }
    printf("mpd_qnew=valid flags=%u exp=%ld digits=%ld len=%ld alloc=%ld data=%s\n",
           (unsigned)value->flags, (long)value->exp, (long)value->digits,
           (long)value->len, (long)value->alloc,
           value->data == NULL ? "NULL" : "non-NULL");
    mpd_del(value);
    return 0;
}
