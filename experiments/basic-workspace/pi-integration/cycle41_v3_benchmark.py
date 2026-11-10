#!/usr/bin/env python3
"""Repeated v2 formula-oracle versus v3 finite-table validation benchmark."""
from __future__ import annotations
import copy,json,pathlib,statistics,sys,time
HERE=pathlib.Path(__file__).resolve().parent;ROOT=HERE.parent
sys.path[:0]=[str(ROOT),str(HERE)]
from cycle20_gateway import Cycle20Gateway

SOURCE=HERE/"results/cycle34-cross-function-authorization/primary-contract.json"
CAP=50;THRESHOLD=45

def summarize(xs): return {"samples":xs,"median_ms":statistics.median(xs),"min_ms":min(xs),"max_ms":max(xs)}
def clock(fn):
 start=time.perf_counter();result=fn();return (time.perf_counter()-start)*1000,result

def contracts(n,out):
 base=json.loads(SOURCE.read_text());inputs=list(base["validation"]["inputs"])
 candidate=0
 while len(inputs)<n:
  if candidate not in inputs: inputs.append(candidate)
  candidate+=1
 inputs=sorted(inputs)
 v2=copy.deepcopy(base);v2["mission_id"]=f"cycle41.bench.v2.n{n}";v2["validation"]["inputs"]=inputs
 v3=copy.deepcopy(v2);v3["version"]=3
 v3["validation"]={"mode":"finite_expected_results","inputs":inputs,
  "functions":[{"function_handle":r["function_handle"],"result_key":r["result_key"]} for r in base["validation"]["functions"]],
  "expected_results":[{"clamp_score":min(CAP,max(0,x)),"is_passing":int(min(CAP,max(0,x))>=THRESHOLD)} for x in inputs]}
 paths=[]
 for name,doc in (("v2",v2),("v3",v3)):
  path=out/f"{name}-n{n}.json";path.write_text(json.dumps(doc),encoding="utf-8");paths.append(path)
 return paths

def request(g): return {"expected_revision":3,"scope_mode":"per_target","edits":[
 {"target":copy.deepcopy(row["target"]),"expected_value":row["expected_value"],
  "replacement_value":row["replacement_constraint"]["values"][0]} for row in g.edit_targets]}

def sample_mode(mode,path,out,n,repeats=5):
 init=[];parse=[];lookup=[];preview=[];commit=[];validate=[];mir=[]
 for i in range(repeats):
  ms,g=clock(lambda:Cycle20Gateway(out/f"{mode}-n{n}-r{i}",contract_path=path));init.append(ms)
  g.handle("discover_functions",{},f"discover-{mode}-{n}-{i}")
  req=request(g)
  ms,_=clock(lambda:g.handle("preview_semantic_edit",req,f"preview-{mode}-{n}-{i}"))
  if not _["ok"]: raise RuntimeError(f"{mode} preview failed: {_}")
  tx=_['transaction_id'];preview.append(ms)
  ms,c=clock(lambda:g.handle("commit_preview",{"transaction_id":tx},f"commit-{mode}-{n}-{i}"))
  if not c["committed"]: raise RuntimeError(f"{mode} commit failed: {c}")
  commit.append(ms)
  ms,v=clock(lambda:g.validate_current(4));validate.append(ms)
  if not v["mission_complete"]: raise RuntimeError(f"{mode} validation failed: {v}")
  # Separately measure the shared MIR observation loop on final revision.
  ms,_=clock(lambda:g._run_observations(g.ws,g.doc,4,g.aliases));mir.append(ms)
  # Parse/schema and expected lookup are measured without gateway or MIR startup.
  ms,_=clock(lambda:[Cycle20Gateway._validate_contract_shape(g.contract) for _ in range(200)]);parse.append(ms/200)
  ms,_=clock(lambda:[g._expected_observations() for _ in range(200)]);lookup.append(ms/200)
 return {"gateway_initialization_ms":summarize(init),"candidate_preview_ms":summarize(preview),
  "commit_revalidation_ms":summarize(commit),"final_validate_and_replay_ms":summarize(validate),
  "mir_observation_loop_ms":summarize(mir),"contract_parse_validate_ms_per_call":summarize(parse),
  "expected_observation_lookup_ms_per_call":summarize(lookup),"function_count":2,"authorized_targets":3,
  "input_count":n,"repeat_count":repeats}

def main():
 import argparse,platform,os
 p=argparse.ArgumentParser();p.add_argument('--output',type=pathlib.Path,required=True);a=p.parse_args();out=a.output.resolve()
 if out.exists() and any(out.iterdir()):raise SystemExit(f'refusing overwrite {out}')
 out.mkdir(parents=True,exist_ok=True);results={}
 for n in (16,32,64):
  v2p,v3p=contracts(n,out);results[str(n)]={}
  results[str(n)]["v2"]=sample_mode("v2",v2p,out,n)
  results[str(n)]["v3"]=sample_mode("v3",v3p,out,n)
 doc={"schema":"basic-workspace.cycle41-v2-v3-benchmark","version":1,"confirmatory":True,
  "environment":{"platform":platform.platform(),"python":platform.python_version()},"warmup":"gateway worker initialization included per sample; each sample uses a fresh authoritative gateway",
  "threshold_registered_before_run":"2x same-input-count median and repeated confirmation; applied separately to each metric",
  "dimensions":{"input_counts":[16,32,64],"functions":2,"authorized_targets":3,"dependency_depth":1},
  "results":results,"limitation":"Canonical v2/v3 equivalence fixture has two functions and three targets; function-count/dependency-depth scaling is characterized by generated workflow corpus, not this isolated oracle benchmark."}
 (out/'benchmark.json').write_text(json.dumps(doc,indent=2)+'\n');print(json.dumps({n:{m:round(v['candidate_preview_ms']['median_ms'],3) for m,v in modes.items()} for n,modes in results.items()},indent=2))
if __name__=='__main__':main()
