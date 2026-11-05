#include <dlfcn.h>
#if defined(__APPLE__)
#include <mach-o/dyld.h>
#endif
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <time.h>

typedef int (*binary_fn)(int, int);
typedef int (*unary_fn)(int);

static unsigned long long now_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (unsigned long long)ts.tv_sec * 1000000000ULL + ts.tv_nsec;
}

static long long timeval_us(struct timeval tv) {
    return (long long)tv.tv_sec * 1000000LL + tv.tv_usec;
}

static int image_loaded(const char *basename) {
#if defined(__APPLE__)
    uint32_t i;
    for (i = 0; i < _dyld_image_count(); i++) {
        const char *name = _dyld_get_image_name(i);
        const char *slash = name ? strrchr(name, '/') : NULL;
        if (name && strcmp(slash ? slash + 1 : name, basename) == 0) return 1;
    }
    return 0;
#elif defined(__linux__)
    void *handle = dlopen(basename, RTLD_NOLOAD | RTLD_NOW);
    if (handle) {
        dlclose(handle);
        return 1;
    }
    return 0;
#else
    (void)basename;
    return -1;
#endif
}

int main(int argc, char **argv) {
    int cycles = 1, cycle;
    const char *path;
    const char *basename;
    if (argc != 2 && argc != 4) return 2;
    path = argv[1];
    if (argc == 4 && strcmp(argv[2], "-n") == 0) cycles = atoi(argv[3]);
    if (cycles < 1) return 2;
    basename = strrchr(path, '/');
    basename = basename ? basename + 1 : path;
#if defined(__linux__)
    basename = path;
#endif
    puts("cycle,compute_calls,open_ns,dlsym_ns,first_call_ns,compute_ns,close_ns,loaded_before,loaded_after_close,runtime_loaded_after_close,user_cpu_us,system_cpu_us,minor_faults,major_faults,maxrss_native_units");
    for (cycle = 1; cycle <= cycles; cycle++) {
        void *handle;
        binary_fn add;
        unary_fn scale;
        int before = image_loaded(basename);
        unsigned long long t0 = now_ns();
        unsigned long long t1, t2, t3, t4, t5, t6;
        int add_result, scale_result, i;
        volatile long long checksum = 0;
        const int compute_iterations = 10000;
        struct rusage usage_before, usage_after;
        getrusage(RUSAGE_SELF, &usage_before);
        handle = dlopen(path, RTLD_NOW | RTLD_LOCAL);
        t1 = now_ns();
        if (!handle) {
            fprintf(stderr, "dlopen: %s\n", dlerror());
            return 3;
        }
        *(void **)(&add) = dlsym(handle, "lab_add");
        *(void **)(&scale) = dlsym(handle, "lab_scale");
        t2 = now_ns();
        if (!add || !scale) {
            fprintf(stderr, "dlsym: %s\n", dlerror());
            dlclose(handle);
            return 4;
        }
        t3 = now_ns();
        add_result = add(20, 22);
        t4 = now_ns();
        scale_result = scale(7);
        for (i = 0; i < compute_iterations; i++)
            checksum += add(i, 1) + scale(i % 100);
        t5 = now_ns();
        if (add_result != 42 || scale_result != 42 || checksum <= 0) {
            fprintf(stderr, "wrong result: add=%d scale=%d\n", add_result, scale_result);
            dlclose(handle);
            return 5;
        }
        if (dlclose(handle) != 0) return 6;
        t6 = now_ns();
        getrusage(RUSAGE_SELF, &usage_after);
        printf("%d,%d,%llu,%llu,%llu,%llu,%llu,%d,%d,%d,%lld,%lld,%ld,%ld,%ld\n", cycle,
               compute_iterations * 2,
               t1 - t0, t2 - t1, t4 - t3, t5 - t4, t6 - t5,
               before, image_loaded(basename),
#if defined(__APPLE__)
               image_loaded("libmadc-0.dylib"),
#else
               image_loaded("libmadc.so.0"),
#endif
               timeval_us(usage_after.ru_utime) - timeval_us(usage_before.ru_utime),
               timeval_us(usage_after.ru_stime) - timeval_us(usage_before.ru_stime),
               usage_after.ru_minflt - usage_before.ru_minflt,
               usage_after.ru_majflt - usage_before.ru_majflt,
               usage_after.ru_maxrss);
    }
    return 0;
}
