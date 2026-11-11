#include <stdint.h>
#include <stdio.h>
#include <inttypes.h>
extern int64_t ext8(int64_t); extern int64_t uext32(int64_t);
extern float i2f(int64_t); extern double ui2d(int64_t);
extern int64_t f2i(float); extern int64_t d2i(double);
extern double f2d(float); extern float d2f(double);
extern int64_t addo(int64_t,int64_t); extern int64_t addos(int64_t,int64_t);
extern int64_t mulo(int64_t,int64_t); extern int64_t umulo(int64_t,int64_t);
int main(void){int bad=0;float f;double d;
  bad|=ext8(128)!=-128;bad|=uext32((int64_t)UINT32_C(0xf1234567))!=(int64_t)UINT32_C(0xf1234567);
  f=i2f(INT64_C(16777217));bad|=f!=16777216.0f;d=ui2d((int64_t)UINT64_C(0x8000000000000000));bad|=d!=9223372036854775808.0;
  bad|=f2i(-123.75f)!=-123;bad|=d2i(123.75)!=123;bad|=f2d(1.5f)!=1.5;bad|=d2f(1.5)!=1.5f;
  bad|=addo(INT64_MAX,1)!=1;bad|=addos(INT32_MAX,1)!=1;bad|=mulo(INT64_MAX,2)!=1;bad|=umulo((int64_t)UINT64_MAX,2)!=1;
  printf("cycle45_aot_checks=12 failures=%d\n",bad);return bad?1:0;
}
