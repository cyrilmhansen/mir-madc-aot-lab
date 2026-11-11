/* Fresh-process executor for the Cycle45 bounded reducer's generated MIR text. */
#include "mir.h"
#include "mir-gen.h"
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main(int argc,char **argv){FILE*f;long n;char*s;MIR_context_t c;MIR_module_t m;MIR_item_t it=NULL,x;MIR_val_t a[2],r[1];int64_t v0,v1=0;if(argc<3||argc>4)return 2;v0=strtoll(argv[2],NULL,0);if(argc==4)v1=strtoll(argv[3],NULL,0);f=fopen(argv[1],"rb");if(!f)return 3;if(fseek(f,0,SEEK_END)||(n=ftell(f))<0||fseek(f,0,SEEK_SET))return 4;s=malloc((size_t)n+1);if(!s)return 5;if(fread(s,1,(size_t)n,f)!=(size_t)n)return 6;fclose(f);s[n]=0;c=MIR_init();MIR_scan_string(c,s);free(s);for(m=DLIST_HEAD(MIR_module_t,*MIR_get_module_list(c));m;m=DLIST_NEXT(MIR_module_t,m))for(x=DLIST_HEAD(MIR_item_t,m->items);x;x=DLIST_NEXT(MIR_item_t,x))if(x->item_type==MIR_func_item&&!strcmp(MIR_item_name(c,x),"reduce_case"))it=x;if(!it)return 7;for(m=DLIST_HEAD(MIR_module_t,*MIR_get_module_list(c));m;m=DLIST_NEXT(MIR_module_t,m))MIR_load_module(c,m);a[0].i=v0;a[1].i=v1;MIR_interp_arr(c,it,r,it->u.func->nargs,a);printf("interp=%" PRId64 "\n",r[0].i);MIR_gen_init(c);MIR_link(c,MIR_set_gen_interface,NULL);if(it->u.func->nargs==1){typedef int64_t(*fn)(int64_t);printf("jit=%" PRId64 "\n",((fn)MIR_gen(c,it))(v0));}else{typedef int64_t(*fn)(int64_t,int64_t);printf("jit=%" PRId64 "\n",((fn)MIR_gen(c,it))(v0,v1));}MIR_gen_finish(c);MIR_finish(c);return 0;}
