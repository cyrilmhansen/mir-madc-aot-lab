/* Isolated parser error-path probe. Parent process owns timeout/isolation. */
#include "mir.h"
#include <stdio.h>
int main(int argc,char **argv){if(argc!=2)return 2;MIR_context_t c=MIR_init();MIR_scan_string(c,argv[1]);MIR_finish(c);puts("accepted");return 0;}
