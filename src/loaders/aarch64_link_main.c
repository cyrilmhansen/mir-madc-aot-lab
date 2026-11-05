extern int arm_calculate(int value);

int main(void) {
    return arm_calculate(5) == 42 ? 0 : 1;
}
