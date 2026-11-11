#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <limits.h>
#include <string.h>
int main(int argc,char**argv){if(argc!=2)return 2;void*h=dlopen(argv[1],RTLD_NOW|RTLD_LOCAL);if(!h){fprintf(stderr,"dlopen: %s\n",dlerror());return 3;}int bad=0,n=0;
  typedef int64_t(*f1_t)(int64_t);typedef int64_t(*f2_t)(int64_t,int64_t);typedef int64_t(*mem_t)(void*);typedef int64_t(*loop_t)(void*,int64_t);typedef int64_t(*mix_t)(int64_t,double);
  f1_t cvbr_0=(f1_t)dlsym(h,"cvbr_0"),cvbr_1=(f1_t)dlsym(h,"cvbr_1");f2_t ovbr_0=(f2_t)dlsym(h,"ovbr_0");mem_t memcv_0=(mem_t)dlsym(h,"memcv_0");loop_t loopmem_1=(loop_t)dlsym(h,"loopmem_1");mix_t callcv_1=(mix_t)dlsym(h,"callcv_1"),callcv_0=(mix_t)dlsym(h,"callcv_0");f2_t ovcall_0=(f2_t)dlsym(h,"ovcall_0");
  if(!cvbr_0||!cvbr_1||!ovbr_0||!memcv_0||!loopmem_1||!callcv_1||!callcv_0||!ovcall_0){fprintf(stderr,"dlsym failed: %s\n",dlerror());bad++;}
  if(!bad){uint8_t b[24];int64_t x;bad|=cvbr_0(128)!=20;n++;bad|=cvbr_1(255)!=11;n++;bad|=ovbr_0(INT64_MAX,1)!=100;n++;memset(b,0xa5,sizeof b);b[0]=0x80;memcv_0(b);memcpy(&x,b+8,8);bad|=x!=-127;n++;b[0]=0xff;b[1]=0x80;bad|=loopmem_1(b,2)!=383;n++;bad|=callcv_1(5,-3.75)!=19;n++;bad|=callcv_0(5,2.5)!=26;n++;bad|=ovcall_0(INT64_MAX,1)!=100;n++;}
  printf("composite_dlopen_checks=%d failures=%d\n",n,bad);if(dlclose(h)!=0)bad++;return bad?1:0;}
