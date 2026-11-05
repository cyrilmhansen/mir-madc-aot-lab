extern int arm_shared_scale;
int arm_bonus(int value);

int arm_calculate(int value) {
    return arm_bonus(value) * arm_shared_scale;
}
