#!/usr/bin/env python3
"""Bounded structural reducer for generated Cycle45 MIR conversion/overflow specs."""
import json, pathlib, subprocess, sys
import re

ROOT=pathlib.Path(__file__).resolve().parents[2]
OUT=ROOT/'results/cycle45-mir-numeric-boundaries'
RUNNER=pathlib.Path(sys.argv[1]).resolve()
OUT.mkdir(parents=True,exist_ok=True)

def render(spec):
    narg=1 if spec['kind']=='conversion' else 2
    args='i64:x' if narg==1 else 'i64:a, i64:b'
    locals=[]
    for op in spec['ops']:
        if op['dst'] not in locals: locals.append(op['dst'])
    if spec['kind']=='conversion':
        ret=spec['ops'][-1]['dst']
        body='\n'.join('  '+o['text'] for o in spec['ops'])
        return f"reduce_mod: module\nreduce_case: func i64, {args}\n  local "+', '.join('i64:'+x for x in locals)+f"\n{body}\n  ret {ret}\n  endfunc\n  endmodule\n"
    result='result'; overflow='ov'
    if result not in locals: locals.append(result)
    if overflow not in locals: locals.append(overflow)
    body='\n'.join('  '+o['text'] for o in spec['ops'])
    body += f"\n  {spec['opcode']} {overflow}, a, b\n  bo overflow\n  mov {result}, 0\n  jmp finish\noverflow:\n  mov {result}, 1\nfinish:\n  ret {result}"
    return f"reduce_mod: module\nreduce_case: func i64, {args}\n  local "+', '.join('i64:'+x for x in locals)+f"\n{body}\n  endfunc\n  endmodule\n"

def observe(spec,tag):
    text=render(spec); mir=OUT/f'{tag}.mir';mir.write_text(text)
    vals=[spec['x']] if spec['kind']=='conversion' else [spec['a'],spec['b']]
    p=subprocess.run([str(RUNNER),str(mir),*map(str,vals)],text=True,capture_output=True,timeout=8)
    if p.returncode: return {'valid':False,'returncode':p.returncode,'stderr':p.stderr,'mir':text}
    got={k:int(v) for k,v in (line.split('=',1) for line in p.stdout.splitlines())}
    expected=spec['expected']
    category=spec['injected_class']
    # Fault is in the test observation comparator, affecting only the requested backend.
    observed=dict(got)
    trigger=(spec['kind']=='conversion' and 'ext8' in text and spec['x']==128) or (spec['kind']=='overflow' and spec['opcode']=='addo' and spec['a']==(1<<63)-1 and spec['b']==1)
    if trigger: observed['jit'] ^= 1
    mismatch=(observed['jit']!=expected and got['interp']==expected)
    return {'valid':True,'returncode':p.returncode,'stdout':p.stdout,'actual':got,'observed':observed,
            'expected':expected,'trigger':trigger,'mismatch':mismatch,'failure_class':category if mismatch else None,'mir':text}

def run_case(spec,tag):
    o=observe(spec,tag)
    if not o['valid'] or not o['mismatch'] or o['failure_class']!=spec['injected_class']:
        raise RuntimeError(f"failure class lost at {tag}: {o}")
    return o

def reduce_spec(spec,name):
    current=json.loads(json.dumps(spec)); steps=[]; run_case(current,name+'-original')
    # Delete unrelated typed operations one at a time; each trial regenerates MIR and runs a fresh process.
    pos=0
    while pos<len(current['ops']):
        trial=json.loads(json.dumps(current))
        removed={trial['ops'][pos]['dst']}; drop={pos}; changed=True
        while changed:
            changed=False
            for k,o in enumerate(trial['ops']):
                if k in drop: continue
                parts=[p.strip() for p in o['text'].split(',')]
                if len(parts)>1 and any(re.search(r'\b'+re.escape(name)+r'\b',','.join(parts[1:])) for name in removed):
                    drop.add(k); removed.add(o['dst']); changed=True
        if any(trial['ops'][k]['text'].split()[0]==spec['required_opcode'] for k in drop): pos+=1; continue
        removed_ops=[trial['ops'][k] for k in sorted(drop)]
        trial['ops']=[o for k,o in enumerate(trial['ops']) if k not in drop]
        try: run_case(trial,name+f'-trial-{len(steps):02}')
        except (RuntimeError,subprocess.TimeoutExpired): pos+=1; continue
        steps.append({'removed':removed_ops,'remaining':len(trial['ops'])})
        current=trial
    final=run_case(current,name+'-reduced')
    (OUT/f'{name}-original-spec.json').write_text(json.dumps(spec,indent=2)+'\n')
    (OUT/f'{name}-reduced-spec.json').write_text(json.dumps(current,indent=2)+'\n')
    (OUT/f'{name}-reduction.json').write_text(json.dumps({'injected':True,'failure_class':spec['injected_class'],'affected_backend':'jit observation comparator','original_ops':len(spec['ops']),'reduced_ops':len(current['ops']),'steps':steps,'fresh_process_reproduction':{'command':'mir-reduce-runner <generated.mir> <inputs>','reduced_observation':{k:final[k] for k in ('actual','observed','expected','failure_class')}},'original_mir':render(spec),'reduced_mir':render(current)},indent=2)+'\n')
    return {'name':name,'failure_class':spec['injected_class'],'original_ops':len(spec['ops']),'reduced_ops':len(current['ops']),'preserved_boundary_opcode':spec['required_opcode'],'fresh_reproduction':final['mismatch']}

cases=[]
conv={'kind':'conversion','x':128,'expected':18446744073709551488,'injected_class':'injected_conversion_boundary_jit_mismatch','required_opcode':'ext8','ops':[{'dst':'n0','text':'add n0, x, 9'},{'dst':'n1','text':'mul n1, n0, 7'},{'dst':'n2','text':'sub n2, n1, 4'},{'dst':'r','text':'ext8 r, x'}]}
# ext8(0x80) is -128 represented as the corresponding i64 bit pattern.
conv['expected']=-128
cases.append(reduce_spec(conv,'injected-conversion'))
ov={'kind':'overflow','a':(1<<63)-1,'b':1,'expected':1,'opcode':'addo','injected_class':'injected_overflow_branch_jit_mismatch','required_opcode':'addo','ops':[{'dst':'n0','text':'add n0, a, 17'},{'dst':'n1','text':'mul n1, b, 9'},{'dst':'n2','text':'sub n2, n0, n1'}]}
cases.append(reduce_spec(ov,'injected-overflow'))
(OUT/'reducer-validation.json').write_text(json.dumps({'method':'typed specification deletion with regenerate-to-MIR and fresh-process interpreter/JIT execution at every accepted step','cases':cases,'injected_faults_are_not_product_findings':True},indent=2)+'\n')
print(json.dumps(cases,indent=2))
