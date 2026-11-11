#!/usr/bin/env python3
"""Summarize concrete CFG/opcode coverage from generated MIR and observations."""
import json, pathlib, re, sys
root=pathlib.Path(__file__).resolve().parents[2]
mir=pathlib.Path(sys.argv[1]) if len(sys.argv)>1 else root/'experiments/mir-api-coverage/build/cycle43-final.mir'
res=pathlib.Path(sys.argv[2]) if len(sys.argv)>2 else root/'results/cycle43-mir-cfg-memory/differential-results.jsonl'
out=pathlib.Path(sys.argv[3]) if len(sys.argv)>3 else root/'results/cycle43-mir-cfg-memory'
text=mir.read_text(); functions={}; cur=None
for raw in text.splitlines():
    line=raw.strip()
    if not line or line.startswith('#') or line.split()[0].lower() == 'local': continue
    m=re.match(r'([^:]+):\s*func\b',line)
    if m: cur=m.group(1);functions[cur]=[];continue
    if cur is None: continue
    if line=='endfunc':cur=None;continue
    if line.endswith(':') and re.fullmatch(r'L\d+:',line): functions[cur].append(('LABEL',line[:-1]));continue
    op=line.split()[0].upper(); functions[cur].append((op,line))
branch_ops={'BLT','BGE','BGT','BEQ','UBLT','JMP'}
block_counts={}
for name,insns in functions.items():
    leaders={0} if insns else set()
    labels={v:i for i,(op,v) in enumerate(insns) if op=='LABEL'}
    for i,(op,v) in enumerate(insns):
        if op=='LABEL':leaders.add(i)
        if op in branch_ops or op=='RET':
            if i+1<len(insns):leaders.add(i+1)
    block_counts[name]=len(leaders)
all_ops={op for insns in functions.values() for op,_ in insns if op not in {'LABEL'}}
rows=[json.loads(x) for x in res.read_text().splitlines() if x]
control=sum(x['domain']=='cfg' for x in rows); memory=sum(x['domain']=='memory' for x in rows)
cfg={
 "cases":control,"function_variants":len([n for n in functions if n.startswith('cfg_')]),
 "basic_blocks_by_function":{n:v for n,v in block_counts.items() if n.startswith('cfg_')},
 "conditional_branch_outcomes_from_frozen_spec":{
  "cfg_diamond.BLT_taken_not_taken":[3,13],
  "cfg_multiway.first_BLT_taken_not_taken":[3,9],
  "cfg_multiway.second_BLT_taken_not_taken":[3,6],
  "cfg_count_loop.BGE_exit_taken_not_taken":[12,48],
  "cfg_accum_loop.BGE_exit_taken_not_taken":[12,48],
  "cfg_nested_if.outer_BLT_taken_not_taken":[3,9],
  "cfg_nested_if.nonnegative_BGT_taken_not_taken":[5,4],
  "cfg_nested_if.negative_BLT_taken_not_taken":[2,1],
  "cfg_nested_loops.outer_BGE_exit_taken_not_taken":[12,48],
  "cfg_nested_loops.inner_BGE_exit_taken_not_taken":[48,49],
  "cfg_early_returns.negative_BLT_taken_not_taken":[3,9],
  "cfg_early_returns.zero_BEQ_taken_not_taken":[1,8],
  "cfg_early_returns.lt10_BLT_taken_not_taken":[6,2],
  "cfg_signed_unsigned.signed_BLT_taken_not_taken":[3,9],
  "cfg_signed_unsigned.unsigned_UBLT_taken_not_taken":[9,3],
  "cfg_equiv_a.low_BLT_taken_not_taken":[3,9],
  "cfg_equiv_a.high_BGT_taken_not_taken":[1,11],
  "cfg_equiv_b.high_BGT_taken_not_taken":[1,11],
  "cfg_equiv_b.nonnegative_BGE_taken_not_taken":[8,3]
 },
 "note":"Branch outcome totals are derived from the pre-registered mathematical input/spec table, not hardware branch tracing.",
 "loop_iteration_bound":8
}
mem_tuples=[]
def mem_tuple(operation,element_type,displacement,index=None,scale=None,alignment=None):
    mem_tuples.append({"operation":operation,"element_type":element_type,"displacement_bytes":displacement,"index":index,"scale":scale,"effective_alignment":alignment})
mem_tuple('load','I64',0,alignment=8)
for scale in [1,2,4,8]: mem_tuple('load','I64',0,'y',scale,8)
mem_tuple('load','I8',1,alignment=1); mem_tuple('load','U8',1,alignment=1); mem_tuple('load','U8',8,alignment=1)
mem_tuple('load','I16',2,alignment=2); mem_tuple('load','U16',2,alignment=2)
mem_tuple('load','I32',4,alignment=4); mem_tuple('load','U32',4,alignment=4)
for scale in [1,2,4,8]: mem_tuple('load','I16',0,'y',scale,1 if scale==1 else 2)
for scale in [1,2,4]: mem_tuple('load','U16',0,'y',scale,1 if scale==1 else 2)
mem_tuple('store','I64',0,alignment=8); mem_tuple('store','I8',1,alignment=1); mem_tuple('store','I64',8,alignment=8)
mem_tuple('store','I64',0,'i',8,8); mem_tuple('store','I16',2,alignment=2); mem_tuple('store','I32',4,alignment=4)
mem={"cases":memory,"function_variants":len([n for n in functions if n.startswith('mem_')]),"memory_types":["MIR_T_I8","MIR_T_U8","MIR_T_I16","MIR_T_U16","MIR_T_I32","MIR_T_U32","MIR_T_I64"],"unique_typed_operation_address_tuples":len(mem_tuples),"tuples":mem_tuples,"address_scales_tested":[1,2,4,8],"semantic_families":["aligned direct load","store then reload","indexed I64 loads","signed I8/I16/I32 loads","unsigned U8/U16/U32 loads","narrow store/readback","overlapping I64 store/U8 load","indexed I16/U16 reads","indexed bounded I64 loop update"],"alignment":"I64 accesses are 8-byte aligned in this corpus; I16 indexed scale-1 accesses can be unaligned but remain in bounds and have a memcpy-based C oracle.","canary":"8 bytes on each side and the full 80-byte allocation are compared after each engine"}
cycle42=json.loads((root/'results/cycle42-mir-api-coverage/instruction-coverage.json').read_text())
old_ops={op for sig in cycle42['tested_type_signatures'] for op in sig['instructions']}
cumulative=old_ops|all_ops
cum={"cycle42_unique_opcodes":len(old_ops),"cycle43_opcodes_present":sorted(all_ops),"cycle43_only_new_opcodes":sorted(all_ops-old_ops),"cumulative_unique_opcode_count":len(cumulative),"cumulative_unique_opcodes":sorted(cumulative),"enum_denominator":248,"case_counts":{"cfg":control,"memory":memory,"total":len(rows)}}
out.mkdir(parents=True,exist_ok=True)
(out/'cfg-coverage.json').write_text(json.dumps(cfg,indent=2)+'\n')
(out/'memory-addressing-coverage.json').write_text(json.dumps(mem,indent=2)+'\n')
(out/'opcode-coverage.json').write_text(json.dumps(cum,indent=2)+'\n')
print(json.dumps({'cfg':control,'memory':memory,'opcodes_in_source':len(all_ops),'cumulative_unique':cum['cumulative_unique_opcode_count']}))
