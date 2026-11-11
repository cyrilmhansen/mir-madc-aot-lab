#include <stdint.h>
#include <stdio.h>
#include <limits.h>
#include <string.h>
extern int64_t cvbr_0(int64_t),cvbr_1(int64_t),cvbr_2(int64_t),cvbr_3(int64_t);
extern int64_t ovbr_0(int64_t,int64_t),ovbr_1(int64_t,int64_t);
extern int64_t memcv_0(void*),memcv_1(void*),loopmem_0(void*,int64_t),loopmem_1(void*,int64_t);
extern int64_t callcv_0(int64_t,double),callcv_1(int64_t,double),callcv_2(int64_t,double),ovcall_0(int64_t,int64_t),ovcall_1(int64_t,int64_t),ovcall_2(int64_t,int64_t);
int main(void){int bad=0,n=0;uint8_t b[24];int64_t x;
#define T(c) do{if(!(c)){printf("failed line %d\n",__LINE__);bad++;}n++;}while(0)
 T(cvbr_0(128)==20);T(cvbr_1(255)==11);
 T(ovbr_0(INT64_MAX,1)==100);T(ovbr_1(INT64_MIN,1)==101);
 memset(b,0xa5,sizeof b);b[0]=0x80;x=memcv_0(b);memcpy(&x,b+8,8);T(x==-127);
 memset(b,0xa5,sizeof b);b[0]=0xff;x=memcv_1(b);memcpy(&x,b+8,8);T(x==257);
 b[0]=0xff;b[1]=0x7f;T(loopmem_0(b,2)==126);b[0]=0xff;b[1]=0x80;T(loopmem_1(b,2)==383);
 T(callcv_0(5,2.5)==26);T(callcv_1(5,-3.75)==19);
 T(ovcall_0(INT64_MAX,1)==100);T(ovcall_1(1,2)==4);
 T(cvbr_2(0)==22);T(cvbr_3(128)==13);
 T(callcv_2(-4,8.9)==21);T(ovcall_2(INT64_MAX,1)==102);
 printf("composite_native_calls=%d failures=%d\n",n,bad);return bad?1:0;}
