#include <math.h>
#include <stdio.h>

extern double SQUARE(double);
extern double ADD(double, double);

int main(void) {
  const double values[] = {0.0, 2.5, -3.0, -0.125, 1234.5};
  for (size_t i = 0; i < sizeof(values) / sizeof(values[0]); i++)
    if (fabs(SQUARE(values[i]) - values[i] * values[i]) > 1e-12) return 1;
  if (fabs(ADD(-1.25, 4.5) - 3.25) > 1e-12
      || fabs(ADD(-2.0, -3.5) + 5.5) > 1e-12) return 2;
  puts("PASS: direct MIR SQUARE/ADD linked from C");
  return 0;
}
