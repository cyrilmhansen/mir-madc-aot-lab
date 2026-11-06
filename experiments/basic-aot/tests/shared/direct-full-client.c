#include "basic-shared-api.h"

#include <math.h>
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

extern double SQUARE(double);
extern double ADD(double, double);
extern double STRLEN(const char *);
extern void REPORT(double);

typedef double (*strlen_fn)(const char *);
typedef void (*report_fn)(double);

int main(void) {
  if (fabs(SQUARE(-0.125) - 0.015625) > 1e-14
      || fabs(ADD(1.25, 2.0) - 3.25) > 1e-14) return 1;
  strlen_fn str_len = (strlen_fn)dlsym(RTLD_DEFAULT, "STRLEN");
  report_fn report = (report_fn)dlsym(RTLD_DEFAULT, "REPORT");
  if (str_len == NULL || report == NULL || fabs(str_len("BASIC") - 5.0) > 1e-14) return 2;
  basic_module_init();
  char *u = BASIC_UPPER("bonjour");
  char *l = BASIC_LITERAL("x");
  char *e = BASIC_ECHO("echo");
  char *v = BASIC_LOCAL("local");
  char *c = BASIC_CONCAT("con", "cat");
  char *z = BASIC_EMPTY("x");
  char *b = BASIC_BORROWED("borrowed");
  if (!u || strcmp(u, "BONJOUR") || !l || strcmp(l, "literal") || !e || strcmp(e, "echo")
      || !v || strcmp(v, "LOCAL") || !c || strcmp(c, "concat") || !z || strcmp(z, "")
      || !b || strcmp(b, "borrowed")) return 3;
  report(7.5);
  basic_module_fini();
  if (strcmp(u, "BONJOUR")) return 4;
  free(c); free(b); free(u); free(z); free(e); free(v); free(l);
  puts("PASS: direct MIR complete C ABI");
  return 0;
}
