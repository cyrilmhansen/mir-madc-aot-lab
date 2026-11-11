#include "mir.h"
#include "mir-gen.h"
#include <stdio.h>
#include <stdlib.h>
int main(int argc,char**argv){FILE*f;long n;char*s;MIR_context_t c;MIR_module_t m;if(argc!=2)return 2;f=fopen(argv[1],"rb");if(!f)return 3;fseek(f,0,SEEK_END);n=ftell(f);fseek(f,0,SEEK_SET);s=malloc((size_t)n+1);if(!s)return 4;fread(s,1,(size_t)n,f);fclose(f);s[n]=0;c=MIR_init();MIR_scan_string(c,s);free(s);for(m=DLIST_HEAD(MIR_module_t,*MIR_get_module_list(c));m;m=DLIST_NEXT(MIR_module_t,m))MIR_load_module(c,m);MIR_gen_init(c);MIR_link(c,MIR_set_gen_interface,NULL);puts("accepted by load and link");MIR_gen_finish(c);MIR_finish(c);return 0;}
