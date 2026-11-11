/* Direct MIR calling-convention corpus. Generated scalar cases use exact C prototypes. */
#define _GNU_SOURCE
#include "mir.h"
#include "mir-gen.h"
#include "mir-debug.h"
#include <dlfcn.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define V_I64(x) (x)
#define V_U64(x) (x)
#define V_I32(x) (x)
#define V_U32(x) (x)
#define V_P(x) (x)
#define V_F(x) (x)
#define V_D(x) (x)
#include "cycle44-signature-stubs.inc"

#define R(n) MIR_new_reg_op(ctx,(n))
#define I(n) MIR_new_int_op(ctx,(n))
#define U(n) MIR_new_uint_op(ctx,(n))
#define D(n) MIR_new_double_op(ctx,(n))
#define APP(f,x) MIR_append_insn(ctx,(f),(x))
static MIR_context_t ctx;

int64_t abi_c_integer8(int64_t a0,int64_t a1,int64_t a2,int64_t a3,int64_t a4,int64_t a5,int64_t a6,int64_t a7) {
  return 3*a0+5*a1+7*a2+11*a3+13*a4+17*a5+19*a6+23*a7;
}
double abi_c_mixed(int64_t a0,double a1,int64_t a2,double a3,int64_t a4,double a5,int64_t a6,double a7) {
  return 3.0*a0+5.0*a1+7.0*a2+11.0*a3+13.0*a4+17.0*a5+19.0*a6+23.0*a7;
}
int64_t abi_c_pointer(uint8_t *p,int64_t n) {
  int64_t sum=0;
  for(int64_t i=0;i<n;i++){p[i]=(uint8_t)(i*7+3);sum+=(int64_t)p[i]*(i+1);}
  return sum;
}

static MIR_item_t find_item(const char *name) {
  MIR_module_t m; MIR_item_t it;
  for(m=DLIST_HEAD(MIR_module_t,*MIR_get_module_list(ctx));m;m=DLIST_NEXT(MIR_module_t,m))
    for(it=DLIST_HEAD(MIR_item_t,m->items);it;it=DLIST_NEXT(MIR_item_t,it))
      if(MIR_item_name(ctx,it)&&strcmp(MIR_item_name(ctx,it),name)==0)return it;
  return NULL;
}
static MIR_item_t make_arr_func(const char *name,MIR_type_t ret,size_t n,MIR_var_t *vars) {
  return MIR_new_func_arr(ctx,name,1,&ret,n,vars);
}
static MIR_item_t make_i64_func(const char *name,size_t n,MIR_var_t *vars) {
  return make_arr_func(name,MIR_T_I64,n,vars);
}
static MIR_item_t make_proto(const char *name,MIR_type_t ret,size_t n,MIR_var_t *vars) {
  return MIR_new_proto_arr(ctx,name,1,&ret,n,vars);
}
static MIR_type_t mir_type(AbiType t) {
  switch(t){case ABI_I64:return MIR_T_I64;case ABI_U64:return MIR_T_U64;case ABI_I32:return MIR_T_I32;case ABI_U32:return MIR_T_U32;case ABI_P:return MIR_T_P;case ABI_F:return MIR_T_F;case ABI_D:return MIR_T_D;default:abort();}
}
static void make_matrix_func(int id) {
  const AbiCase *spec=&abi_cases[id];
  MIR_var_t vars[10]; MIR_type_t ret=spec->returns_double?MIR_T_D:MIR_T_I64;
  char argnames[10][12]; MIR_item_t f;
  for(int j=0;j<spec->n;j++) {
    vars[j].type=mir_type(spec->args[j]);
    snprintf(argnames[j],sizeof argnames[j],"a%d",j); vars[j].name=argnames[j]; vars[j].size=0;
  }
  f=make_arr_func(spec->name,ret,(size_t)spec->n,vars);
  if(!f){fprintf(stderr,"failed creating %s\n",spec->name);exit(30);}
  if(spec->returns_double) {
    MIR_reg_t acc=MIR_new_func_reg(ctx,f->u.func,MIR_T_D,"acc");
    APP(f,MIR_new_insn(ctx,MIR_DMOV,R(acc),D(0.0)));
    for(int j=0;j<spec->n;j++) {
      char tmpname[16]; snprintf(tmpname,sizeof tmpname,"tmp%d",j);
      MIR_reg_t src=MIR_reg(ctx,argnames[j],f->u.func), tmp=MIR_new_func_reg(ctx,f->u.func,MIR_T_D,tmpname);
      if(spec->args[j]==ABI_D) APP(f,MIR_new_insn(ctx,MIR_DMOV,R(tmp),R(src)));
      else if(spec->args[j]==ABI_F) APP(f,MIR_new_insn(ctx,MIR_F2D,R(tmp),R(src)));
      else APP(f,MIR_new_insn(ctx,MIR_I2D,R(tmp),R(src)));
      APP(f,MIR_new_insn(ctx,MIR_DMUL,R(tmp),R(tmp),D((double)(3+2*j))));
      APP(f,MIR_new_insn(ctx,MIR_DADD,R(acc),R(acc),R(tmp)));
    }
    APP(f,MIR_new_ret_insn(ctx,1,R(acc)));
  } else {
    MIR_reg_t acc=MIR_new_func_reg(ctx,f->u.func,MIR_T_I64,"acc");
    APP(f,MIR_new_insn(ctx,MIR_MOV,R(acc),I(0)));
    for(int j=0;j<spec->n;j++) {
      char tmpname[16]; snprintf(tmpname,sizeof tmpname,"tmp%d",j);
      MIR_reg_t src=MIR_reg(ctx,argnames[j],f->u.func), tmp=MIR_new_func_reg(ctx,f->u.func,MIR_T_I64,tmpname);
      APP(f,MIR_new_insn(ctx,MIR_MUL,R(tmp),R(src),I(3+2*j)));
      APP(f,MIR_new_insn(ctx,MIR_ADD,R(acc),R(acc),R(tmp)));
    }
    APP(f,MIR_new_ret_insn(ctx,1,R(acc)));
  }
  MIR_finish_func(ctx); MIR_new_export(ctx,spec->name);
}

static void make_leaf(const char *name,const int64_t *weights) {
  MIR_var_t v[8]; char names[8][8];
  for(int i=0;i<8;i++){v[i].type=MIR_T_I64;snprintf(names[i],8,"a%d",i);v[i].name=names[i];v[i].size=0;}
  MIR_item_t f=make_i64_func(name,8,v); MIR_reg_t acc=MIR_new_func_reg(ctx,f->u.func,MIR_T_I64,"acc");
  APP(f,MIR_new_insn(ctx,MIR_MOV,R(acc),I(0)));
  for(int i=0;i<8;i++){char tmpname[16];snprintf(tmpname,sizeof tmpname,"tmp%d",i);MIR_reg_t tmp=MIR_new_func_reg(ctx,f->u.func,MIR_T_I64,tmpname);APP(f,MIR_new_insn(ctx,MIR_MUL,R(tmp),R(MIR_reg(ctx,names[i],f->u.func)),I(weights[i])));APP(f,MIR_new_insn(ctx,MIR_ADD,R(acc),R(acc),R(tmp)));}
  APP(f,MIR_new_ret_insn(ctx,1,R(acc)));MIR_finish_func(ctx);MIR_new_export(ctx,name);
}
static void make_identity(const char *name,MIR_type_t argtype,MIR_type_t rettype) {
  MIR_var_t v={argtype,"x",0};MIR_item_t f=MIR_new_func_arr(ctx,name,1,&rettype,1,&v);
  APP(f,MIR_new_ret_insn(ctx,1,R(MIR_reg(ctx,"x",f->u.func))));MIR_finish_func(ctx);MIR_new_export(ctx,name);
}
static MIR_insn_t call_arr(MIR_item_t proto,MIR_op_t target,MIR_op_t *results,size_t nr,MIR_op_t *args,size_t na) {
  MIR_op_t ops[24]; size_t n=0; ops[n++]=MIR_new_ref_op(ctx,proto);ops[n++]=target;
  for(size_t i=0;i<nr;i++)ops[n++]=results[i];
  for(size_t i=0;i<na;i++)ops[n++]=args[i];
  return MIR_new_insn_arr(ctx,MIR_CALL,n,ops);
}
static void make_call_module(void) {
  MIR_module_t m=MIR_new_module(ctx,"abi_callers");
  MIR_item_t leaf=MIR_new_import(ctx,"abi_leaf8"), leafb=MIR_new_import(ctx,"abi_leaf8b");
  int64_t weights[8]={3,5,7,11,13,17,19,23}, weightsb[8]={2,4,6,8,10,12,14,16};
  MIR_type_t itypes[8]; MIR_var_t args[8]; char n[8][8];
  for(int i=0;i<8;i++){itypes[i]=MIR_T_I64;args[i].type=MIR_T_I64;snprintf(n[i],8,"x%d",i);args[i].name=n[i];args[i].size=0;}
  MIR_item_t leafp=make_proto("abi_leaf8_proto",MIR_T_I64,8,args), leafbp=make_proto("abi_leaf8b_proto",MIR_T_I64,8,args);
  MIR_item_t fn=make_i64_func("abi_internal_caller",8,args);
  MIR_reg_t live=MIR_new_func_reg(ctx,fn->u.func,MIR_T_I64,"live"),r1=MIR_new_func_reg(ctx,fn->u.func,MIR_T_I64,"r1"),r2=MIR_new_func_reg(ctx,fn->u.func,MIR_T_I64,"r2"),out=MIR_new_func_reg(ctx,fn->u.func,MIR_T_I64,"out");
  APP(fn,MIR_new_insn(ctx,MIR_MUL,R(live),R(MIR_reg(ctx,n[0],fn->u.func)),I(29)));
  {MIR_reg_t t=MIR_new_func_reg(ctx,fn->u.func,MIR_T_I64,"t");APP(fn,MIR_new_insn(ctx,MIR_MUL,R(t),R(MIR_reg(ctx,n[7],fn->u.func)),I(31)));APP(fn,MIR_new_insn(ctx,MIR_ADD,R(live),R(live),R(t)));}
  MIR_op_t a1[8],a2[8];for(int i=0;i<8;i++){a1[i]=R(MIR_reg(ctx,n[i],fn->u.func));a2[i]=R(MIR_reg(ctx,n[7-i],fn->u.func));}
  MIR_op_t o1[1]={R(r1)},o2[1]={R(r2)}; APP(fn,call_arr(leafp,MIR_new_ref_op(ctx,leaf),o1,1,a1,8)); APP(fn,call_arr(leafbp,MIR_new_ref_op(ctx,leafb),o2,1,a2,8));
  APP(fn,MIR_new_insn(ctx,MIR_ADD,R(out),R(live),R(r1)));APP(fn,MIR_new_insn(ctx,MIR_ADD,R(out),R(out),R(r2)));APP(fn,MIR_new_ret_insn(ctx,1,R(out)));MIR_finish_func(ctx);MIR_new_export(ctx,"abi_internal_caller");
  MIR_item_t internalp=make_proto("abi_internal_caller_proto",MIR_T_I64,8,args);
  MIR_item_t top=make_i64_func("abi_chain_top",8,args);MIR_reg_t tr=MIR_new_func_reg(ctx,top->u.func,MIR_T_I64,"r");MIR_op_t ta[8],to[1]={R(tr)};for(int i=0;i<8;i++)ta[i]=R(MIR_reg(ctx,n[i],top->u.func));APP(top,call_arr(internalp,MIR_new_ref_op(ctx,fn),to,1,ta,8));APP(top,MIR_new_insn(ctx,MIR_ADD,R(tr),R(tr),I(17)));APP(top,MIR_new_ret_insn(ctx,1,R(tr)));MIR_finish_func(ctx);MIR_new_export(ctx,"abi_chain_top");
  (void)weights;(void)weightsb;(void)itypes;
  MIR_item_t ci=MIR_new_import(ctx,"abi_c_integer8"), cm=MIR_new_import(ctx,"abi_c_mixed"), cp=MIR_new_import(ctx,"abi_c_pointer");
  MIR_item_t cip=make_proto("abi_c_integer8_proto",MIR_T_I64,8,args);
  MIR_item_t fi=MIR_new_func_arr(ctx,"abi_import_integer8",1,(MIR_type_t[]){MIR_T_I64},8,args);MIR_reg_t fr=MIR_new_func_reg(ctx,fi->u.func,MIR_T_I64,"r");MIR_op_t fa[8],fo[1]={R(fr)};for(int i=0;i<8;i++)fa[i]=R(MIR_reg(ctx,n[i],fi->u.func));APP(fi,call_arr(cip,MIR_new_ref_op(ctx,ci),fo,1,fa,8));APP(fi,MIR_new_ret_insn(ctx,1,R(fr)));MIR_finish_func(ctx);MIR_new_export(ctx,"abi_import_integer8");
  MIR_var_t mixed[8];MIR_type_t mt[8]={MIR_T_I64,MIR_T_D,MIR_T_I64,MIR_T_D,MIR_T_I64,MIR_T_D,MIR_T_I64,MIR_T_D};char mn[8][8];for(int i=0;i<8;i++){mixed[i].type=mt[i];snprintf(mn[i],8,"m%d",i);mixed[i].name=mn[i];mixed[i].size=0;}
  MIR_item_t cmp=make_proto("abi_c_mixed_proto",MIR_T_D,8,mixed);MIR_item_t fm=MIR_new_func_arr(ctx,"abi_import_mixed",1,(MIR_type_t[]){MIR_T_D},8,mixed);MIR_reg_t mr=MIR_new_func_reg(ctx,fm->u.func,MIR_T_D,"r");MIR_op_t ma[8],mo[1]={R(mr)};for(int i=0;i<8;i++)ma[i]=R(MIR_reg(ctx,mn[i],fm->u.func));APP(fm,call_arr(cmp,MIR_new_ref_op(ctx,cm),mo,1,ma,8));APP(fm,MIR_new_ret_insn(ctx,1,R(mr)));MIR_finish_func(ctx);MIR_new_export(ctx,"abi_import_mixed");
  MIR_var_t pv[2]={{MIR_T_P,"ptr",0},{MIR_T_I64,"len",0}};MIR_item_t cpp=make_proto("abi_c_pointer_proto",MIR_T_I64,2,pv),pf=MIR_new_func_arr(ctx,"abi_import_pointer",1,(MIR_type_t[]){MIR_T_I64},2,pv);MIR_reg_t pr=MIR_new_func_reg(ctx,pf->u.func,MIR_T_I64,"r");MIR_op_t pa[2]={R(MIR_reg(ctx,"ptr",pf->u.func)),R(MIR_reg(ctx,"len",pf->u.func))},po[1]={R(pr)};APP(pf,call_arr(cpp,MIR_new_ref_op(ctx,cp),po,1,pa,2));APP(pf,MIR_new_ret_insn(ctx,1,R(pr)));MIR_finish_func(ctx);MIR_new_export(ctx,"abi_import_pointer");
  MIR_item_t two=MIR_new_import(ctx,"abi_two_result");MIR_type_t twores[2]={MIR_T_I64,MIR_T_D};MIR_var_t twoargs[2]={{MIR_T_I64,"a",0},{MIR_T_D,"b",0}};
  MIR_item_t twop=MIR_new_proto_arr(ctx,"abi_two_result_proto",2,twores,2,twoargs);
  MIR_item_t twoc=MIR_new_func_arr(ctx,"abi_two_result_caller",1,(MIR_type_t[]){MIR_T_D},2,twoargs);MIR_reg_t ri=MIR_new_func_reg(ctx,twoc->u.func,MIR_T_I64,"ri"),rd=MIR_new_func_reg(ctx,twoc->u.func,MIR_T_D,"rd"),di=MIR_new_func_reg(ctx,twoc->u.func,MIR_T_D,"di"),sum=MIR_new_func_reg(ctx,twoc->u.func,MIR_T_D,"sum");
  MIR_op_t twoout[2]={R(ri),R(rd)},twoin[2]={R(MIR_reg(ctx,"a",twoc->u.func)),R(MIR_reg(ctx,"b",twoc->u.func))};APP(twoc,call_arr(twop,MIR_new_ref_op(ctx,two),twoout,2,twoin,2));APP(twoc,MIR_new_insn(ctx,MIR_I2D,R(di),R(ri)));APP(twoc,MIR_new_insn(ctx,MIR_DADD,R(sum),R(di),R(rd)));APP(twoc,MIR_new_ret_insn(ctx,1,R(sum)));MIR_finish_func(ctx);MIR_new_export(ctx,"abi_two_result_caller");
  (void)weights;(void)weightsb;(void)m;MIR_finish_module(ctx);
}
static MIR_context_t build_program(void) {
  int64_t w1[8]={3,5,7,11,13,17,19,23},w2[8]={2,4,6,8,10,12,14,16};
  ctx=MIR_init();MIR_new_module(ctx,"abi_signatures");
  for(int i=0;i<ABI_CASE_COUNT;i++)make_matrix_func(i);
  make_leaf("abi_leaf8",w1);make_leaf("abi_leaf8b",w2);
  make_identity("abi_sign_i32",MIR_T_I32,MIR_T_I64);
  make_identity("abi_zero_u32",MIR_T_U32,MIR_T_U64);
  make_identity("abi_raw_u64",MIR_T_U64,MIR_T_U64);
  make_identity("abi_float_identity",MIR_T_F,MIR_T_F);
  make_identity("abi_pointer_identity",MIR_T_P,MIR_T_P);
  MIR_var_t rv[2]={{MIR_T_I64,"a",0},{MIR_T_D,"b",0}};MIR_type_t res[2]={MIR_T_I64,MIR_T_D};MIR_item_t mr=MIR_new_func_arr(ctx,"abi_two_result",2,res,2,rv);MIR_reg_t ar=MIR_reg(ctx,"a",mr->u.func),br=MIR_reg(ctx,"b",mr->u.func),dr=MIR_new_func_reg(ctx,mr->u.func,MIR_T_D,"d");APP(mr,MIR_new_insn(ctx,MIR_DMUL,R(dr),R(br),D(2.0)));APP(mr,MIR_new_ret_insn(ctx,2,R(ar),R(dr)));MIR_finish_func(ctx);MIR_new_export(ctx,"abi_two_result");
  MIR_finish_module(ctx);make_call_module();return ctx;
}
static void load_and_link(void) {
  MIR_module_t m;for(m=DLIST_HEAD(MIR_module_t,*MIR_get_module_list(ctx));m;m=DLIST_NEXT(MIR_module_t,m))MIR_load_module(ctx,m);
  MIR_load_external(ctx,"abi_c_integer8",(void*)abi_c_integer8);MIR_load_external(ctx,"abi_c_mixed",(void*)abi_c_mixed);MIR_load_external(ctx,"abi_c_pointer",(void*)abi_c_pointer);
  MIR_gen_init(ctx);MIR_link(ctx,MIR_set_gen_interface,NULL);
}
static void save_files(const char *textpath,const char *binpath) {
  FILE *f=fopen(textpath,"w");if(!f){perror(textpath);exit(20);}MIR_output(ctx,f);fclose(f);f=fopen(binpath,"wb");if(!f){perror(binpath);exit(21);}MIR_write(ctx,f);fclose(f);
}
static int64_t expected_internal(int seed) {
  int64_t a[8];for(int i=0;i<8;i++)a[i]=seed+i+1;
  int64_t x=0,y=0,live=a[0]*29+a[7]*31;
  int64_t w1[8]={3,5,7,11,13,17,19,23},w2[8]={2,4,6,8,10,12,14,16};
  for(int i=0;i<8;i++){x+=a[i]*w1[i];y+=a[7-i]*w2[i];}
  return live+x+y;
}
static int64_t call8_i64(void *p,int seed,int top) {int64_t a[8];for(int i=0;i<8;i++)a[i]=seed+i+1;if(top){typedef int64_t(*F)(int64_t,int64_t,int64_t,int64_t,int64_t,int64_t,int64_t,int64_t);return ((F)p)(a[0],a[1],a[2],a[3],a[4],a[5],a[6],a[7]);}typedef int64_t(*F)(int64_t,int64_t,int64_t,int64_t,int64_t,int64_t,int64_t,int64_t);return ((F)p)(a[0],a[1],a[2],a[3],a[4],a[5],a[6],a[7]);}
static double call8_mixed(void *p,int seed) {typedef double(*F)(int64_t,double,int64_t,double,int64_t,double,int64_t,double);return ((F)p)(seed+1,.5*(seed+2),seed+3,.5*(seed+4),seed+5,.5*(seed+6),seed+7,.5*(seed+8));}
static int64_t call_pointer(void *p,uint8_t *b,int64_t n) {typedef int64_t(*F)(uint8_t*,int64_t);return ((F)p)(b,n);}
static double call_two_result(void *p,int64_t a,double b) {typedef double(*F)(int64_t,double);return ((F)p)(a,b);}
static const char *resolver_drop;
static void *resolver(const char *name,void *env) {(void)env;if(resolver_drop&&!strcmp(name,resolver_drop))return NULL;if(!strcmp(name,"abi_c_integer8"))return (void*)abi_c_integer8;if(!strcmp(name,"abi_c_mixed"))return (void*)abi_c_mixed;if(!strcmp(name,"abi_c_pointer"))return (void*)abi_c_pointer;return NULL;}
static int run_semantics(int emit_rows) {
  MIR_val_t vals[10],res[2]; int failures=0;
  for(int i=0;i<ABI_CASE_COUNT;i++) {
    const AbiCase *spec=&abi_cases[i]; MIR_item_t f=find_item(spec->name);
    if(!f){fprintf(stderr,"missing %s\n",spec->name);return 30;}
    void *jit=MIR_gen(ctx,f);
    for(int seed=0;seed<5;seed++) {
      memset(vals,0,sizeof vals); abi_fill_dispatch(i,seed,vals); memset(res,0,sizeof res);
      MIR_interp_arr(ctx,f,res,(size_t)spec->n,vals);
      int64_t got_i=0,want_i=0; double got_d=0,want_d=0;
      abi_run_dispatch(i,jit,seed,&got_i,&got_d);
      if(spec->returns_double) {
        want_d=abi_oracle_double_dispatch(i,seed);
        if(res[0].d!=want_d||got_d!=want_d){failures++;fprintf(stderr,"double mismatch %s seed=%d interp=%.17g jit=%.17g expected=%.17g\n",spec->name,seed,res[0].d,got_d,want_d);}
        if(emit_rows)printf("{\"case\":\"%s\",\"seed\":%d,\"expected\":%.17g,\"interpreter\":%.17g,\"jit\":%.17g,\"pass\":%s}\n",spec->name,seed,want_d,res[0].d,got_d,(res[0].d==want_d&&got_d==want_d)?"true":"false");
      } else {
        want_i=abi_oracle_int_dispatch(i,seed);
        if(res[0].i!=want_i||got_i!=want_i){failures++;fprintf(stderr,"integer mismatch %s seed=%d interp=%" PRId64 " jit=%" PRId64 " expected=%" PRId64 "\n",spec->name,seed,res[0].i,got_i,want_i);}
        if(emit_rows)printf("{\"case\":\"%s\",\"seed\":%d,\"expected\":\"%" PRId64 "\",\"interpreter\":\"%" PRId64 "\",\"jit\":\"%" PRId64 "\",\"pass\":%s}\n",spec->name,seed,want_i,res[0].i,got_i,(res[0].i==want_i&&got_i==want_i)?"true":"false");
      }
    }
  }
  /* Register pressure: values are formed before two nested calls and consumed afterwards. */
  for(int seed=0;seed<3;seed++) {
    int64_t a[8]; MIR_val_t av[8],r[2];
    for(int i=0;i<8;i++){a[i]=seed+i+1;av[i].i=a[i];}
    MIR_item_t f=find_item("abi_internal_caller"),top=find_item("abi_chain_top");
    int64_t expected=expected_internal(seed),got=call8_i64(MIR_gen(ctx,f),seed,0);
    MIR_interp_arr(ctx,f,r,8,av); if(r[0].i!=expected||got!=expected)failures++;
    int64_t topwant=expected+17;MIR_interp_arr(ctx,top,r,8,av);
    if(r[0].i!=topwant||call8_i64(MIR_gen(ctx,top),seed,1)!=topwant)failures++;
    MIR_item_t imp=find_item("abi_import_integer8");int64_t cexpected=abi_c_integer8(a[0],a[1],a[2],a[3],a[4],a[5],a[6],a[7]);
    MIR_interp_arr(ctx,imp,r,8,av);if(r[0].i!=cexpected||call8_i64(MIR_gen(ctx,imp),seed,0)!=cexpected)failures++;
    MIR_val_t mv[8];for(int i=0;i<8;i++){if(i%2==0)mv[i].i=seed+i+1;else mv[i].d=.5*(seed+i+1);}
    MIR_item_t impm=find_item("abi_import_mixed");double mw=abi_c_mixed(seed+1,.5*(seed+2),seed+3,.5*(seed+4),seed+5,.5*(seed+6),seed+7,.5*(seed+8));
    MIR_interp_arr(ctx,impm,r,8,mv);if(r[0].d!=mw||call8_mixed(MIR_gen(ctx,impm),seed)!=mw)failures++;
    MIR_item_t imptr=find_item("abi_import_pointer");uint8_t ip[18],jp[18];memset(ip,0xa5,sizeof ip);memset(jp,0xa5,sizeof jp);MIR_val_t pv[2]={0};pv[0].a=ip+5;pv[1].i=8;int64_t pw=abi_c_pointer(ip+5,8);MIR_interp_arr(ctx,imptr,r,2,pv);if(r[0].i!=pw||abi_c_pointer(jp+5,8)!=pw)failures++;memset(jp,0xa5,sizeof jp);if(call_pointer(MIR_gen(ctx,imptr),jp+5,8)!=pw||memcmp(ip,jp,sizeof ip)!=0)failures++;
    for(int k=0;k<5;k++)if(ip[k]!=0xa5||ip[k+13]!=0xa5)failures++;
    MIR_item_t sid=find_item("abi_sign_i32"),zid=find_item("abi_zero_u32"),tid=find_item("abi_raw_u64"),fid=find_item("abi_float_identity"),pid=find_item("abi_pointer_identity");MIR_val_t sv[1],sr[2];sv[0].i=(int64_t)(int32_t)-1234567;MIR_interp_arr(ctx,sid,sr,1,sv);if(sr[0].i!=(int64_t)(int32_t)-1234567||((int64_t(*)(int32_t))MIR_gen(ctx,sid))((int32_t)-1234567)!=(int64_t)(int32_t)-1234567)failures++;
    sv[0].u=UINT32_C(0xf1234567);MIR_interp_arr(ctx,zid,sr,1,sv);if(sr[0].u!=UINT32_C(0xf1234567)||((uint64_t(*)(uint32_t))MIR_gen(ctx,zid))(UINT32_C(0xf1234567))!=UINT32_C(0xf1234567))failures++;
    sv[0].u=UINT64_C(0xf123456789abcdef);MIR_interp_arr(ctx,tid,sr,1,sv);if(sr[0].u!=UINT64_C(0xf123456789abcdef)||((uint64_t(*)(uint64_t))MIR_gen(ctx,tid))(UINT64_C(0xf123456789abcdef))!=UINT64_C(0xf123456789abcdef))failures++;
    sv[0].f=1.25f;MIR_interp_arr(ctx,fid,sr,1,sv);if(sr[0].f!=1.25f||((float(*)(float))MIR_gen(ctx,fid))(1.25f)!=1.25f)failures++;
    sv[0].a=ip;MIR_interp_arr(ctx,pid,sr,1,sv);if(sr[0].a!=ip||((void*(*)(void*))MIR_gen(ctx,pid))(ip)!=ip)failures++;
    MIR_item_t twoc=find_item("abi_two_result_caller");MIR_val_t tv[2]={0};tv[0].i=17;tv[1].d=2.5;double tw=22.0;MIR_interp_arr(ctx,twoc,sr,2,tv);if(sr[0].d!=tw||call_two_result(MIR_gen(ctx,twoc),17,2.5)!=tw)failures++;
    if(emit_rows)printf("{\"case\":\"internal_and_import_calls\",\"seed\":%d,\"internal_expected\":\"%" PRId64 "\",\"internal_observed\":\"%" PRId64 "\",\"import_integer_expected\":\"%" PRId64 "\",\"import_integer_observed\":\"%" PRId64 "\",\"mixed_expected\":%.17g,\"mixed_observed\":%.17g}\n",seed,expected,got,cexpected,call8_i64(MIR_gen(ctx,imp),seed,0),mw,call8_mixed(MIR_gen(ctx,impm),seed));
  }
  if(emit_rows)fprintf(stderr,"PASS ABI matrix=%d shapes (%d confirmatory, %d exploratory) x 5 seeds; call graph/import seeds=3 failures=%d\n",ABI_CASE_COUNT,ABI_CONFIRMATORY_COUNT,ABI_CASE_COUNT-ABI_CONFIRMATORY_COUNT,failures);
  return failures?1:0;
}
static int emit_artifact(const char *kind,const char *path) {
  void *buf=NULL;size_t size=0;struct MIR_object_exec_params params={0};const char *needed[]={"libc.so.6"};int rc;
  MIR_module_t m; MIR_item_t item;
  for(m=DLIST_HEAD(MIR_module_t,*MIR_get_module_list(ctx));m;m=DLIST_NEXT(MIR_module_t,m))MIR_load_module(ctx,m);
  MIR_load_external(ctx,"abi_c_integer8",(void*)abi_c_integer8);MIR_load_external(ctx,"abi_c_mixed",(void*)abi_c_mixed);MIR_load_external(ctx,"abi_c_pointer",(void*)abi_c_pointer);
  MIR_gen_init(ctx);MIR_gen_set_object_mode(ctx,1);MIR_link(ctx,MIR_set_gen_interface,NULL);
  for(m=DLIST_HEAD(MIR_module_t,*MIR_get_module_list(ctx));m;m=DLIST_NEXT(MIR_module_t,m))
    for(item=DLIST_HEAD(MIR_item_t,m->items);item;item=DLIST_NEXT(MIR_item_t,item))
      if(item->item_type==MIR_func_item)(void)MIR_gen(ctx,item);
  if(!strcmp(kind,"object"))rc=MIR_gen_object_emit(ctx,&buf,&size);
  else {params.shared_p=1;params.needed=needed;params.n_needed=1;rc=MIR_gen_object_emit_executable(ctx,&params,&buf,&size);}
  if(rc||!buf){fprintf(stderr,"native emission failed rc=%d\n",rc);return 40;}
  FILE *f=fopen(path,"wb");if(!f)return 41;if(fwrite(buf,1,size,f)!=size||fclose(f))return 42;
  printf("artifact=%s bytes=%zu\n",kind,size);free(buf);MIR_gen_finish(ctx);return 0;
}
static int load_object(const char *path) {
  FILE *f=fopen(path,"rb");if(!f)return 50;fseek(f,0,SEEK_END);long n=ftell(f);fseek(f,0,SEEK_SET);char *b=malloc((size_t)n);if(!b)return 51;fread(b,1,(size_t)n,f);fclose(f);
  char err[512]={0};MIR_object_loaded_t lo=MIR_object_load(b,(size_t)n,resolver,NULL,err,sizeof err);if(!lo){fprintf(stderr,"MIR_object_load: %s\n",err);free(b);return 52;}int failures=0;
  for(int i=0;i<ABI_CASE_COUNT;i++)for(int seed=0;seed<3;seed++){void *sym=MIR_object_loaded_sym(lo,abi_cases[i].name);int64_t iv=0;double dv=0;abi_run_dispatch(i,sym,seed,&iv,&dv);if(abi_cases[i].returns_double?dv!=abi_oracle_double_dispatch(i,seed):iv!=abi_oracle_int_dispatch(i,seed))failures++;}
  {int64_t want=expected_internal(2),got=call8_i64(MIR_object_loaded_sym(lo,"abi_internal_caller"),2,0);if(got!=want){fprintf(stderr,"loader internal got=%" PRId64 " expected=%" PRId64 "\n",got,want);failures++;}}
  {int64_t want=abi_c_integer8(1,2,3,4,5,6,7,8),got=call8_i64(MIR_object_loaded_sym(lo,"abi_import_integer8"),0,0);if(got!=want){fprintf(stderr,"loader import integer got=%" PRId64 " expected=%" PRId64 "\n",got,want);failures++;}}
  {double want=abi_c_mixed(1,1,3,2,5,3,7,4),got=call8_mixed(MIR_object_loaded_sym(lo,"abi_import_mixed"),0);if(got!=want){fprintf(stderr,"loader import mixed got=%.17g expected=%.17g\n",got,want);failures++;}}
  {uint8_t b[18];memset(b,0xa5,sizeof b);int64_t want=abi_c_pointer(b+5,8),got=call_pointer(MIR_object_loaded_sym(lo,"abi_import_pointer"),b+5,8);if(got!=want){fprintf(stderr,"loader import pointer got=%" PRId64 " expected=%" PRId64 "\n",got,want);failures++;}for(int j=0;j<5;j++)if(b[j]!=0xa5||b[13+j]!=0xa5){fprintf(stderr,"loader pointer canary changed at %d\n",j);failures++;}}
  {double want=22.0,got=call_two_result(MIR_object_loaded_sym(lo,"abi_two_result_caller"),17,2.5);if(got!=want){fprintf(stderr,"loader multi-return got=%.17g expected=%.17g\n",got,want);failures++;}}
  MIR_object_loaded_unload(lo);free(b);printf("MIR_object_load signatures=%d failures=%d\n",ABI_CASE_COUNT,failures);return failures?53:0;
}
static int read_text(const char *path) {FILE*f=fopen(path,"rb");if(!f)return 60;fseek(f,0,SEEK_END);long n=ftell(f);fseek(f,0,SEEK_SET);char*s=malloc((size_t)n+1);fread(s,1,(size_t)n,f);fclose(f);s[n]=0;ctx=MIR_init();MIR_scan_string(ctx,s);free(s);return 0;}
int main(int argc,char **argv) {
  int rc=0;
  if(argc==3&&!strcmp(argv[1],"--text")){if(read_text(argv[2]))return 60;load_and_link();rc=run_semantics(1);MIR_gen_finish(ctx);MIR_finish(ctx);return rc;}
  if(argc==3&&!strcmp(argv[1],"--binary")){FILE*f=fopen(argv[2],"rb");if(!f)return 61;ctx=MIR_init();MIR_read(ctx,f);fclose(f);load_and_link();rc=run_semantics(1);MIR_gen_finish(ctx);MIR_finish(ctx);return rc;}
  if(argc==3&&!strcmp(argv[1],"--object")){build_program();return emit_artifact("object",argv[2]);}
  if(argc==3&&!strcmp(argv[1],"--shared")){build_program();return emit_artifact("shared",argv[2]);}
  if(argc==3&&(!strcmp(argv[1],"--load-object")||!strcmp(argv[1],"--load-object-missing-import"))){if(!strcmp(argv[1],"--load-object-missing-import"))resolver_drop="abi_c_mixed";return load_object(argv[2]);}
  if(argc==4&&!strcmp(argv[1],"--generate")){build_program();save_files(argv[2],argv[3]);MIR_finish(ctx);return 0;}
  if(argc==2&&!strcmp(argv[1],"--run")){build_program();load_and_link();rc=run_semantics(1);MIR_gen_finish(ctx);MIR_finish(ctx);return rc;}
  fprintf(stderr,"usage: %s --generate text.mir program.bmir | --run | --text file | --binary file | --object out.o | --shared out.so | --load-object out.o\n",argv[0]);return 2;
}
