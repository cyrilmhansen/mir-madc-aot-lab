extern int lab_add(int, int);
extern int lab_scale(int);

int main(void) {
    return (lab_add(20, 22) == 42 && lab_scale(7) == 42) ? 0 : 1;
}
