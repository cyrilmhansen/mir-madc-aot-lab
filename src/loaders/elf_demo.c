#include "elf_exports.c"

int main(void) {
    return (lab_add(20, 22) == 42 && lab_scale(7) == 42
            && lab_global_multiplier == 6) ? 0 : 1;
}
