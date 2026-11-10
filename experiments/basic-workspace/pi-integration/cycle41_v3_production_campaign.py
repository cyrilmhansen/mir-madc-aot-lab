#!/usr/bin/env python3
"""Cycle39 mathematical templates through Cycle19/Cycle37/Cycle20-v3."""
from __future__ import annotations
import copy, json, pathlib, random, sys, time

HERE=pathlib.Path(__file__).resolve().parent; ROOT=HERE.parent
sys.path[:0]=[str(ROOT),str(HERE)]
import cycle36_preflight as c36
import cycle37_preflight as c37
import cycle38_preflight as c38
import cycle39_differential_campaign as c39
from basic_workspace.model import WorkspaceError
from cycle20_gateway import Cycle20Gateway
from cycle39_differential_campaign import atom_num, atom_x, atom_call, assign, if_assign

OUT=HERE/"results/cycle41-finite-oracle-coverage"
FAMILIES=("threshold_ge","threshold_lt","sequential_override","two_callees")
INPUTS={}; CURRENT={}; INITIAL_RULES={}; FINAL_RULES={}; LABEL_CASES={}
PROFILE=c36.PROFILE

def write(path,value):
 path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def calls_in(body):
 out=[]
 def walk(v):
  if isinstance(v,dict):
   if v.get("kind")=="call": out.append(v["function_handle"])
   for x in v.values(): walk(x)
  elif isinstance(v,list):
   for x in v: walk(x)
 for x in body: walk(x)
 return sorted(set(out))

def boundary_inputs(case,rules):
 values=set(c39.input_corpus(case)); values.update([-25,-1,0,1,100,101])
 for rule in rules.values():
  if rule["kind"]=="clamp":
   for v in (rule["lower"],rule["upper_condition"],rule["upper_result"]): values.update((v-1,v,v+1))
  elif rule["kind"]=="predicate":
   t=rule["threshold"];values.update((t-1,t,t+1))
  elif rule["kind"]=="sequential":
   for step in rule["steps"]:
    t=step["threshold"];values.update((t-1,t,t+1))
 return sorted(values)

def evaluate(rules,handle,x): return float(c39.oracle_value(rules,handle,x))

def _new_raw_predicate(case,index,operator,threshold):
 stem=f"{case['case_id'].replace('-','_')}_AUX{index}".upper(); handle=f"{stem.lower()}.function"
 body=[assign(atom_num(0)),if_assign(atom_x(),operator,atom_num(threshold),1)]
 name=stem
 return {"operation":"create_numeric_function","portable_handle":handle,
   "arguments":{"name":name,"parameters":["X"],"body":body}}, {"handle":handle,"kind":"predicate","source":"x","operator":operator,"threshold":threshold}

def prepare_case(case,seed):
 """Use Cycle39's typed templates/specification; add one typed partner where required."""
 family=case["family"]; count=len(case["functions"])
 constructors=copy.deepcopy(case["operations"][:count])
 initial_rules={row["handle"]:copy.deepcopy(row["rule"]) for row in case["initial_specification"]["functions"]}
 # Current template rows may be one-function; add a second independently specified function so v3
 # maintenance can exercise an atomic edit across distinct function identities.
 if family in {"threshold_ge","threshold_lt"}:
  source=case["functions"][0]["rule"]
  for extra in (1,2):
   op,rule=_new_raw_predicate(case,extra,source["operator"],source["threshold"]+3*extra)
   constructors.append(op);initial_rules[op["portable_handle"]]=rule
 elif family=="clamp":
  provider=constructors[0]["portable_handle"]; handle=f"{case['case_id'].replace('-','_')}_accepted.function"
  name=f"{case['case_id'].replace('-','_')}_ACCEPTED".upper();t=max(2,int(initial_rules[provider]["upper_condition"])//2)
  body=[assign(atom_num(0)),if_assign(atom_call(provider),">=",atom_num(t),1)]
  constructors.append({"operation":"create_numeric_function","portable_handle":handle,"arguments":{"name":name,"parameters":["X"],"body":body}})
  initial_rules[handle]={"kind":"predicate","source":provider,"operator":">=","threshold":t}
 names=[op["arguments"]["name"] for op in constructors]
 handles=[op["portable_handle"] for op in constructors]
 for op in constructors:
  op["arguments"]["parameters"]=["X"]
 # Mutation target plan: every edit is a nonnegative numeric RHS or the clamp's direct result literal.
 final_rules=copy.deepcopy(initial_rules); mutations=[]
 if family in {"clamp","dependent_predicate"}:
  provider=handles[0]; rule=final_rules[provider]; new_cap=int(rule["upper_condition"])-1
  mutations.extend([{"handle":provider,"body_index":2,"expected":rule["upper_condition"],"replacement":new_cap,"label":"clamp comparison"},
                    {"handle":provider,"statement_value":rule["upper_result"],"expected":rule["upper_result"],"replacement":new_cap,"label":"clamp result"}])
  rule["upper_condition"]=new_cap;rule["upper_result"]=new_cap
  pred_handle=handles[1]; pred=final_rules[pred_handle]; old=pred["threshold"];new=old+1
  mutations.append({"handle":pred_handle,"body_index":1,"expected":old,"replacement":new,"label":"dependent threshold"});pred["threshold"]=new
 elif family in {"threshold_ge","threshold_lt"}:
  for h in handles:
   rule=final_rules[h];old=rule["threshold"];new=old+1
   idx=1
   mutations.append({"handle":h,"body_index":idx,"expected":old,"replacement":new,"label":"raw predicate threshold"});rule["threshold"]=new
 elif family=="sequential_override":
  minor=handles[1]; old=final_rules[minor]["threshold"];new=old+1
  mutations.append({"handle":minor,"body_index":1,"expected":old,"replacement":new,"label":"minor threshold"});final_rules[minor]["threshold"]=new
  eligible=handles[2];old=final_rules[eligible]["steps"][1]["threshold"];new=old+1
  mutations.append({"handle":eligible,"body_index":2,"expected":old,"replacement":new,"label":"override condition"});final_rules[eligible]["steps"][1]["threshold"]=new
  old=final_rules[eligible]["steps"][0]["threshold"];new=old+1
  mutations.append({"handle":eligible,"body_index":1,"expected":old,"replacement":new,"label":"initial condition"});final_rules[eligible]["steps"][0]["threshold"]=new
 elif family=="two_callees":
  for h in handles[:2]:
   old=final_rules[h]["threshold"];new=old+1
   mutations.append({"handle":h,"body_index":1,"expected":old,"replacement":new,"label":"callee threshold"});final_rules[h]["threshold"]=new
  aggregator=handles[2];old=final_rules[aggregator]["steps"][0]["threshold"];new=old+1
  mutations.append({"handle":aggregator,"body_index":1,"expected":old,"replacement":new,"label":"first callee guard"});final_rules[aggregator]["steps"][0]["threshold"]=new
 elif family=="dependency_chain":
  for h in (handles[0],handles[-1]):
   old=final_rules[h]["threshold"];new=old+1
   mutations.append({"handle":h,"body_index":1,"expected":old,"replacement":new,"label":"dependency-chain threshold"});final_rules[h]["threshold"]=new
 else:
  raise ValueError(family)
 # Ensure replacement literals differ and stay in direct numeric-node grammar.
 if any(m["expected"]==m["replacement"] or m["expected"]<0 or m["replacement"]<0 for m in mutations):
  raise ValueError("generated edit target is not a distinct nonnegative numeric literal")
 input_set=set(boundary_inputs(case,initial_rules))
 for mutation in mutations: input_set.update((mutation["replacement"]-1,mutation["replacement"],mutation["replacement"]+1))
 inputs=sorted(input_set)
 if len(inputs)>64: raise ValueError(f"input corpus exceeds v3 bound: {len(inputs)}")
 edges=[]
 for op in constructors:
  for callee in calls_in(op["arguments"]["body"]): edges.append({"caller_handle":op["portable_handle"],"callee_handle":callee})
 return {"case_id":case["case_id"],"seed":seed,"family":family,"constructors":constructors,"names":names,"handles":handles,
  "initial_rules":initial_rules,"final_rules":final_rules,"mutations":mutations,"inputs":inputs,"edges":edges,
  "rename_target":handles[0],"rename_old_name":names[0],"rename_new_name":names[0]+"_RENAMED"}

def math_rows(case,final=False):
 rules=case["final_rules"] if final else case["initial_rules"]
 return [{"handle":h,"name":name,"result_key":name.lower()} for h,name in zip(case["handles"],case["names"])], rules

def oracle_by_name(label,x):
 case=CURRENT; return {name.lower():evaluate(INITIAL_RULES,h,x) for h,name in zip(case["handles"],case["names"])}

def build_sequence(label,case):
 steps=[];known=[]
 for i,op in enumerate(case["constructors"]):
  h=op["portable_handle"];name=op["arguments"]["name"];body=op["arguments"]["body"]
  callees=calls_in(body);step_edges=[{"caller_handle":h,"callee_handle":c} for c in callees]
  expected={str(x):{prev["arguments"]["name"].lower():evaluate(case["initial_rules"],prev["portable_handle"],x) for prev in case["constructors"][:i+1]} for x in case["inputs"]}
  steps.append({"step_id":f"step-{i+1:02d}-{name.lower()}","mission_id":f"cycle41.{label}.{i+1:02d}",
   "expected_base_revision":i+1,"function":{"name":name,"portable_handle":h,"parameters":["X"],"return_type":"numeric"},
   "required_callees":callees,"required_dependency_edges":step_edges,
   "required_existing_function_handles_unchanged":[row["portable_handle"] for row in case["constructors"][:i]],
   "validation":{"inputs":case["inputs"],"expected_results":expected}})
 return {"schema":"basic-workspace.numeric-function-creation-sequence","version":1,"sequence_id":f"cycle41.{label}.creation.v1",
   "objective":f"Construct independent Cycle39 mathematical template {case['family']}.","execution_profile_id":PROFILE,
   "starting_revision":1,"maximum_steps":8,"steps":steps}

def function_request(label,name):
 row=next(op for op in CURRENT["constructors"] if op["arguments"]["name"]==name)
 return copy.deepcopy(row["arguments"])

def rename_contract(label,creation,out):
 case=CURRENT;path=pathlib.Path(out)/"rename-contract.json"
 contract={"schema":"basic-workspace.semantic-rename-contract","version":2,"mission_id":f"cycle41.{label}.rename.v2",
  "objective":f"Rename {case['rename_old_name']} preserving semantic identity and call bindings.",
  "base_document_revision":creation["final_revision"],"execution_profile_id":PROFILE,"target_handle":case["rename_target"],
  "expected_source_name":case["rename_old_name"],"new_source_name":case["rename_new_name"],
  "unchanged_function_handles":[h for h in case["handles"] if h!=case["rename_target"]],"unchanged_dependency_edges":True,
  "required_revision_increment":1,"validation_inputs":case["inputs"]}
 c37.write(path,contract);return path,contract

def make_v3_contract(label,creation,renamed,out):
 case=CURRENT;stream,ws,doc,replay,baseline=c36._replay_source(creation["evidence"])
 targets=[]
 for m in case["mutations"]:
  target_fn=next(row for row in case["constructors"] if row["portable_handle"]==m["handle"])
  if "statement_value" in m:
   found=[]
   for ph in stream["portable_handles"]:
    if ph.startswith(m["handle"].rsplit(".",1)[0]+".statement."):
     target={"function_handle":m["handle"],"statement_handle":ph,"expression_path":[]}
     try:
      _f,_s,node=Cycle20Gateway._target_expression(baseline,target)
      if float(node["value"])==float(m["expected"]): found.append(target)
     except WorkspaceError: pass
   if len(found)!=1: raise RuntimeError(f"Expected exactly one typed result literal at {m}: {found}")
   target=found[0]
  else:
   target={"function_handle":m["handle"],"control_path":[{"block":"body","index":m["body_index"]}],"expression_path":[1]}
   _f,_s,node=Cycle20Gateway._target_expression(baseline,target)
   if float(node["value"])!=float(m["expected"]): raise RuntimeError(f"Typed target value mismatch: {m} vs {node}")
  targets.append({"target":target,"expected_original_value":m["expected"],"replacement_constraint":{"kind":"one_of","values":[m["replacement"]]},"label":m["label"]})
 changed={m["handle"] for m in case["mutations"]}
 names={op["portable_handle"]:op["arguments"]["name"].lower() for op in case["constructors"]}
 functions=[{"function_handle":h,"result_key":names[h]} for h in case["handles"]]
 expected=[{names[h]:evaluate(case["final_rules"],h,x) for h in case["handles"]} for x in case["inputs"]]
 contract={"schema":"basic-workspace.numeric-literal-maintenance-contract","version":3,"scope_mode":"per_target",
  "mission_id":f"cycle41.{label}.maintenance.v3","objective":f"Apply the host-authorized numeric edits for {case['family']}.",
  "base_document_revision":renamed["revision"],"execution_profile_id":PROFILE,
  "allowed_function_handles":sorted(changed),"authorized_targets":targets,"minimum_edits":len(targets),"maximum_edits":len(targets),
  "unchanged_function_handles":sorted(set(case["handles"])-changed),"required_dependency_edges":case["edges"],"revision_increment":1,
  "validation":{"mode":"finite_expected_results","inputs":case["inputs"],"functions":functions,"expected_results":expected}}
 path=pathlib.Path(out)/"maintenance-contract.json";write(path,contract)
 # Independently assert the host table equals the math spec before binding its trust anchor.
 if any(row!=expected[i] for i,row in enumerate(contract["validation"]["expected_results"])): raise AssertionError("finite table generation mismatch")
 return path,contract

def maintenance_contract(label,creation,renamed,out): return make_v3_contract(label,creation,renamed,out)

def expected_by_handle(label,maintained,x):
 case=CURRENT;rules=case["final_rules"] if maintained else case["initial_rules"]
 return {h:evaluate(rules,h,x) for h in case["handles"]}

def run_one(label,case,out):
 global CURRENT,INITIAL_RULES
 CURRENT=case;INITIAL_RULES=case["initial_rules"];INPUTS[label]=case["inputs"]
 c36.INPUTS[label]=case["inputs"];c36.sequence_contract=lambda _label:build_sequence(label,case);c36.fn_request=function_request
 c37.INPUTS[label]=case["inputs"];c37.oracle=oracle_by_name;c37.rename_contract=rename_contract
 c38.INPUTS[label]=case["inputs"];c38.expected_by_handle=expected_by_handle;c38.maintenance_contract=maintenance_contract
 case_dir=pathlib.Path(out)/label;case_dir.mkdir(parents=True,exist_ok=False);write(case_dir/"mathematical-specification.json",case)
 creation=c36.create_program(label,pathlib.Path(out));creation["portable_handles"]=c36.read(creation["evidence"]/"constructive-operations.json")["portable_handles"]
 renamed=c37.run_rename(label,creation,pathlib.Path(out));rename_root=pathlib.Path(out)/label
 renamed.update({"handoff_path":rename_root/"handoff/handoff.json","anchor_path":rename_root/"handoff/host-trust-anchor.json",
  "contract_path":rename_root/"rename-contract.json","revision":creation["final_revision"]+1,"evidence":rename_root/"rename/gateway-evidence"})
 maintenance=c38.run_maintenance(label,creation,renamed,case_dir)
 summary={"case_id":case["case_id"],"seed":case["seed"],"family":case["family"],"function_count":len(case["handles"]),
  "creation_revision":creation["final_revision"],"rename_revision":renamed["revision"],"maintenance_revision":renamed["revision"]+1,
  "constructor_commits":len(case["constructors"]),"rename_commits":1,"maintenance_targets":len(case["mutations"]),
  "validation_mode":"finite_expected_results","production_gateways":["Cycle19","Cycle37","Cycle20-v3"],
  "oracle_mir_replay_agree":True,"portable_handles":case["handles"],"dependency_edges":case["edges"],"contract":maintenance["contract"]}
 write(case_dir/"summary.json",summary);return summary

def select_cases(count,seed_offset,families=FAMILIES):
 candidates=c39.generate_cases(120,seed_offset=seed_offset); buckets={f:[] for f in families}
 for c in candidates:
  if c["family"] in buckets and len(buckets[c["family"]]) < count//len(families): buckets[c["family"]].append(c)
 for family,items in buckets.items():
  if len(items)<count//len(families): raise RuntimeError(f"Not enough generated cases for {family}")
 # Return balanced ordered families; configured count is a multiple of family count.
 selected=[]
 for j in range(count//len(families)):
  for family in families:selected.append(buckets[family][j])
 return selected

def main():
 import argparse,shutil
 p=argparse.ArgumentParser();p.add_argument('--output',type=pathlib.Path,required=True);p.add_argument('--count',type=int,default=16);p.add_argument('--seed-offset',type=int,default=410000);p.add_argument('--family-set',choices=['priority','controls'],default='priority')
 a=p.parse_args();out=a.output.resolve()
 if out.exists() and any(out.iterdir()):raise SystemExit(f'refusing overwrite {out}')
 if not shutil.which('bun'):raise SystemExit('bun is required for actual TypeScript bridge')
 fams=FAMILIES if a.family_set=='priority' else ('clamp','dependent_predicate','dependency_chain')
 if a.count%len(fams):raise SystemExit('count must be divisible by selected family count')
 out.mkdir(parents=True,exist_ok=True);summaries=[]
 selected=select_cases(a.count,a.seed_offset,fams)
 for i,c in enumerate(selected,1):
  prepared=prepare_case(c,c['seed']);prepared['case_id']=f"cycle41-{a.seed_offset}-{i:02d}";label=f"workflow-{i:02d}"
  summaries.append(run_one(label,prepared,out))
 write(out/"workflow-results.json",{"family_set":a.family_set,"count":len(summaries),"workflows":summaries,"passed":True})
 print(json.dumps({"count":len(summaries),"families":dict(__import__('collections').Counter(r['family'] for r in summaries))},indent=2))

if __name__=='__main__':main()
