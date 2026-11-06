#include <stdio.h>
#include <stdlib.h>

#include "mpdecimal.h"

static size_t allocation_sizes[2];
static size_t allocation_count;
static size_t free_count;

static void *
recording_malloc(size_t size)
{
    if (allocation_count < sizeof allocation_sizes / sizeof allocation_sizes[0])
        allocation_sizes[allocation_count] = size;
    allocation_count++;
    return malloc(size);
}

static void
recording_free(void *ptr)
{
    free_count++;
    free(ptr);
}

int
main(void)
{
    mpd_mallocfunc = recording_malloc;
    mpd_free = recording_free;
    mpd_t *value = mpd_qnew();
    if (value == NULL) {
        puts("mpd_qnew=NULL");
        return 2;
    }
    if (value->flags != 0 || value->exp != 0 || value->digits != 0 ||
        value->len != 0 || value->alloc < MPD_MINALLOC_MIN ||
        value->data == NULL || allocation_count != 2 ||
        allocation_sizes[0] != sizeof *value ||
        allocation_sizes[1] != (size_t)value->alloc * sizeof *value->data) {
        puts("mpd_qnew=invalid-structure");
        mpd_del(value);
        return 3;
    }
    /* qnew intentionally leaves coefficient storage uninitialized. Write and
       read every allocated word so the probe never reads indeterminate data. */
    for (mpd_ssize_t i = 0; i < value->alloc; i++)
        value->data[i] = (mpd_uint_t)i;
    for (mpd_ssize_t i = 0; i < value->alloc; i++) {
        if (value->data[i] != (mpd_uint_t)i) {
            puts("mpd_qnew=data-corruption");
            mpd_del(value);
            return 4;
        }
    }
    printf("mpd_qnew=valid flags=%u exp=%ld digits=%ld len=%ld alloc=%ld data=%s\n",
           (unsigned)value->flags, (long)value->exp, (long)value->digits,
           (long)value->len, (long)value->alloc,
           value->data == NULL ? "NULL" : "non-NULL");
    mpd_del(value);
    if (free_count != 2) {
        puts("mpd_qnew=free-count-mismatch");
        return 5;
    }
    return 0;
}
