#include <stdint.h>
#include <stdio.h>

static inline uint64_t
mul_high_u64(uint64_t a, uint64_t b)
{
    uint64_t high, low;
    __asm__("mulq %3"
            : "=d" (high), "=a" (low)
            : "%a" (a), "rm" (b)
            : "cc");
    (void)low;
    return high;
}

int
main(void)
{
    uint64_t high = mul_high_u64(1, 48);
    if (high != 0) {
        printf("high=%llu\n", (unsigned long long)high);
        return 1;
    }
    puts("high=0");
    return 0;
}
