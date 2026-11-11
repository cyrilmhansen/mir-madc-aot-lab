#!/usr/bin/env python3
"""Narrow Cycle46 reducer for a conversion-dependent CFG and pointer memory path."""
import json,pathlib,re,subprocess,sys
ROOT=pathlib.Path(__file__).resolve().parents[2];OUT=ROOT/'results/cycle46-mir-integration-gate/counterexamples';OUT.mkdir(parents=True,exist_ok=True);RUN=pathlib.Path(sys.argv[1]).resolve()
def render(s):
    locals=[]
    for op in s['noise']+s['core']:
        dst=op.split()[1].rstrip(',')
        if dst not in locals:locals.append(dst)
    if s['kind']=='conversion_branch':
        for x in ['converted','result']:
            if x not in locals:locals.append(x)
        body='\n'.join('  '+o for o in s['noise']+s['core'])
        body+=f"\n  ext8 converted, x\n  bge yes, converted, {s['threshold']}\n  mov result, 0\n  jmp done\nyes:\n  mov result, 1\ndone:\n  ret result"
        return 'reduce_mod: module\nreduce_case: func i64, i64:x\n  local '+', '.join('i64:'+v for v in locals)+'\n'+body+'\n  endfunc\n  endmodule\n'
    for x in ['raw','converted','result']:
        if x not in locals:locals.append(x)
    body='\n'.join('  '+o for o in s['noise'])
    body+=f"\n  mov raw, i8:0(p)\n  ext8 converted, raw\n  add result, converted, {s['increment']}\n  mov i64:8(p), result\n  ret result"
    return 'reduce_mod: module\nreduce_case: func i64, p:p\n  local '+', '.join('i64:'+v for v in locals)+'\n'+body+'\n  endfunc\n  endmodule\n'
def run(s,name):
    text=render(s);path=OUT/(name+'.mir');path.write_text(text)
    cmd=[str(RUN),str(path),'--memory'] if s['kind']=='memory_native' else [str(RUN),str(path),str(s['input'])]
    p=subprocess.run(cmd,text=True,capture_output=True,timeout=8)
    if p.returncode:raise RuntimeError((p.returncode,p.stderr,text))
    vals=dict(line.split('=',1) for line in p.stdout.splitlines());expected=s['expected'];observed=dict(vals)
    trigger=(s['kind']=='conversion_branch' and 'ext8 converted, x' in text and s['input']==128) or (s['kind']=='memory_native' and 'i8:0(p)' in text and 'i64:8(p)' in text)
    if trigger:observed['jit']=str(int(vals['jit'])^1)
    memory_expected='80'+'a5'*7+'81ffffffffffffff'+'a5'*8 if s['kind']=='memory_native' else None
    memory_ok=(s['kind']!='memory_native' or vals.get('memory')==memory_expected)
    fail=trigger and vals['jit']==str(expected) and observed['jit']!=str(expected) and memory_ok
    return {'text':text,'stdout':p.stdout,'expected':expected,'expected_memory':memory_expected,'memory_matches':memory_ok,'observed':observed,'failure':fail,'trigger':trigger}
def reduce(s,name):
    cur=json.loads(json.dumps(s));steps=[];orig=run(cur,name+'-original');assert orig['failure']
    i=0
    while i<len(cur['noise']):
        t=json.loads(json.dumps(cur));removed_dst=t['noise'][i].split()[1].rstrip(',');drop={i};dead={removed_dst};changed=True
        while changed:
            changed=False
            for j,line in enumerate(t['noise']):
                if j in drop:continue
                parts=[x.strip() for x in line.split(',')]
                if len(parts)>1 and any(re.search(r'\b'+re.escape(d)+r'\b',','.join(parts[1:])) for d in dead):
                    drop.add(j);dead.add(parts[0].split()[-1]);changed=True
        removed=[t['noise'][j] for j in sorted(drop)];t['noise']=[line for j,line in enumerate(t['noise']) if j not in drop]
        try:o=run(t,name+f'-trial-{len(steps):02}')
        except (RuntimeError,subprocess.TimeoutExpired):i+=1;continue
        if not o['failure']:i+=1;continue
        steps.append({'removed_operations':removed,'remaining_noise':len(t['noise'])});cur=t
    final=run(cur,name+'-reduced');assert final['failure']
    (OUT/(name+'-result.json')).write_text(json.dumps({'failure_class':s['failure_class'],'backend':'JIT/native generated code invoked through typed C function pointer','original_noise_operations':len(s['noise']),'reduced_noise_operations':len(cur['noise']),'preserved_core':s['core'],'steps':steps,'original_spec':s,'reduced_spec':cur,'original_mir':orig['text'],'reduced_mir':final['text'],'fresh_process_observation':{'stdout':final['stdout'],'expected':final['expected'],'expected_memory':final['expected_memory'],'memory_matches':final['memory_matches'],'observed':final['observed']}},indent=2)+'\n')
    return {'case':name,'failure_class':s['failure_class'],'original_noise':len(s['noise']),'reduced_noise':len(cur['noise']),'core_preserved':True,'fresh_process':final['failure']}
conv={'kind':'conversion_branch','input':128,'threshold':0,'expected':0,'failure_class':'injected_conversion_dependent_branch_jit_mismatch','noise':['mov n0, 7','mul n1, n0, 9','add n2, n1, 13'],'core':['mov n3, x']}
mem={'kind':'memory_native','input':None,'increment':1,'expected':-127,'failure_class':'injected_native_pointer_memory_jit_mismatch','noise':['mov n0, 9','mul n1, n0, 7','add n2, n1, 3'],'core':['mov n3, 0']}
results=[reduce(conv,'injected-composite-cfg'),reduce(mem,'injected-composite-memory')]
(ROOT/'results/cycle46-mir-integration-gate/composite-reducer-validation.json').write_text(json.dumps({'method':'bounded generated MIR text templates with fresh-process interpreter/JIT observations; comparator-only injected discrepancies','cases':results,'not_product_findings':True},indent=2)+'\n');print(json.dumps(results,indent=2))
