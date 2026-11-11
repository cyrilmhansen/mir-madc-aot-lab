/* Bounded direct MIR differential corpus. This links to libmir.a directly and
   does not use the MADC frontend. */
#include "mir.h"
#include "mir-gen.h"
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct { const char *name; MIR_insn_code_t code; int kind; } Op;
static const Op ops[] = {
  {"add", MIR_ADD, 0}, {"sub", MIR_SUB, 1}, {"mul", MIR_MUL, 2},
  {"div", MIR_DIV, 3}, {"mod", MIR_MOD, 4}, {"and", MIR_AND, 5},
  {"or", MIR_OR, 6}, {"xor", MIR_XOR, 7}, {"lsh", MIR_LSH, 8},
  {"rsh", MIR_RSH, 9}, {"ursh", MIR_URSH, 10}, {"eq", MIR_EQ, 11},
  {"lt", MIR_LT, 12}, {"ult", MIR_ULT, 13}, {"ge", MIR_GE, 14},
  {"uge", MIR_UGE, 15}, {"ext8", MIR_EXT8, 16}, {"uext8", MIR_UEXT8, 17}
};
typedef struct { const char *name; MIR_insn_code_t code; int kind; } FOp;
static const FOp fops[] = {{"dadd",MIR_DADD,0},{"dsub",MIR_DSUB,1},{"dmul",MIR_DMUL,2},
  {"ddiv",MIR_DDIV,3},{"deq",MIR_DEQ,4},{"dlt",MIR_DLT,5},{"dge",MIR_DGE,6}};
static const double fpairs[][2]={{1.5,2.0},{5.0,2.0},{-3.25,0.5},{0.0,3.0},
  {100.0,4.0},{-8.0,0.5},{0.5,2.0},{-1.5,-2.0}};
static const int64_t pairs[][2] = {
  {0,0},{1,0},{-1,1},{1,-1},{2,3},{-7,3},{7,-3},{17,5},
  {INT32_MAX,1},{INT32_MIN,-1},{INT64_MAX/4,3},{INT64_MIN/4,-3},
  {0x5555555555555555LL,1},{0x3333333333333333LL,4},{-16,2},{16,-2}
};

static uint64_t expected(const Op *op, int64_t a, int64_t b) {
  uint64_t ua = (uint64_t)a, ub = (uint64_t)b;
  switch (op->kind) {
  case 0: return (uint64_t)(a+b); case 1: return (uint64_t)(a-b);
  case 2: return ua*ub; case 3: return (uint64_t)(a/b);
  case 4: return (uint64_t)(a%b); case 5: return ua&ub;
  case 6: return ua|ub; case 7: return ua^ub;
  case 8: return ua << (unsigned)b;
  case 9: { unsigned n=(unsigned)b; uint64_t v=ua>>n; return a<0 && n ? v | (UINT64_MAX << (64-n)) : v; }
  case 10: return ua >> (unsigned)b; case 11: return a==b;
  case 12: return a<b; case 13: return ua<ub; case 14: return a>=b;
  case 15: return ua>=ub; case 16: return (uint64_t)(int64_t)(int8_t)a;
  case 17: return (uint64_t)(uint8_t)a; default: abort();
  }
}

static MIR_item_t find_func(MIR_context_t ctx, const char *name) {
  MIR_module_t m; MIR_item_t it;
  for (m=DLIST_HEAD(MIR_module_t,*MIR_get_module_list(ctx)); m; m=DLIST_NEXT(MIR_module_t,m))
    for (it=DLIST_HEAD(MIR_item_t,m->items); it; it=DLIST_NEXT(MIR_item_t,it))
      if (it->item_type==MIR_func_item && strcmp(MIR_item_name(ctx,it),name)==0) return it;
  return NULL;
}

static MIR_context_t construct(void) {
  MIR_context_t ctx=MIR_init(); MIR_type_t rt=MIR_T_I64; size_t i,j;
  MIR_new_module(ctx,"direct_corpus");
  for (i=0;i<sizeof ops/sizeof ops[0];i++) for (j=0;j<sizeof pairs/sizeof pairs[0];j++) {
    char name[48], aname[24], bname[24];
    snprintf(name,sizeof name,"case_%s_%02zu",ops[i].name,j);
    snprintf(aname,sizeof aname,"a"); snprintf(bname,sizeof bname,"b");
    MIR_item_t f=MIR_new_func(ctx,name,1,&rt,2,MIR_T_I64,aname,MIR_T_I64,bname);
    MIR_reg_t a=MIR_reg(ctx,aname,f->u.func), b=MIR_reg(ctx,bname,f->u.func);
    MIR_reg_t r=MIR_new_func_reg(ctx,f->u.func,MIR_T_I64,"r");
    if (ops[i].kind>=16)
      MIR_append_insn(ctx,f,MIR_new_insn(ctx,ops[i].code,MIR_new_reg_op(ctx,r),MIR_new_reg_op(ctx,a)));
    else
      MIR_append_insn(ctx,f,MIR_new_insn(ctx,ops[i].code,MIR_new_reg_op(ctx,r),MIR_new_reg_op(ctx,a),MIR_new_reg_op(ctx,b)));
    MIR_append_insn(ctx,f,MIR_new_ret_insn(ctx,1,MIR_new_reg_op(ctx,r)));
    MIR_finish_func(ctx);
  }
  for (i=0;i<sizeof fops/sizeof fops[0];i++) for (j=0;j<sizeof fpairs/sizeof fpairs[0];j++) {
    char name[48]; MIR_type_t argtype=MIR_T_D;
    MIR_type_t restype=fops[i].kind<4?MIR_T_D:MIR_T_I64;
    snprintf(name,sizeof name,"f64_%s_%02zu",fops[i].name,j);
    MIR_item_t f=MIR_new_func(ctx,name,1,&restype,2,argtype,"a",argtype,"b");
    MIR_reg_t a=MIR_reg(ctx,"a",f->u.func), b=MIR_reg(ctx,"b",f->u.func);
    MIR_reg_t r=MIR_new_func_reg(ctx,f->u.func,restype,"r");
    MIR_append_insn(ctx,f,MIR_new_insn(ctx,fops[i].code,MIR_new_reg_op(ctx,r),MIR_new_reg_op(ctx,a),MIR_new_reg_op(ctx,b)));
    MIR_append_insn(ctx,f,MIR_new_ret_insn(ctx,1,MIR_new_reg_op(ctx,r)));
    MIR_finish_func(ctx);
  }
  MIR_finish_module(ctx); return ctx;
}

static int run(MIR_context_t ctx, int jit, int emit) {
  size_t i,j,count=0; MIR_module_t m; MIR_item_t it;
  for (m=DLIST_HEAD(MIR_module_t,*MIR_get_module_list(ctx));m;m=DLIST_NEXT(MIR_module_t,m)) MIR_load_module(ctx,m);
  if (jit) { MIR_gen_init(ctx); MIR_link(ctx,MIR_set_gen_interface,NULL); }
  for (i=0;i<sizeof ops/sizeof ops[0];i++) for (j=0;j<sizeof pairs/sizeof pairs[0];j++) {
    char name[48]; snprintf(name,sizeof name,"case_%s_%02zu",ops[i].name,j);
    it=find_func(ctx,name); if (!it) return 10;
    int64_t a=pairs[j][0], b=pairs[j][1];
    if (ops[i].kind==8 || ops[i].kind==9 || ops[i].kind==10) b=(int64_t)((uint64_t)b & 63u);
    if ((ops[i].kind==3 || ops[i].kind==4) && b==0) b=1;
    uint64_t want=expected(&ops[i],a,b), got_interp=0, got_jit=0;
    MIR_val_t args[2],res[1]; args[0].i=a; args[1].i=b;
    MIR_interp_arr(ctx,it,res,2,args); got_interp=res[0].u;
    if (jit) { typedef int64_t (*fn_t)(int64_t,int64_t); fn_t fn=(fn_t)MIR_gen(ctx,it); got_jit=(uint64_t)fn(a,b); }
    if (got_interp!=want || (jit && got_jit!=want)) {
      fprintf(stderr,"mismatch %s a=%" PRId64 " b=%" PRId64 " want=%" PRIu64 " interp=%" PRIu64 " jit=%" PRIu64 "\n",name,a,b,want,got_interp,got_jit); return 11;
    }
    if (emit) printf("{\"case\":\"%s\",\"a\":\"%" PRId64 "\",\"b\":\"%" PRId64 "\",\"expected_u64\":\"%" PRIu64 "\",\"interp_u64\":\"%" PRIu64 "\",\"jit_u64\":\"%" PRIu64 "\"}\n",name,a,b,want,got_interp,got_jit);
    count++;
  }
  for (i=0;i<sizeof fops/sizeof fops[0];i++) for (j=0;j<sizeof fpairs/sizeof fpairs[0];j++) {
    char name[48]; snprintf(name,sizeof name,"f64_%s_%02zu",fops[i].name,j);
    it=find_func(ctx,name); if (!it) return 12;
    double a=fpairs[j][0],b=fpairs[j][1],want=0.0,got=0.0; int64_t want_i=0,got_i=0;
    switch(fops[i].kind){case 0:want=a+b;break;case 1:want=a-b;break;case 2:want=a*b;break;case 3:want=a/b;break;case 4:want_i=a==b;break;case 5:want_i=a<b;break;case 6:want_i=a>=b;break;}
    MIR_val_t args[2],res[1]; args[0].d=a; args[1].d=b; MIR_interp_arr(ctx,it,res,2,args);
    if(fops[i].kind<4){got=res[0].d;if(jit){typedef double(*fn_t)(double,double);fn_t fn=(fn_t)MIR_gen(ctx,it);double actual=fn(a,b);if(actual!=want){fprintf(stderr,"f64 JIT mismatch %s\n",name);return 13;}}if(got!=want){fprintf(stderr,"f64 interp mismatch %s\n",name);return 14;}}
    else {got_i=res[0].i;if(jit){typedef int64_t(*fn_t)(double,double);fn_t fn=(fn_t)MIR_gen(ctx,it);int64_t actual=fn(a,b);if(actual!=want_i){fprintf(stderr,"f64 compare JIT mismatch %s\n",name);return 15;}}if(got_i!=want_i){fprintf(stderr,"f64 compare interp mismatch %s\n",name);return 16;}}
    if(emit){if(fops[i].kind<4)printf("{\"case\":\"%s\",\"a\":\"%a\",\"b\":\"%a\",\"expected_f64\":\"%a\",\"interp_f64\":\"%a\",\"jit\":\"agree\"}\n",name,a,b,want,got);else printf("{\"case\":\"%s\",\"a\":\"%a\",\"b\":\"%a\",\"expected_i64\":%" PRId64 ",\"interp_i64\":%" PRId64 ",\"jit\":\"agree\"}\n",name,a,b,want_i,got_i);}
    count++;
  }
  if (jit) MIR_gen_finish(ctx);
  fprintf(stderr,"PASS direct MIR cases=%zu interpreters=%zu jit=%s\n",count,count,jit?"yes":"no");
  return 0;
}

int main(int argc,char **argv) {
  MIR_context_t ctx; int rc;
  if (argc==3 && (strcmp(argv[1],"--text")==0 || strcmp(argv[1],"--binary")==0)) {
    FILE *f=fopen(argv[2],"rb"); if(!f)return 20; ctx=MIR_init();
    if(strcmp(argv[1],"--binary")==0) MIR_read(ctx,f);
    else { long n; char *buf; if(fseek(f,0,SEEK_END) || (n=ftell(f))<0 || fseek(f,0,SEEK_SET)) return 21;
      buf=malloc((size_t)n+1); if(!buf || fread(buf,1,(size_t)n,f)!=(size_t)n)return 22; buf[n]=0;
      MIR_scan_string(ctx,buf); free(buf); }
    fclose(f); rc=run(ctx,1,1);
  } else {
    ctx=construct(); rc=run(ctx,1,1);
    if (!rc && argc==3) {
      FILE *f=fopen(argv[1],"wb"); if(!f)return 23; MIR_output(ctx,f); fclose(f);
      f=fopen(argv[2],"wb"); if(!f)return 24; MIR_write(ctx,f); fclose(f);
    }
  }
  MIR_finish(ctx); return rc;
}
