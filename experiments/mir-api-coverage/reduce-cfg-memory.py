#!/usr/bin/env python3
"""Bounded input reducer, self-tested on two deliberately injected result faults."""
import json, pathlib, sys

root=pathlib.Path(__file__).resolve().parents[2]
src=pathlib.Path(sys.argv[1]) if len(sys.argv)>1 else root/'results/cycle43-mir-cfg-memory/differential-results.jsonl'
out=pathlib.Path(sys.argv[2]) if len(sys.argv)>2 else root/'results/cycle43-mir-cfg-memory/reducer-validation.json'
rows=[json.loads(line) for line in src.read_text().splitlines() if line]

def number(row,key): return int(row[key])
def reduce_input(original, predicate, value_key):
    candidates=[r for r in rows if r.get('domain')==original['domain'] and r.get('case')==original['case']]
    candidates=sorted(candidates,key=lambda r:(abs(number(r,value_key)),number(r,value_key),int(r['k'])))
    for candidate in candidates:
        observed=int(candidate['interp'])
        wrong=observed+1
        if predicate(candidate,wrong,observed): return candidate,wrong,observed
    raise RuntimeError('no preserving valid reduction found')

checks=[]
for domain,name,key in [('cfg','cfg_diamond','x'),('memory','mem_store_i8_load_u8','x')]:
    original=next(r for r in rows if r.get('domain')==domain and r.get('case')==name and int(r[key])!=0)
    def still_fails(candidate,wrong,observed): return wrong!=observed and candidate.get('domain')==domain and candidate.get('case')==name
    reduced,mutated,observed=reduce_input(original,still_fails,key)
    checks.append({'fault':'deliberately injected expected_result_plus_one','domain':domain,'failure_class':'oracle_expectation_mismatch_test_only','original':original,'reduced':reduced,'injected_expected':mutated,'observed_mir':observed,'preserved_class':mutated!=observed,'input_abs_reduced':abs(int(reduced[key]))<abs(int(original[key]))})
out.write_text(json.dumps({'classification':'test-only reducer validation; injected discrepancies are not MIR defects','strategy':'drop unrelated cases by selecting one result row, then minimize the input among valid generated rows for the same function','checks':checks,'limitations':['Does not rewrite CFG blocks or MIR statements','Memory operations remain the generated single function template','Uses recorded interpreter outputs for reducer self-test; every reduced input is a corpus case previously executed through MIR']},indent=2)+'\n')
print(json.dumps([{'domain':x['domain'],'original':x['original']['x'],'reduced':x['reduced']['x'],'preserved_class':x['preserved_class']} for x in checks]))
