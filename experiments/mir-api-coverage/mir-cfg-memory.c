/* Direct MIR control-flow and memory differential tests. No MADC frontend. */
#include "mir.h"
#include "mir-gen.h"
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define APP(f, x) MIR_append_insn(ctx, (f), (x))
#define R(n) MIR_new_reg_op(ctx, (n))
#define I(n) MIR_new_int_op(ctx, (n))
#define L(n) MIR_new_label_op(ctx, (n))
static MIR_context_t ctx;
static MIR_type_t i64=MIR_T_I64;

static MIR_item_t fn2(const char *name) { return MIR_new_func(ctx,name,1,&i64,2,MIR_T_I64,"x",MIR_T_I64,"y"); }
static MIR_reg_t arg(MIR_item_t f,const char *n) { return MIR_reg(ctx,n,f->u.func); }
static MIR_reg_t local(MIR_item_t f,const char *n) { return MIR_new_func_reg(ctx,f->u.func,MIR_T_I64,n); }
static void finish(MIR_item_t f) { (void)f; MIR_finish_func(ctx); }

static MIR_item_t make_diamond(const char *name) {
  MIR_item_t f=fn2(name); MIR_reg_t x=arg(f,"x"),r=local(f,"r"); MIR_label_t neg=MIR_new_label(ctx),done=MIR_new_label(ctx);
  APP(f,MIR_new_insn(ctx,MIR_BLT,L(neg),R(x),I(0)));
  APP(f,MIR_new_insn(ctx,MIR_ADD,R(r),R(x),I(10)));
  APP(f,MIR_new_insn(ctx,MIR_JMP,L(done)));
  APP(f,neg);
  APP(f,MIR_new_insn(ctx,MIR_SUB,R(r),I(0),R(x)));
  APP(f,done); APP(f,MIR_new_ret_insn(ctx,1,R(r))); finish(f); return f;
}
static MIR_item_t make_multiway(void) {
  MIR_item_t f=fn2("cfg_multiway"); MIR_reg_t x=arg(f,"x"),r=local(f,"r"); MIR_label_t neg=MIR_new_label(ctx),mid=MIR_new_label(ctx),done=MIR_new_label(ctx);
  APP(f,MIR_new_insn(ctx,MIR_BLT,L(neg),R(x),I(0)));
  APP(f,MIR_new_insn(ctx,MIR_BLT,L(mid),R(x),I(5)));
  APP(f,MIR_new_insn(ctx,MIR_MOV,R(r),I(2))); APP(f,MIR_new_insn(ctx,MIR_JMP,L(done)));
  APP(f,mid); APP(f,MIR_new_insn(ctx,MIR_MOV,R(r),I(0))); APP(f,MIR_new_insn(ctx,MIR_JMP,L(done)));
  APP(f,neg); APP(f,MIR_new_insn(ctx,MIR_MOV,R(r),I(-2)));
  APP(f,done); APP(f,MIR_new_ret_insn(ctx,1,R(r))); finish(f); return f;
}
static MIR_item_t make_count_loop(void) {
  MIR_item_t f=fn2("cfg_count_loop"); MIR_reg_t x=arg(f,"x"),i=local(f,"i"); MIR_label_t loop=MIR_new_label(ctx),done=MIR_new_label(ctx);
  APP(f,MIR_new_insn(ctx,MIR_MOV,R(i),I(0))); APP(f,loop);
  APP(f,MIR_new_insn(ctx,MIR_BGE,L(done),R(i),R(x)));
  APP(f,MIR_new_insn(ctx,MIR_ADD,R(i),R(i),I(1))); APP(f,MIR_new_insn(ctx,MIR_JMP,L(loop)));
  APP(f,done); APP(f,MIR_new_ret_insn(ctx,1,R(i))); finish(f); return f;
}
static MIR_item_t make_accum_loop(void) {
  MIR_item_t f=fn2("cfg_accum_loop"); MIR_reg_t x=arg(f,"x"),i=local(f,"i"),s=local(f,"s"); MIR_label_t loop=MIR_new_label(ctx),done=MIR_new_label(ctx);
  APP(f,MIR_new_insn(ctx,MIR_MOV,R(i),I(0))); APP(f,MIR_new_insn(ctx,MIR_MOV,R(s),I(0))); APP(f,loop);
  APP(f,MIR_new_insn(ctx,MIR_BGE,L(done),R(i),R(x)));
  APP(f,MIR_new_insn(ctx,MIR_ADD,R(s),R(s),R(i))); APP(f,MIR_new_insn(ctx,MIR_ADD,R(i),R(i),I(1)));
  APP(f,MIR_new_insn(ctx,MIR_JMP,L(loop))); APP(f,done); APP(f,MIR_new_ret_insn(ctx,1,R(s))); finish(f); return f;
}
static MIR_item_t make_nested_if(void) {
  MIR_item_t f=fn2("cfg_nested_if"); MIR_reg_t x=arg(f,"x"),r=local(f,"r");
  MIR_label_t neg=MIR_new_label(ctx),smallneg=MIR_new_label(ctx),pos=MIR_new_label(ctx),done=MIR_new_label(ctx);
  APP(f,MIR_new_insn(ctx,MIR_BLT,L(neg),R(x),I(0))); APP(f,MIR_new_insn(ctx,MIR_BGT,L(pos),R(x),I(5)));
  APP(f,MIR_new_insn(ctx,MIR_MOV,R(r),I(3))); APP(f,MIR_new_insn(ctx,MIR_JMP,L(done)));
  APP(f,pos); APP(f,MIR_new_insn(ctx,MIR_MOV,R(r),I(4))); APP(f,MIR_new_insn(ctx,MIR_JMP,L(done)));
  APP(f,neg); APP(f,MIR_new_insn(ctx,MIR_BLT,L(smallneg),R(x),I(-5)));
  APP(f,MIR_new_insn(ctx,MIR_MOV,R(r),I(1))); APP(f,MIR_new_insn(ctx,MIR_JMP,L(done)));
  APP(f,smallneg); APP(f,MIR_new_insn(ctx,MIR_MOV,R(r),I(2))); APP(f,done);
  APP(f,MIR_new_ret_insn(ctx,1,R(r))); finish(f); return f;
}
static MIR_item_t make_nested_loops(void) {
  MIR_item_t f=fn2("cfg_nested_loops"); MIR_reg_t x=arg(f,"x"),y=arg(f,"y"),i=local(f,"i"),j=local(f,"j"),s=local(f,"s");
  MIR_label_t outer=MIR_new_label(ctx),inner=MIR_new_label(ctx),next=MIR_new_label(ctx),done=MIR_new_label(ctx);
  APP(f,MIR_new_insn(ctx,MIR_MOV,R(i),I(0))); APP(f,MIR_new_insn(ctx,MIR_MOV,R(s),I(0))); APP(f,outer);
  APP(f,MIR_new_insn(ctx,MIR_BGE,L(done),R(i),R(x))); APP(f,MIR_new_insn(ctx,MIR_MOV,R(j),I(0))); APP(f,inner);
  APP(f,MIR_new_insn(ctx,MIR_BGE,L(next),R(j),R(y)));
  APP(f,MIR_new_insn(ctx,MIR_ADD,R(s),R(s),R(i))); APP(f,MIR_new_insn(ctx,MIR_ADD,R(s),R(s),R(j)));
  APP(f,MIR_new_insn(ctx,MIR_ADD,R(j),R(j),I(1))); APP(f,MIR_new_insn(ctx,MIR_JMP,L(inner)));
  APP(f,next); APP(f,MIR_new_insn(ctx,MIR_ADD,R(i),R(i),I(1))); APP(f,MIR_new_insn(ctx,MIR_JMP,L(outer)));
  APP(f,done); APP(f,MIR_new_ret_insn(ctx,1,R(s))); finish(f); return f;
}
static MIR_item_t make_early_returns(void) {
  MIR_item_t f=fn2("cfg_early_returns"); MIR_reg_t x=arg(f,"x");
  MIR_label_t zero=MIR_new_label(ctx),high=MIR_new_label(ctx),done=MIR_new_label(ctx);
  APP(f,MIR_new_insn(ctx,MIR_BLT,L(done),R(x),I(0)));
  APP(f,MIR_new_insn(ctx,MIR_BEQ,L(zero),R(x),I(0)));
  APP(f,MIR_new_insn(ctx,MIR_BLT,L(high),R(x),I(10)));
  APP(f,MIR_new_ret_insn(ctx,1,I(2))); APP(f,high); APP(f,MIR_new_ret_insn(ctx,1,I(1)));
  APP(f,zero); APP(f,MIR_new_ret_insn(ctx,1,I(0))); APP(f,done); APP(f,MIR_new_ret_insn(ctx,1,I(-1))); finish(f); return f;
}
static MIR_item_t make_signed_unsigned(void) {
  MIR_item_t f=fn2("cfg_signed_unsigned"); MIR_reg_t x=arg(f,"x"),r=local(f,"r"),s=local(f,"s"),o=local(f,"o");
  MIR_label_t sn=MIR_new_label(ctx),sd=MIR_new_label(ctx),un=MIR_new_label(ctx),ud=MIR_new_label(ctx),done=MIR_new_label(ctx);
  APP(f,MIR_new_insn(ctx,MIR_BLT,L(sn),R(x),I(0))); APP(f,MIR_new_insn(ctx,MIR_MOV,R(r),I(0))); APP(f,MIR_new_insn(ctx,MIR_JMP,L(sd)));
  APP(f,sn); APP(f,MIR_new_insn(ctx,MIR_MOV,R(r),I(1))); APP(f,sd);
  APP(f,MIR_new_insn(ctx,MIR_UBLT,L(un),R(x),MIR_new_uint_op(ctx,UINT64_C(0x8000000000000000))));
  APP(f,MIR_new_insn(ctx,MIR_MOV,R(s),I(0))); APP(f,MIR_new_insn(ctx,MIR_JMP,L(ud)));
  APP(f,un); APP(f,MIR_new_insn(ctx,MIR_MOV,R(s),I(1))); APP(f,ud);
  APP(f,MIR_new_insn(ctx,MIR_MUL,R(o),R(s),I(2))); APP(f,MIR_new_insn(ctx,MIR_ADD,R(o),R(o),R(r)));
  APP(f,done); APP(f,MIR_new_ret_insn(ctx,1,R(o))); finish(f); return f;
}
static MIR_item_t make_equiv(const char *name,int reversed) {
  MIR_item_t f=fn2(name); MIR_reg_t x=arg(f,"x"),r=local(f,"r"); MIR_label_t low=MIR_new_label(ctx),high=MIR_new_label(ctx),done=MIR_new_label(ctx);
  if(!reversed){APP(f,MIR_new_insn(ctx,MIR_BLT,L(low),R(x),I(0)));APP(f,MIR_new_insn(ctx,MIR_BGT,L(high),R(x),I(10)));APP(f,MIR_new_insn(ctx,MIR_MOV,R(r),R(x)));APP(f,MIR_new_insn(ctx,MIR_JMP,L(done)));}
  else {APP(f,MIR_new_insn(ctx,MIR_BGT,L(high),R(x),I(10)));APP(f,MIR_new_insn(ctx,MIR_BGE,L(low),R(x),I(0)));APP(f,MIR_new_insn(ctx,MIR_MOV,R(r),I(0)));APP(f,MIR_new_insn(ctx,MIR_JMP,L(done)));}
  if(!reversed){APP(f,low);APP(f,MIR_new_insn(ctx,MIR_MOV,R(r),I(0)));APP(f,MIR_new_insn(ctx,MIR_JMP,L(done)));APP(f,high);APP(f,MIR_new_insn(ctx,MIR_MOV,R(r),I(10)));}
  else {APP(f,high);APP(f,MIR_new_insn(ctx,MIR_MOV,R(r),I(10)));APP(f,MIR_new_insn(ctx,MIR_JMP,L(done)));APP(f,low);APP(f,MIR_new_insn(ctx,MIR_MOV,R(r),R(x)));}
  APP(f,done);APP(f,MIR_new_ret_insn(ctx,1,R(r)));finish(f);return f;
}

static MIR_item_t memfn(const char *name) { return MIR_new_func(ctx,name,1,&i64,3,MIR_T_P,"p",MIR_T_I64,"x",MIR_T_I64,"y"); }
static MIR_item_t make_mem(const char *name,int mode,int scale) {
  MIR_item_t f=memfn(name); MIR_reg_t p=arg(f,"p"),x=arg(f,"x"),y=arg(f,"y"),r=local(f,"r");
  if(mode==0){APP(f,MIR_new_insn(ctx,MIR_MOV,R(r),MIR_new_mem_op(ctx,MIR_T_I64,0,p,0,0)));}
  else if(mode==1){APP(f,MIR_new_insn(ctx,MIR_MOV,MIR_new_mem_op(ctx,MIR_T_I64,0,p,0,0),R(x)));APP(f,MIR_new_insn(ctx,MIR_MOV,R(r),MIR_new_mem_op(ctx,MIR_T_I64,0,p,0,0)));}
  else if(mode==2){APP(f,MIR_new_insn(ctx,MIR_MOV,R(r),MIR_new_mem_op(ctx,MIR_T_I64,0,p,y,(MIR_scale_t)scale)));}
  else if(mode==3){APP(f,MIR_new_insn(ctx,MIR_MOV,R(r),MIR_new_mem_op(ctx,MIR_T_I8,1,p,0,0)));}
  else if(mode==4){APP(f,MIR_new_insn(ctx,MIR_MOV,R(r),MIR_new_mem_op(ctx,MIR_T_U8,1,p,0,0)));}
  else if(mode==5){APP(f,MIR_new_insn(ctx,MIR_MOV,MIR_new_mem_op(ctx,MIR_T_I8,1,p,0,0),R(x)));APP(f,MIR_new_insn(ctx,MIR_MOV,R(r),MIR_new_mem_op(ctx,MIR_T_U8,1,p,0,0)));}
  else if(mode==6){APP(f,MIR_new_insn(ctx,MIR_MOV,MIR_new_mem_op(ctx,MIR_T_I64,8,p,0,0),R(x)));APP(f,MIR_new_insn(ctx,MIR_MOV,R(r),MIR_new_mem_op(ctx,MIR_T_U8,8,p,0,0)));}
  else if(mode==7){MIR_reg_t i=local(f,"i"),v=local(f,"v"),s=local(f,"s");MIR_label_t loop=MIR_new_label(ctx),done=MIR_new_label(ctx);APP(f,MIR_new_insn(ctx,MIR_MOV,R(i),I(0)));APP(f,MIR_new_insn(ctx,MIR_MOV,R(s),I(0)));APP(f,loop);APP(f,MIR_new_insn(ctx,MIR_BGE,L(done),R(i),R(x)));APP(f,MIR_new_insn(ctx,MIR_MOV,R(v),MIR_new_mem_op(ctx,MIR_T_I64,0,p,i,8)));APP(f,MIR_new_insn(ctx,MIR_ADD,R(v),R(v),I(1)));APP(f,MIR_new_insn(ctx,MIR_MOV,MIR_new_mem_op(ctx,MIR_T_I64,0,p,i,8),R(v)));APP(f,MIR_new_insn(ctx,MIR_ADD,R(s),R(s),R(v)));APP(f,MIR_new_insn(ctx,MIR_ADD,R(i),R(i),I(1)));APP(f,MIR_new_insn(ctx,MIR_JMP,L(loop)));APP(f,done);APP(f,MIR_new_insn(ctx,MIR_MOV,R(r),R(s)));}
  else if(mode==9){APP(f,MIR_new_insn(ctx,MIR_MOV,R(r),MIR_new_mem_op(ctx,MIR_T_I16,2,p,0,0)));}
  else if(mode==10){APP(f,MIR_new_insn(ctx,MIR_MOV,R(r),MIR_new_mem_op(ctx,MIR_T_U16,2,p,0,0)));}
  else if(mode==11){APP(f,MIR_new_insn(ctx,MIR_MOV,R(r),MIR_new_mem_op(ctx,MIR_T_I32,4,p,0,0)));}
  else if(mode==12){APP(f,MIR_new_insn(ctx,MIR_MOV,R(r),MIR_new_mem_op(ctx,MIR_T_U32,4,p,0,0)));}
  else if(mode==13){APP(f,MIR_new_insn(ctx,MIR_MOV,MIR_new_mem_op(ctx,MIR_T_I16,2,p,0,0),R(x)));APP(f,MIR_new_insn(ctx,MIR_MOV,R(r),MIR_new_mem_op(ctx,MIR_T_U16,2,p,0,0)));}
  else if(mode==14){APP(f,MIR_new_insn(ctx,MIR_MOV,MIR_new_mem_op(ctx,MIR_T_I32,4,p,0,0),R(x)));APP(f,MIR_new_insn(ctx,MIR_MOV,R(r),MIR_new_mem_op(ctx,MIR_T_U32,4,p,0,0)));}
  else if(mode>=15&&mode<=21){MIR_type_t t=mode>=20?MIR_T_U16:MIR_T_I16;APP(f,MIR_new_insn(ctx,MIR_MOV,R(r),MIR_new_mem_op(ctx,t,0,p,y,(MIR_scale_t)scale)));}
  APP(f,MIR_new_ret_insn(ctx,1,R(r)));finish(f);return f;
}

static MIR_context_t construct(void) {
  ctx=MIR_init(); MIR_new_module(ctx,"cycle43_cfg_memory");
  make_diamond("cfg_diamond");make_multiway();make_count_loop();make_accum_loop();make_nested_if();make_nested_loops();make_early_returns();make_signed_unsigned();make_equiv("cfg_equiv_a",0);make_equiv("cfg_equiv_b",1);
  make_mem("mem_load64",0,0);make_mem("mem_store_reload64",1,0);
  make_mem("mem_index_s1",2,1);make_mem("mem_index_s2",2,2);make_mem("mem_index_s4",2,4);make_mem("mem_index_s8",2,8);
  make_mem("mem_signed_i8",3,0);make_mem("mem_unsigned_u8",4,0);make_mem("mem_store_i8_load_u8",5,0);make_mem("mem_alias64_u8",6,0);make_mem("mem_loop_update",7,8);
  make_mem("mem_signed_i16",9,0);make_mem("mem_unsigned_u16",10,0);make_mem("mem_signed_i32",11,0);make_mem("mem_unsigned_u32",12,0);
  make_mem("mem_store_i16_load_u16",13,0);make_mem("mem_store_i32_load_u32",14,0);
  make_mem("mem_index_i16_s1",15,1);make_mem("mem_index_i16_s2",16,2);make_mem("mem_index_i16_s4",17,4);make_mem("mem_index_i16_s8",18,8);
  make_mem("mem_index_u16_s1",19,1);make_mem("mem_index_u16_s2",20,2);make_mem("mem_index_u16_s4",21,4);
  MIR_new_export(ctx,"cfg_diamond"); MIR_new_export(ctx,"mem_store_reload64");
  MIR_finish_module(ctx);return ctx;
}

static MIR_item_t find_func(MIR_context_t c,const char *name){MIR_module_t m;MIR_item_t it;for(m=DLIST_HEAD(MIR_module_t,*MIR_get_module_list(c));m;m=DLIST_NEXT(MIR_module_t,m))for(it=DLIST_HEAD(MIR_item_t,m->items);it;it=DLIST_NEXT(MIR_item_t,it))if(it->item_type==MIR_func_item&&strcmp(MIR_item_name(c,it),name)==0)return it;return NULL;}
static const int64_t xs[16]={-10,-6,-1,0,1,4,5,6,8,9,10,11,13,16,20,32};
static const int64_t ys[16]={7,6,5,4,3,2,1,0,0,1,2,3,4,5,6,7};
static int64_t bounded(int64_t x){return x<0?0:x>8?8:x;}
static int64_t oracle_cfg(int id,int64_t x,int64_t y){switch(id){case 0:return x<0?-x:x+10;case 1:return x<0?-2:x<5?0:2;case 2:return bounded(x);case 3:{int64_t n=bounded(x);return n*(n-1)/2;}case 4:return x<0?(x< -5?2:1):x>5?4:3;case 5:{int64_t n=bounded(x),m=bounded(y),s=0,i,j;for(i=0;i<n;i++)for(j=0;j<m;j++)s+=i+j;return s;}case 6:return x<0?-1:x==0?0:x<10?1:2;case 7:{uint64_t u=(uint64_t)x;return (x<0?1:0)+2*(u<UINT64_C(0x8000000000000000)?1:0);}case 8:case 9:return x<0?0:x>10?10:x;default:abort();}}

static void initmem(uint8_t *a,int seed){size_t i;memset(a,0xA5,80);uint8_t *p=a+8;for(i=0;i<64;i++)p[i]=(uint8_t)((seed*17+(int)i*13+3)&255);for(i=0;i<4;i++){uint64_t v=(uint64_t)(seed*3+(int)i+1);memcpy(p+i*8,&v,8);}}
static void hexmem(char *out,const uint8_t *p,size_t n){static const char h[]="0123456789abcdef";size_t i;for(i=0;i<n;i++){out[2*i]=h[p[i]>>4];out[2*i+1]=h[p[i]&15];}out[2*n]=0;}
static int64_t load_i16(const uint8_t *p){uint16_t v;memcpy(&v,p,2);return v<UINT16_C(0x8000)?v:(int64_t)v-INT64_C(65536);}
static int64_t load_i32(const uint8_t *p){uint32_t v;memcpy(&v,p,4);return v<UINT32_C(0x80000000)?v:(int64_t)v-INT64_C(4294967296);}
static int64_t oracle_mem(int id,uint8_t *p,int64_t x,int64_t y){uint64_t u;int64_t s;uint8_t b;uint16_t h;uint32_t w;switch(id){case 0:memcpy(&s,p,8);return s;case 1:u=(uint64_t)x;memcpy(p,&u,8);memcpy(&s,p,8);return s;case 2:case 3:case 4:case 5:memcpy(&s,p+y*(id==2?1:id==3?2:id==4?4:8),8);return s;case 6:b=p[1];return b<128?b:(int64_t)b-256;case 7:return p[1];case 8:p[1]=(uint8_t)x;return p[1];case 9:u=(uint64_t)x;memcpy(p+8,&u,8);b=p[8];return b;case 10:{int64_t i,acc=0;for(i=0;i<x;i++){memcpy(&s,p+i*8,8);s++;memcpy(p+i*8,&s,8);acc+=s;}return acc;}case 11:return load_i16(p+2);case 12:memcpy(&h,p+2,2);return h;case 13:return load_i32(p+4);case 14:memcpy(&w,p+4,4);return w;case 15:u=(uint64_t)x;h=(uint16_t)u;memcpy(p+2,&h,2);memcpy(&h,p+2,2);return h;case 16:u=(uint64_t)x;w=(uint32_t)u;memcpy(p+4,&w,4);memcpy(&w,p+4,4);return w;case 17:case 18:case 19:case 20:case 21:case 22:case 23:{size_t off=(size_t)y*(id==17||id==21?1:id==18||id==22?2:id==19||id==23?4:8);if(id>=21){memcpy(&h,p+off,2);return h;}return load_i16(p+off);}default:abort();}}

static int run(MIR_context_t c,int jit,int emit){MIR_module_t m;MIR_item_t f;size_t fam,k,count=0;char hex[161];
  for(m=DLIST_HEAD(MIR_module_t,*MIR_get_module_list(c));m;m=DLIST_NEXT(MIR_module_t,m))MIR_load_module(c,m);
  if(jit){MIR_gen_init(c);MIR_link(c,MIR_set_gen_interface,NULL);}
  const char *cnames[]={"cfg_diamond","cfg_multiway","cfg_count_loop","cfg_accum_loop","cfg_nested_if","cfg_nested_loops","cfg_early_returns","cfg_signed_unsigned","cfg_equiv_a","cfg_equiv_b"};
  const int cid[]={0,1,2,3,4,5,6,7,8,9};
  for(fam=0;fam<10;fam++){f=find_func(c,cnames[fam]);if(!f)return 2;size_t n=(fam==9?0:fam==0?16:12);for(k=0;k<n;k++){int64_t x=xs[k],y=ys[k];if(fam==2||fam==3||fam==5)x=bounded(x);if(fam==5)y=bounded(y);int64_t want=oracle_cfg(cid[fam],x,y),got;MIR_val_t a[2],r[1];a[0].i=x;a[1].i=y;MIR_interp_arr(c,f,r,2,a);got=r[0].i;if(got!=want){fprintf(stderr,"CFG interpreter mismatch %s k=%zu x=%" PRId64 " got=%" PRId64 " want=%" PRId64 "\n",cnames[fam],k,x,got,want);return 3;}int64_t jgot=got;if(jit){typedef int64_t(*g)(int64_t,int64_t);jgot=((g)MIR_gen(c,f))(x,y);if(jgot!=want){fprintf(stderr,"CFG JIT mismatch %s k=%zu\n",cnames[fam],k);return 4;}}if(emit)printf("{\"domain\":\"cfg\",\"case\":\"%s\",\"k\":%zu,\"x\":\"%" PRId64 "\",\"y\":\"%" PRId64 "\",\"expected\":\"%" PRId64 "\",\"interp\":\"%" PRId64 "\",\"jit\":\"%" PRId64 "\"}\n",cnames[fam],k,x,y,want,got,jgot);count++;}}
  /* Equivalent CFGs use the same 12 inputs as cfg_equiv_a. */
  f=find_func(c,"cfg_equiv_b");for(k=0;k<12;k++){int64_t x=xs[k],want=oracle_cfg(9,x,0);MIR_val_t a[2],r[1];a[0].i=x;a[1].i=0;MIR_interp_arr(c,f,r,2,a);int64_t got=r[0].i,jgot=got;if(jit){typedef int64_t(*g)(int64_t,int64_t);jgot=((g)MIR_gen(c,f))(x,0);}if(got!=want||jgot!=want)return 5;if(emit)printf("{\"domain\":\"cfg\",\"case\":\"cfg_equiv_b\",\"k\":%zu,\"x\":\"%" PRId64 "\",\"expected\":\"%" PRId64 "\",\"interp\":\"%" PRId64 "\",\"jit\":\"%" PRId64 "\"}\n",k,x,want,got,jgot);count++;}
  const char *mnames[]={"mem_load64","mem_store_reload64","mem_index_s1","mem_index_s2","mem_index_s4","mem_index_s8","mem_signed_i8","mem_unsigned_u8","mem_store_i8_load_u8","mem_alias64_u8","mem_loop_update","mem_signed_i16","mem_unsigned_u16","mem_signed_i32","mem_unsigned_u32","mem_store_i16_load_u16","mem_store_i32_load_u32","mem_index_i16_s1","mem_index_i16_s2","mem_index_i16_s4","mem_index_i16_s8","mem_index_u16_s1","mem_index_u16_s2","mem_index_u16_s4"};
  const int64_t memory_inputs[]={0,1,127,128,255,256,32767,32768,65535,INT64_C(0x1122334455667788),-1,-128};
  for(fam=0;fam<24;fam++) {
    f=find_func(c,mnames[fam]);
    if(!f)return 6;
    for(k=0;k<12;k++) {
      _Alignas(16) uint8_t a0[80],a1[80],a2[80];
      initmem(a0,(int)k); memcpy(a1,a0,80); memcpy(a2,a0,80);
      int64_t x=memory_inputs[k], y=(int64_t)(k%4);
      int scale=fam==2?1:fam==3?2:fam==4?4:fam==5?8:fam==17?1:fam==18?2:fam==19?4:fam==20?8:fam==21?1:fam==22?2:fam==23?4:0;
      if(scale&&fam>=17) y=(int64_t)(k%4);
      else if(scale) y=(int64_t)(k%4)*(8/scale);
      if(fam==10)x=(int64_t)(k%5);
      int64_t want=oracle_mem((int)fam,a0+8,x,y),got,jgot;
      MIR_val_t a[3],r[1]; a[0].a=a1+8; a[1].i=x; a[2].i=y;
      MIR_interp_arr(c,f,r,3,a); got=r[0].i;
      if(got!=want||memcmp(a0,a1,80)!=0) {
        fprintf(stderr,"MEM interpreter mismatch %s k=%zu got=%" PRId64 " want=%" PRId64 " state=%d\n",mnames[fam],k,got,want,memcmp(a0,a1,80)); return 7;
      }
      jgot=got;
      if(jit) {
        typedef int64_t(*g)(void*,int64_t,int64_t);
        jgot=((g)MIR_gen(c,f))(a2+8,x,y);
        if(jgot!=want||memcmp(a0,a2,80)!=0) {
          fprintf(stderr,"MEM JIT mismatch %s k=%zu got=%" PRId64 " want=%" PRId64 " state=%d\n",mnames[fam],k,jgot,want,memcmp(a0,a2,80)); return 8;
        }
      }
      hexmem(hex,a0+8,64);
      if(emit) printf("{\"domain\":\"memory\",\"case\":\"%s\",\"k\":%zu,\"x\":\"%" PRId64 "\",\"y\":\"%" PRId64 "\",\"expected\":\"%" PRId64 "\",\"interp\":\"%" PRId64 "\",\"jit\":\"%" PRId64 "\",\"memory_hex\":\"%s\",\"canaries_ok\":true}\n",mnames[fam],k,x,y,want,got,jgot,hex);
      count++;
    }
  }
  if(jit) { MIR_gen_finish(c); }
  fprintf(stderr,"PASS cfg_memory cases=%zu interpreter=yes jit=%s\n",count,jit?"yes":"no");return 0;
}

static int read_file(FILE *f,char **out){long n;if(fseek(f,0,SEEK_END)||(n=ftell(f))<0||fseek(f,0,SEEK_SET))return 0;char *p=malloc((size_t)n+1);if(!p||fread(p,1,(size_t)n,f)!=(size_t)n)return 0;p[n]=0;*out=p;return 1;}
int main(int argc,char **argv){MIR_context_t c;int rc;if(argc==3&&(!strcmp(argv[1],"--text")||!strcmp(argv[1],"--binary"))){FILE *f=fopen(argv[2],"rb");if(!f)return 20;c=MIR_init();if(!strcmp(argv[1],"--binary"))MIR_read(c,f);else{char *s;if(!read_file(f,&s))return 21;MIR_scan_string(c,s);free(s);}fclose(f);rc=run(c,1,1);}else if(argc==3&&!strcmp(argv[1],"--emit-object")){MIR_module_t m;void *buf=NULL;size_t n=0;c=construct();for(m=DLIST_HEAD(MIR_module_t,*MIR_get_module_list(c));m;m=DLIST_NEXT(MIR_module_t,m))MIR_load_module(c,m);MIR_gen_init(c);MIR_gen_set_object_mode(c,1);MIR_link(c,MIR_set_gen_interface,NULL);(void)MIR_gen(c,find_func(c,"cfg_diamond"));(void)MIR_gen(c,find_func(c,"mem_store_reload64"));rc=MIR_gen_object_emit(c,&buf,&n);if(rc||!buf){MIR_gen_finish(c);MIR_finish(c);return 24;}FILE *f=fopen(argv[2],"wb");if(!f){free(buf);return 25;}if(fwrite(buf,1,n,f)!=n||fclose(f)!=0)return 26;free(buf);fprintf(stderr,"AOT object bytes=%zu\n",n);MIR_gen_finish(c);MIR_finish(c);return 0;}else{c=construct();if(argc==3){FILE *f=fopen(argv[1],"wb");if(!f)return 22;MIR_output(c,f);fclose(f);f=fopen(argv[2],"wb");if(!f)return 23;MIR_write(c,f);fclose(f);}rc=run(c,1,1);}MIR_finish(c);return rc;}
