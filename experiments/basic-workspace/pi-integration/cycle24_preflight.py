#!/usr/bin/env python3
"""No-inference Cycle 24 production bridge and transaction preflight."""
from __future__ import annotations
import argparse, importlib.util, json, os, pathlib, socket, subprocess, sys, tempfile, time
HERE=pathlib.Path(__file__).resolve().parent
ROOT=HERE.parent
sys.path.insert(0,str(HERE))
from run_cycle16 import MODEL, gateway_call
ATOMIC_TOOLS=["workspace_discover_functions","workspace_inspect_program","workspace_preview_function","workspace_commit_preview","workspace_validate_mission"]
EDIT_TOOLS=["workspace_discover_functions","workspace_inspect_program","workspace_preview_semantic_edit","workspace_commit_preview","workspace_validate_mission"]
BASE=HERE/"results/cycle21-reusable-maintenance/real-agent-01"
CONTRACTS=HERE/"results/cycle24-dependency-propagation/contracts"
def write(p,v):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
def read(p):return json.loads(p.read_text(encoding="utf-8"))
def port():
 with socket.socket() as s:s.bind(("127.0.0.1",0));return s.getsockname()[1]
def stop(proc):
 if proc and proc.poll() is None:
  proc.terminate()
  try:proc.wait(timeout=5)
  except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=5)
def start_gateway(cmd,env,errpath):
 err=errpath.open("w",encoding="utf-8"); proc=subprocess.Popen(cmd,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=err,text=True,env=env)
 line=proc.stdout.readline()
 if not line: stop(proc);err.close();raise RuntimeError(f"gateway failed to start: {errpath.read_text()[-2000:]}")
 return proc,err,json.loads(line)
def dispatch(mode,ready,request,outdir):
 inp=outdir/"dispatch-input.json"; result=outdir/"dispatch-output.json";write(inp,request)
 env=os.environ.copy();env.update({"BASIC_WS_AUTHORING_MODE":"semantic_edit" if mode=="semantic_edit" else "atomic",
  "BASIC_WS_PI_GATEWAY":f"127.0.0.1:{ready['port']}","BASIC_WS_DISPATCH_PROBE_INPUT":str(inp),
  "BASIC_WS_DISPATCH_PROBE_OUTPUT":str(result),"NODE_PATH":"/usr/lib/node_modules/@earendil-works/pi-coding-agent/node_modules"})
 p=subprocess.run(["bun",str(HERE/"cycle20b_dispatch_probe.ts")],env=env,capture_output=True,text=True,timeout=90)
 (outdir/"dispatch.stdout.log").write_text(p.stdout,encoding="utf-8");(outdir/"dispatch.stderr.log").write_text(p.stderr,encoding="utf-8")
 if p.returncode or not result.is_file():raise RuntimeError(f"TypeScript/JSONL dispatch failed: {p.stderr[-2500:]} {p.stdout[-1000:]}")
 return read(result)
def score_body():
 num=lambda x:{"kind":"number","value":x}; ref={"kind":"local_ref","name":"X"}
 call=lambda h:{"kind":"call","function_handle":h,"arguments":[{"kind":"local_ref","name":"X"}]}
 assign=lambda x:{"kind":"assign","target":{"kind":"result"},"expression":num(x)}
 return [{"kind":"if","condition":{"kind":"binary","operator":"<","left":call("clamp_score.function"),"right":num(20)},"then":[assign(0)]},
  {"kind":"if","condition":{"kind":"binary","operator":">=","left":call("clamp_score.function"),"right":num(20)},"then":[assign(1)]},
  {"kind":"if","condition":{"kind":"binary","operator":">=","left":call("is_passing.function"),"right":num(1)},"then":[assign(2)]}]
def main():
 ap=argparse.ArgumentParser();ap.add_argument("--output",type=pathlib.Path,required=True);a=ap.parse_args();out=a.output.resolve()
 if out.exists() and any(out.iterdir()):raise SystemExit(f"refusing to overwrite: {out}")
 out.mkdir(parents=True,exist_ok=True)
 env=os.environ.copy(); env["PYTHONPATH"]=str(ROOT)+os.pathsep+str(HERE)+os.pathsep+env.get("PYTHONPATH","")
 # Production extension -> JSONL -> MissionGateway for the creation family.
 create=out/"function-creation";create.mkdir()
 p,e,ready=start_gateway([sys.executable,str(HERE/"cycle19_gateway.py"),"--output",str(create/"gateway-evidence"),"--port","0",
  "--creation-contract",str(CONTRACTS/"mission-1-score-class.json"),"--seed-contract",str(CONTRACTS/"seed-revision5.json"),
  "--baseline-stream",str(BASE/"constructive-operations.json"),"--baseline-history",str(BASE/"history.jsonl"),
  "--baseline-validation",str(BASE/"validation.json")],env,create/"gateway.stderr.log")
 try:
  if not ready.get("ready") or ready.get("revision")!=5 or ready.get("phase")!=3:raise RuntimeError(f"verified revision-5 setup failed: {ready}")
  corr=f"cycle24-create-preflight-{time.time_ns()}"
  args={"expected_revision":5,"name":"SCORE_CLASS","parameters":["X"],"body":score_body()}
  bad_unknown=json.loads(json.dumps(args));bad_unknown["body"][1]["condition"]["left"]["function_handle"]="missing.function"
  bad_other=json.loads(json.dumps(args));bad_other["name"]="UNRELATED"
  stale=json.loads(json.dumps(args));stale["expected_revision"]=4
  result=dispatch("atomic_create",ready,{"authoring_mode":"atomic_create","correlation_id":corr,"preview_args":args,"commit":True,
   "controls":[bad_unknown,bad_other,stale]},create)
  host_validation=gateway_call("127.0.0.1",ready["port"],"host_validate",{"expected_revision":6})
  write(create/"tool-inventory.json",{"tools":result.get("active_tools"),"source":"Production extension registry via deterministic handler dispatch"})
  write(create/"tool-schemas.json",result.get("schemas"))
  if sorted(result.get("active_tools",[]))!=sorted(ATOMIC_TOOLS) or not result.get("schema_ok"):raise RuntimeError("active creation tools/schema mismatch")
  if ready.get("revision")!=5 or not result.get("preview",{}).get("candidate_is_preview_only"):raise RuntimeError("creation preview contract failed")
  if [row.get("code") for row in result.get("controls",[])]!=["MISSION_DEPENDENCY_REQUIRED","MISSION_SIGNATURE","STALE_REVISION"]:raise RuntimeError("creation controls were not rejected as expected")
  if not result.get("committed",{}).get("committed") or result["committed"].get("revision")!=6:raise RuntimeError("creation production dispatch did not commit revision 6")
  if not result.get("validation",{}).get("mission_complete") or not host_validation.get("mission_complete"):
   raise RuntimeError("creation independent oracle/replay failed")
 finally:stop(p);e.close()
 # Use resulting genuine-format committed operation/history as revision-6 input to Cycle20's shared maintenance kernel.
 maint=out/"numeric-maintenance";maint.mkdir(); stream=create/"gateway-evidence/constructive-operations.json"
 history=create/"gateway-evidence/history.jsonl"; validation=create/"gateway-evidence/mission-3-validation-host.json"
 p,e,ready=start_gateway([sys.executable,str(HERE/"cycle20_gateway.py"),"--output",str(maint/"gateway-evidence"),
  "--contract",str(CONTRACTS/"mission-2-threshold45.json"),"--baseline-stream",str(stream),"--baseline-history",str(history),
  "--baseline-validation",str(validation),"--port","0"],env,maint/"gateway.stderr.log")
 try:
  if not ready.get("ready") or ready.get("revision")!=6 or not ready.get("baseline_verified"):raise RuntimeError(f"maintenance baseline replay failed: {ready}")
  corr=f"cycle24-maint-preflight-{time.time_ns()}"
  edit={"expected_revision":6,"function_handle":"is_passing.function","edits":[{"target":{"function_handle":"is_passing.function",
   "control_path":[{"block":"body","index":0}],"expression_path":[1]},"expected_value":40,"replacement_value":45}]}
  bad=json.loads(json.dumps(edit));bad["function_handle"]="score_class.function"
  stale=json.loads(json.dumps(edit));stale["expected_revision"]=5
  wrong=json.loads(json.dumps(edit));wrong["edits"][0]["expected_value"]=41
  result2=dispatch("semantic_edit",ready,{"authoring_mode":"semantic_edit","correlation_id":corr,"preview_args":edit,"commit":True,
   "controls":[bad,stale,wrong]},maint)
  write(maint/"tool-inventory.json",{"tools":result2.get("active_tools"),"source":"Production extension registry via deterministic handler dispatch"})
  write(maint/"tool-schemas.json",result2.get("schemas"))
  if sorted(result2.get("active_tools",[]))!=sorted(EDIT_TOOLS) or not result2.get("schema_ok"):raise RuntimeError("active maintenance tools/schema mismatch")
  if [row.get("code") for row in result2.get("controls",[])]!=["MISSION_EDIT_SCOPE","STALE_REVISION","MISSION_LITERAL_VALUES"]:raise RuntimeError(f"maintenance controls unexpected: {[r.get('code') for r in result2.get('controls',[])]}")
  if not result2.get("preview",{}).get("accepted") or not result2.get("preview",{}).get("candidate_is_preview_only"):raise RuntimeError("maintenance preview failed")
  if not result2.get("committed",{}).get("committed") or result2["committed"].get("revision")!=7:raise RuntimeError("maintenance bridge commit did not advance to revision 7")
  if not result2.get("validation",{}).get("mission_complete"):raise RuntimeError("maintenance oracle/replay validation failed")
 finally:stop(p);e.close()
 summary={"schema":"basic-workspace.cycle24-preflight","version":1,"inference_performed":False,
  "baseline":{"cycle21_revision5_reconstruction":"passed","operation_count":4,"remapped_identity_count":11},
  "function_creation":{"production_typescript_jsonl_dispatch":"passed","base_revision":5,"preview_non_mutating":True,
   "rejected_controls":[r.get("code") for r in result.get("controls",[])],"committed_revision":6,
   "dependency_edges":result["validation"].get("dependency_edges"),"interpreter_jit":result["validation"].get("engines_agree"),
   "host_oracle_and_replay":result["validation"].get("mission_complete"),"schema_bytes":(create/"tool-schemas.json").stat().st_size},
  "numeric_maintenance":{"production_typescript_jsonl_dispatch":"passed","base_revision":6,"rejected_controls":[r.get("code") for r in result2.get("controls",[])],
   "committed_revision":7,"interpreter_jit":result2["validation"].get("engines_agree"),"host_oracle_and_replay":result2["validation"].get("mission_complete"),
   "schema_bytes":(maint/"tool-schemas.json").stat().st_size},"shared_transaction_lifecycle":"SemanticTransactionKernel.preview/commit used for both operation families"}
 write(out/"summary.json",summary);print(json.dumps(summary,indent=2))
if __name__=="__main__":main()
