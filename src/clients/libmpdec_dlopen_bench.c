#define _POSIX_C_SOURCE 200809L
#include <dlfcn.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "mpdecimal.h"

typedef void (*defaultcontext_fn)(mpd_context_t *);
typedef mpd_t *(*qnew_fn)(void);
typedef void (*del_fn)(mpd_t *);
typedef void (*set_string_fn)(mpd_t *, const char *, const mpd_context_t *, uint32_t *);
typedef void (*mul_fn)(mpd_t *, const mpd_t *, const mpd_t *, const mpd_context_t *, uint32_t *);
typedef char *(*to_sci_fn)(const mpd_t *, int);

static uint64_t
nanoseconds(struct timespec start, struct timespec end)
{
    return (uint64_t)(end.tv_sec - start.tv_sec) * UINT64_C(1000000000) +
           (uint64_t)(end.tv_nsec - start.tv_nsec);
}

#define LOAD_SYMBOL(handle, name, type) \
    type name = (type)dlsym(handle, #name); \
    if (name == NULL) { fprintf(stderr, "dlsym %s: %s\n", #name, dlerror()); return 2; }

int
main(int argc, char **argv)
{
    if (argc != 2 && argc != 3) {
        fprintf(stderr, "usage: %s /path/to/libmpdec.so [madc-runtime.so]\n", argv[0]);
        return 2;
    }

    void *runtime_handle = NULL;
    if (argc == 3) {
        runtime_handle = dlopen(argv[2], RTLD_NOW | RTLD_GLOBAL);
        if (runtime_handle == NULL) {
            fprintf(stderr, "dlopen runtime: %s\n", dlerror());
            return 2;
        }
    }

    struct timespec load_start, load_end, op_start, op_end;
    if (clock_gettime(CLOCK_MONOTONIC, &load_start) != 0)
        return 2;
    void *handle = dlopen(argv[1], RTLD_NOW | RTLD_LOCAL);
    if (handle == NULL) {
        fprintf(stderr, "dlopen: %s\n", dlerror());
        return 2;
    }
    if (clock_gettime(CLOCK_MONOTONIC, &load_end) != 0)
        return 2;

    LOAD_SYMBOL(handle, mpd_defaultcontext, defaultcontext_fn);
    LOAD_SYMBOL(handle, mpd_qnew, qnew_fn);
    LOAD_SYMBOL(handle, mpd_del, del_fn);
    LOAD_SYMBOL(handle, mpd_qset_string, set_string_fn);
    LOAD_SYMBOL(handle, mpd_qmul, mul_fn);
    LOAD_SYMBOL(handle, mpd_to_sci, to_sci_fn);

    mpd_context_t ctx;
    mpd_defaultcontext(&ctx);
    ctx.prec = 40;
    uint32_t status = 0;
    mpd_t *a = mpd_qnew();
    mpd_t *b = mpd_qnew();
    mpd_t *result = mpd_qnew();
    if (a == NULL || b == NULL || result == NULL) {
        fprintf(stderr, "mpd_qnew failed\n");
        return 3;
    }

    if (clock_gettime(CLOCK_MONOTONIC, &op_start) != 0)
        return 2;
    mpd_qset_string(a, "123456789", &ctx, &status);
    mpd_qset_string(b, "987654321", &ctx, &status);
    mpd_qmul(result, a, b, &ctx, &status);
    char *text = mpd_to_sci(result, 1);
    if (clock_gettime(CLOCK_MONOTONIC, &op_end) != 0)
        return 2;
    if (status != 0 || text == NULL || strcmp(text, "121932631112635269") != 0) {
        fprintf(stderr, "decimal result mismatch: %s (status=%" PRIu32 ")\n",
                text == NULL ? "NULL" : text, status);
        return 1;
    }

    printf("load_ns=%" PRIu64 " operation_ns=%" PRIu64 " result=%s\n",
           nanoseconds(load_start, load_end), nanoseconds(op_start, op_end), text);
    free(text);
    mpd_del(result);
    mpd_del(b);
    mpd_del(a);
    dlclose(handle);
    if (runtime_handle != NULL)
        dlclose(runtime_handle);
    return 0;
}
