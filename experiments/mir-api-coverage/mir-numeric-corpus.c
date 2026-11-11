/* Cycle45 bounded numerical boundary corpus; direct MIR public API only. */
#include "mir.h"
#include "mir-gen.h"
#include <inttypes.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct { const char *name; MIR_insn_code_t code; MIR_type_t in, out; int kind; } Cvt;
static const Cvt cvts[] = {
  {"ext8",MIR_EXT8,MIR_T_I64,MIR_T_I64,0},{"ext16",MIR_EXT16,MIR_T_I64,MIR_T_I64,1},
  {"ext32",MIR_EXT32,MIR_T_I64,MIR_T_I64,2},{"uext8",MIR_UEXT8,MIR_T_I64,MIR_T_I64,3},
  {"uext16",MIR_UEXT16,MIR_T_I64,MIR_T_I64,4},{"uext32",MIR_UEXT32,MIR_T_I64,MIR_T_I64,5},
  {"i2f",MIR_I2F,MIR_T_I64,MIR_T_F,6},{"ui2f",MIR_UI2F,MIR_T_I64,MIR_T_F,7},
  {"i2d",MIR_I2D,MIR_T_I64,MIR_T_D,8},{"ui2d",MIR_UI2D,MIR_T_I64,MIR_T_D,9},
  {"f2i",MIR_F2I,MIR_T_F,MIR_T_I64,10},{"d2i",MIR_D2I,MIR_T_D,MIR_T_I64,11},
  {"f2d",MIR_F2D,MIR_T_F,MIR_T_D,12},{"d2f",MIR_D2F,MIR_T_D,MIR_T_F,13}
};
typedef struct { const char *name; MIR_insn_code_t code, branch; int bits, uns; } Ov;
static const Ov ovs[] = {
  {"addo",MIR_ADDO,MIR_BO,64,0},{"addos",MIR_ADDOS,MIR_BO,32,0},
  {"subo",MIR_SUBO,MIR_BO,64,0},{"subos",MIR_SUBOS,MIR_BO,32,0},
  {"mulo",MIR_MULO,MIR_BO,64,0},{"mulos",MIR_MULOS,MIR_BO,32,0},
  {"umulo",MIR_UMULO,MIR_UBO,64,1},{"umulos",MIR_UMULOS,MIR_UBO,32,1}
};
static MIR_context_t ctx;
static void app(MIR_item_t f, MIR_insn_t i) { MIR_append_insn(ctx,f,i); }
static MIR_item_t findf(const char *n) { MIR_module_t m; MIR_item_t i; for(m=DLIST_HEAD(MIR_module_t,*MIR_get_module_list(ctx));m;m=DLIST_NEXT(MIR_module_t,m)) for(i=DLIST_HEAD(MIR_item_t,m->items);i;i=DLIST_NEXT(MIR_item_t,i)) if(i->item_type==MIR_func_item&&!strcmp(MIR_item_name(ctx,i),n))return i; return NULL; }
static void func_cvt(const Cvt *c) {
  MIR_type_t rt=c->out; MIR_item_t f=MIR_new_func(ctx,c->name,1,&rt,1,c->in,"x");
  MIR_reg_t x=MIR_reg(ctx,"x",f->u.func), r=MIR_new_func_reg(ctx,f->u.func,c->out,"r");
  app(f,MIR_new_insn(ctx,c->code,MIR_new_reg_op(ctx,r),MIR_new_reg_op(ctx,x)));
  app(f,MIR_new_ret_insn(ctx,1,MIR_new_reg_op(ctx,r))); MIR_finish_func(ctx);
}
static void func_ov(const Ov *o) {
  MIR_type_t rt=MIR_T_I64; MIR_item_t f=MIR_new_func(ctx,o->name,1,&rt,2,MIR_T_I64,"a",MIR_T_I64,"b");
  MIR_reg_t a=MIR_reg(ctx,"a",f->u.func),b=MIR_reg(ctx,"b",f->u.func),v=MIR_new_func_reg(ctx,f->u.func,MIR_T_I64,"v"),r=MIR_new_func_reg(ctx,f->u.func,MIR_T_I64,"r");
  MIR_label_t hit=MIR_new_label(ctx),done=MIR_new_label(ctx);
  app(f,MIR_new_insn(ctx,o->code,MIR_new_reg_op(ctx,v),MIR_new_reg_op(ctx,a),MIR_new_reg_op(ctx,b)));
  app(f,MIR_new_insn(ctx,o->branch,MIR_new_label_op(ctx,hit)));
  app(f,MIR_new_insn(ctx,MIR_MOV,MIR_new_reg_op(ctx,r),MIR_new_int_op(ctx,0)));
  app(f,MIR_new_insn(ctx,MIR_JMP,MIR_new_label_op(ctx,done)));
  app(f,hit); app(f,MIR_new_insn(ctx,MIR_MOV,MIR_new_reg_op(ctx,r),MIR_new_int_op(ctx,1)));
  app(f,done); app(f,MIR_new_ret_insn(ctx,1,MIR_new_reg_op(ctx,r))); MIR_finish_func(ctx);
}
static void func_ov_result(const Ov *o) {
  char name[48]; MIR_type_t rt=MIR_T_I64; snprintf(name,sizeof name,"result_%s",o->name);
  MIR_item_t f=MIR_new_func(ctx,name,1,&rt,2,MIR_T_I64,"a",MIR_T_I64,"b");
  MIR_reg_t a=MIR_reg(ctx,"a",f->u.func),b=MIR_reg(ctx,"b",f->u.func),v=MIR_new_func_reg(ctx,f->u.func,MIR_T_I64,"v");
  app(f,MIR_new_insn(ctx,o->code,MIR_new_reg_op(ctx,v),MIR_new_reg_op(ctx,a),MIR_new_reg_op(ctx,b)));
  app(f,MIR_new_ret_insn(ctx,1,MIR_new_reg_op(ctx,v))); MIR_finish_func(ctx);
}
static MIR_context_t build(void) { size_t i; MIR_module_t m; MIR_item_t it;ctx=MIR_init(); MIR_new_module(ctx,"cycle45_numeric"); for(i=0;i<sizeof(cvts)/sizeof(cvts[0]);i++)func_cvt(&cvts[i]);for(i=0;i<sizeof(ovs)/sizeof(ovs[0]);i++){func_ov(&ovs[i]);func_ov_result(&ovs[i]);}for(m=DLIST_HEAD(MIR_module_t,*MIR_get_module_list(ctx));m;m=DLIST_NEXT(MIR_module_t,m))for(it=DLIST_HEAD(MIR_item_t,m->items);it;it=DLIST_NEXT(MIR_item_t,it))if(it->item_type==MIR_func_item)MIR_new_export(ctx,MIR_item_name(ctx,it));MIR_finish_module(ctx);return ctx; }
static int emit_object(const char *path) { MIR_module_t m; MIR_item_t it; void *buf=NULL; size_t n=0; FILE*f; for(m=DLIST_HEAD(MIR_module_t,*MIR_get_module_list(ctx));m;m=DLIST_NEXT(MIR_module_t,m))MIR_load_module(ctx,m); MIR_gen_init(ctx); MIR_gen_set_object_mode(ctx,1); MIR_link(ctx,MIR_set_gen_interface,NULL); for(m=DLIST_HEAD(MIR_module_t,*MIR_get_module_list(ctx));m;m=DLIST_NEXT(MIR_module_t,m))for(it=DLIST_HEAD(MIR_item_t,m->items);it;it=DLIST_NEXT(MIR_item_t,it))if(it->item_type==MIR_func_item)(void)MIR_gen(ctx,it); if(MIR_gen_object_emit(ctx,&buf,&n)!=0||!buf){MIR_gen_finish(ctx);return 40;}f=fopen(path,"wb");if(!f||fwrite(buf,1,n,f)!=n){if(f)fclose(f);free(buf);MIR_gen_finish(ctx);return 41;}fclose(f);free(buf);MIR_gen_finish(ctx);return 0; }
static uint64_t narrow(uint64_t x,unsigned b,int sign) { uint64_t m=(UINT64_C(1)<<b)-1, y=x&m; if(sign&&(y&(UINT64_C(1)<<(b-1))))y|=~m;return y; }
static int64_t sx32(uint64_t x) { uint32_t y=(uint32_t)x; return (y&UINT32_C(0x80000000))?(int64_t)y-INT64_C(0x100000000):(int64_t)y; }
static int64_t s64(uint64_t u) { int64_t x; memcpy(&x,&u,sizeof x); return x; }
static uint64_t exp_cvt(const Cvt*c,uint64_t u,float fv,double dv) { switch(c->kind){case 0:return narrow(u,8,1);case 1:return narrow(u,16,1);case 2:return narrow(u,32,1);case 3:return narrow(u,8,0);case 4:return narrow(u,16,0);case 5:return narrow(u,32,0);case 6:{float x=(float)s64(u);uint32_t z;memcpy(&z,&x,4);return z;}case 7:{float x=(float)u;uint32_t z;memcpy(&z,&x,4);return z;}case 8:{double x=(double)s64(u);uint64_t z;memcpy(&z,&x,8);return z;}case 9:{double x=(double)u;uint64_t z;memcpy(&z,&x,8);return z;}case 10:return (uint64_t)(int64_t)truncf(fv);case 11:return (uint64_t)(int64_t)trunc(dv);case 12:{double x=(double)fv;uint64_t z;memcpy(&z,&x,8);return z;}case 13:{float x=(float)dv;uint32_t z;memcpy(&z,&x,4);return z;}default:abort();} }
static void input_cvt(const Cvt*c,uint64_t u,float fv,double dv,MIR_val_t *a) { if(c->kind<=9)a->u=u;else if(c->kind==10||c->kind==12)a->f=fv;else a->d=dv; }
static uint64_t result_cvt(const Cvt*c,MIR_val_t r) { if(c->out==MIR_T_F){uint32_t v;memcpy(&v,&r.f,4);return v;}if(c->out==MIR_T_D){uint64_t v;memcpy(&v,&r.d,8);return v;}return r.u; }
static int run(int save,int emit) {
  static const uint64_t ui[]={0,1,UINT64_C(0x7f),UINT64_C(0x80),UINT64_C(0xff),UINT64_C(0x100),UINT64_C(0x7fff),UINT64_C(0x8000),UINT64_C(0xffff),UINT64_C(0x10000),UINT64_C(0x7fffffff),UINT64_C(0x80000000),UINT64_C(0xffffffff),UINT64_C(0x100000000),UINT64_C(0x0101010101010101),UINT64_C(0x8000000000000000),UINT64_C(0x7fffffffffffffff)};
  static const float fs[]={-2147483520.0f,-123.75f,-1.9f,-0.0f,0.0f,0.9f,1.9f,123.75f,16777216.0f,16777218.0f,2147483520.0f};
  static const double ds[]={-9223372036854774784.0,-2147483649.0,-123.75,-1.9,-0.0,0.0,0.9,1.9,123.75,2147483647.0,9007199254740992.0,9223372036854774784.0};
  static const struct {uint64_t a,b; int want;} pairs[] = {
    {0,0,0},{1,2,0},{UINT64_MAX,1,1},{UINT64_C(0x7fffffffffffffff),1,1},
    {UINT64_C(0x8000000000000000),1,0},{0,1,1},{UINT64_C(0x8000000000000000),1,1},
    {3,7,0},{UINT64_C(0x4000000000000000),4,1},{UINT64_MAX,2,1},
    {UINT64_C(0x7fffffff),1,0},{UINT64_C(0x7fffffff),1,1},{UINT64_C(0xffffffff),2,1}
  };
  size_t i,j,n=0; MIR_module_t m; MIR_item_t it;
  for(m=DLIST_HEAD(MIR_module_t,*MIR_get_module_list(ctx));m;m=DLIST_NEXT(MIR_module_t,m))MIR_load_module(ctx,m);
  MIR_gen_init(ctx); MIR_link(ctx,MIR_set_gen_interface,NULL);
  for(i=0;i<sizeof(cvts)/sizeof(cvts[0]);i++) for(j=0;j<sizeof(ui)/sizeof(ui[0]);j++) {
    const Cvt*c=&cvts[i];uint64_t u=ui[j],want,got,jgot;float fv=fs[j%(sizeof(fs)/sizeof(fs[0]))];double dv=ds[j%(sizeof(ds)/sizeof(ds[0]))];MIR_val_t a,r;
    if(c->kind==10||c->kind==12) fv=fs[j%(sizeof(fs)/sizeof(fs[0]))];
    if(c->kind==11||c->kind==13) dv=ds[j%(sizeof(ds)/sizeof(ds[0]))];
    want=exp_cvt(c,u,fv,dv); input_cvt(c,u,fv,dv,&a);it=findf(c->name);if(!it)return 10;MIR_interp_arr(ctx,it,&r,1,&a);got=result_cvt(c,r);
    if(c->in==MIR_T_I64) {
      if(c->out==MIR_T_I64){typedef int64_t(*fn)(int64_t);jgot=(uint64_t)((fn)MIR_gen(ctx,it))(a.i);}
      else if(c->out==MIR_T_F){typedef float(*fn)(int64_t);float x=((fn)MIR_gen(ctx,it))(a.i);uint32_t z;memcpy(&z,&x,4);jgot=z;}
      else {typedef double(*fn)(int64_t);double x=((fn)MIR_gen(ctx,it))(a.i);memcpy(&jgot,&x,8);}
    } else if(c->in==MIR_T_F) {
      if(c->out==MIR_T_I64){typedef int64_t(*fn)(float);jgot=(uint64_t)((fn)MIR_gen(ctx,it))(a.f);}
      else {typedef double(*fn)(float);double x=((fn)MIR_gen(ctx,it))(a.f);memcpy(&jgot,&x,8);}
    } else {
      if(c->out==MIR_T_I64){typedef int64_t(*fn)(double);jgot=(uint64_t)((fn)MIR_gen(ctx,it))(a.d);}
      else {typedef float(*fn)(double);float x=((fn)MIR_gen(ctx,it))(a.d);uint32_t z;memcpy(&z,&x,4);jgot=z;}
    }
    if(got!=want||jgot!=want){fprintf(stderr,"conversion mismatch %s index=%zu expected=%" PRIx64 " interp=%" PRIx64 " jit=%" PRIx64 "\n",c->name,j,want,got,jgot);return 11;}
    if(emit) { uint64_t inbits=u; if(c->in==MIR_T_F){uint32_t z;memcpy(&z,&fv,4);inbits=z;} else if(c->in==MIR_T_D)memcpy(&inbits,&dv,8); printf("{\"family\":\"conversion\",\"opcode\":\"%s\",\"index\":%zu,\"input_bits\":\"%016" PRIx64 "\",\"expected_bits\":\"%016" PRIx64 "\",\"interpreter_bits\":\"%016" PRIx64 "\",\"jit_bits\":\"%016" PRIx64 "\"}\n",c->name,j,inbits,want,got,jgot); }
    n++;
  }
  for(i=0;i<sizeof(ovs)/sizeof(ovs[0]);i++) for(j=0;j<sizeof(pairs)/sizeof(pairs[0]);j++) {
    const Ov*o=&ovs[i];uint64_t a=pairs[j].a,b=pairs[j].b;int want=pairs[j].want; if(o->bits==32){a=(uint32_t)a;b=(uint32_t)b;}
    /* Cases are per-op, with independently defined boundary predicates. */
    if((i==0||i==1)) { int64_t x=o->bits==32?sx32(a):s64(a),y=o->bits==32?sx32(b):s64(b);__int128 p=(__int128)x+y;want=p> (o->bits==32?INT32_MAX:INT64_MAX)||p<(o->bits==32?INT32_MIN:INT64_MIN); }
    else if(i==2||i==3) { int64_t x=o->bits==32?sx32(a):s64(a),y=o->bits==32?sx32(b):s64(b);__int128 p=(__int128)x-y;want=p>(o->bits==32?INT32_MAX:INT64_MAX)||p<(o->bits==32?INT32_MIN:INT64_MIN); }
    else if(i==4||i==5) { __int128 x=o->bits==32?sx32(a):s64(a),y=o->bits==32?sx32(b):s64(b),p=x*y;int64_t lo=o->bits==32?INT32_MIN:INT64_MIN,hi=o->bits==32?INT32_MAX:INT64_MAX;want=p<lo||p>hi; }
    else { __uint128_t p=(__uint128_t)a*(__uint128_t)b;want=o->bits==32?p>UINT32_MAX:p>UINT64_MAX; }
    MIR_val_t av[2],r;av[0].u=a;av[1].u=b;it=findf(o->name);MIR_interp_arr(ctx,it,&r,2,av);uint64_t got=r.u;
    {typedef int64_t(*fn)(int64_t,int64_t);uint64_t jgot=(uint64_t)((fn)MIR_gen(ctx,it))((int64_t)a,(int64_t)b);if(got!=(uint64_t)want||jgot!=(uint64_t)want){fprintf(stderr,"overflow branch mismatch %s index=%zu expected=%d interp=%" PRIu64 " jit=%" PRIu64 "\n",o->name,j,want,got,jgot);return 12;}if(emit)printf("{\"family\":\"overflow\",\"opcode\":\"%s\",\"index\":%zu,\"a\":\"%016" PRIx64 "\",\"b\":\"%016" PRIx64 "\",\"expected_flag\":%d,\"interpreter\":%" PRIu64 ",\"jit\":%" PRIu64 "}\n",o->name,j,a,b,want,got,jgot);}
    {char rn[48];MIR_item_t rf;uint64_t rw,ri,rj;typedef int64_t(*fn_t)(int64_t,int64_t);snprintf(rn,sizeof rn,"result_%s",o->name);rf=findf(rn);MIR_interp_arr(ctx,rf,&r,2,av);ri=r.u;
      if(o->bits==64){if(i==0)rw=a+b;else if(i==2)rw=a-b;else rw=a*b;}
      else if(i==0||i==2||i==4) {uint32_t z=i==0?(uint32_t)a+(uint32_t)b:i==2?(uint32_t)a-(uint32_t)b:(uint32_t)((uint64_t)(uint32_t)a*(uint32_t)b);rw=(uint64_t)sx32(z);}
      else {uint32_t z=i==1?(uint32_t)a+(uint32_t)b:i==3?(uint32_t)a-(uint32_t)b:(uint32_t)((uint64_t)(uint32_t)a*(uint32_t)b);rw=z;}
      rj=(uint64_t)((fn_t)MIR_gen(ctx,rf))((int64_t)a,(int64_t)b);
      if(o->bits==32){if((uint32_t)ri!=(uint32_t)rw||(uint32_t)rj!=(uint32_t)rw){fprintf(stderr,"overflow result mismatch %s index=%zu expected_low32=%08" PRIx64 " interp=%016" PRIx64 " jit=%016" PRIx64 "\n",o->name,j,rw,ri,rj);return 13;}}
      else if(ri!=rw||rj!=rw){fprintf(stderr,"overflow result mismatch %s index=%zu expected=%016" PRIx64 " interp=%016" PRIx64 " jit=%016" PRIx64 "\n",o->name,j,rw,ri,rj);return 14;}
      if(emit)printf("{\"family\":\"overflow_result\",\"opcode\":\"%s\",\"index\":%zu,\"expected_bits\":\"%016" PRIx64 "\",\"interpreter_bits\":\"%016" PRIx64 "\",\"jit_bits\":\"%016" PRIx64 "\"}\n",o->name,j,rw,ri,rj); }
    n+=2;
  }
  if(save){FILE*f=fopen(save==1?"results/cycle45-mir-numeric-boundaries/program.mir":"results/cycle45-mir-numeric-boundaries/program.bmir",save==1?"w":"wb");if(!f)return 20;if(save==1)MIR_output(ctx,f);else MIR_write(ctx,f);fclose(f);}
  MIR_gen_finish(ctx);fprintf(stderr,"PASS cycle45 numerical observations=%zu conversions=%zu overflow_flag_and_result=%zu\n",n,(sizeof(cvts)/sizeof(cvts[0]))*(sizeof(ui)/sizeof(ui[0])),2*(sizeof(ovs)/sizeof(ovs[0]))*(sizeof(pairs)/sizeof(pairs[0])));return 0;
}
static int load_path(int binary,const char *path){FILE*f=fopen(path,"rb");long n;char*s;if(!f)return 30;ctx=MIR_init();if(binary)MIR_read(ctx,f);else{if(fseek(f,0,SEEK_END)||(n=ftell(f))<0||fseek(f,0,SEEK_SET))return 31;s=malloc((size_t)n+1);if(!s)return 32;if(fread(s,1,(size_t)n,f)!=(size_t)n)return 33;s[n]=0;MIR_scan_string(ctx,s);free(s);}fclose(f);return run(0,1);}
int main(int argc,char **argv){int rc;if(argc==3&&!strcmp(argv[1],"--text"))rc=load_path(0,argv[2]);else if(argc==3&&!strcmp(argv[1],"--binary"))rc=load_path(1,argv[2]);else{build();if(argc==3&&!strcmp(argv[1],"--object"))rc=emit_object(argv[2]);else{rc=run(1,1);if(!rc){/* binary is written by a second pass because MIR_write has a binary FILE */FILE*f=fopen("results/cycle45-mir-numeric-boundaries/program.bmir","wb");if(f){MIR_write(ctx,f);fclose(f);}}}}MIR_finish(ctx);return rc;}
