#!/usr/bin/env python3
"""Cycle 25 no-inference Pi schema and production bridge preflight."""
from __future__ import annotations
import argparse,json,os,pathlib,socket,subprocess,sys,time
HERE=pathlib.Path(__file__).resolve().parent; ROOT=HERE.parent
sys.path.insert(0,str(HERE))
from run_cycle16 import MODEL,isolated_config,rpc_preflight,gateway_call
TOOLS=["workspace_discover_functions","workspace_inspect_program","workspace_commit_preview","workspace_validate_mission","workspace_preview_structural_edit"]
def write(path,value):pathlib.Path(path).write_text(json.dumps(value,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
def port():
 with socket.socket() as s:s.bind(("127.0.0.1",0));return s.getsockname()[1]
def stop(proc):
 if proc and proc.poll() is None:
  proc.terminate()
  try:proc.wait(timeout=5)
  except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=5)
def request(*,revision=7,function="score_class.function",anchor="score_class.statement.3",operator="=",callee="clamp_score.function",value=50,result=3):
 return {"expected_revision":revision,"function_handle":function,"before_statement_handle":anchor,
  "statement":{"kind":"if","condition":{"kind":"binary","operator":operator,
    "left":{"kind":"call","function_handle":callee,"arguments":[{"kind":"local_ref","name":"X"}]},
    "right":{"kind":"number","value":value}},"then":[{"kind":"assign","target":{"kind":"result"},"expression":{"kind":"number","value":result}}]}}
def dispatch(out,port,body):
 inpath=out/"dispatch-input.json";result=out/"dispatch-output.json"
 write(inpath,body);env=os.environ.copy();env.update({"BASIC_WS_AUTHORING_MODE":"structural_edit",
  "BASIC_WS_PI_GATEWAY":f"127.0.0.1:{port}","BASIC_WS_DISPATCH_PROBE_INPUT":str(inpath),
  "BASIC_WS_DISPATCH_PROBE_OUTPUT":str(result),"NODE_PATH":"/usr/lib/node_modules/@earendil-works/pi-coding-agent/node_modules"})
 proc=subprocess.run(["bun",str(HERE/"cycle20b_dispatch_probe.ts")],env=env,capture_output=True,text=True,timeout=90)
 (out/"dispatch.stdout.log").write_text(proc.stdout,encoding="utf-8");(out/"dispatch.stderr.log").write_text(proc.stderr,encoding="utf-8")
 if proc.returncode or not result.is_file():raise RuntimeError(f"production extension/JSONL dispatch failed: {proc.stderr[-2000:]}")
 return json.loads(result.read_text())
def main():
 ap=argparse.ArgumentParser();ap.add_argument("--output",type=pathlib.Path,required=True);ap.add_argument("--preflight-only",action="store_true");a=ap.parse_args()
 out=a.output.resolve()
 if out.exists() and any(out.iterdir()):raise SystemExit(f"refusing to overwrite evidence: {out}")
 out.mkdir(parents=True,exist_ok=True)
 env=os.environ.copy();env["PYTHONPATH"]=str(ROOT)+os.pathsep+str(HERE)+os.pathsep+env.get("PYTHONPATH","")
 proc=subprocess.Popen([sys.executable,str(HERE/"cycle25_gateway.py"),"--output",str(out/"gateway-evidence"),"--port","0"],
  stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=(out/"gateway-stderr.log").open("w",encoding="utf-8"),text=True,env=env)
 try:
  ready=json.loads(proc.stdout.readline())
  if not ready.get("ready") or ready.get("revision")!=7 or ready.get("identity_count")!=17:raise RuntimeError(f"verified revision-7 baseline failed: {ready}")
  (out/"gateway-ready.json").write_text(json.dumps({k:v for k,v in ready.items() if k!="port"}|{"port":ready["port"]},indent=2)+"\n")
  # Exercise the exact active TypeBox schema and the production extension-to-JSONL path.
  good=request();controls=[request(function="is_passing.function"),request(anchor="score_class.statement.2"),
   request(revision=6),request(callee="is_passing.function"),request(operator=">=")]
  result=dispatch(out,ready["port"],{"authoring_mode":"structural_edit","correlation_id":f"cycle25-preflight-{time.time_ns()}",
   "preview_args":good,"controls":controls,"commit":True})
  schemas=result.get("schemas",[]);inventory=result.get("active_tools",[])
  write(out/"tool-inventory.json",{"tools":inventory,"source":"actual TypeScript extension active registry"})
  write(out/"tool-schemas.json",schemas)
  if inventory!=TOOLS or not result.get("schema_ok"):raise RuntimeError("actual Pi extension tools/schema did not match the structural allowlist")
  schema=json.dumps(schemas,separators=(",",":"),ensure_ascii=False)
  if '"items":{}' in schema:raise RuntimeError("structural IF schema exposes an unconstrained array item")
  if not result.get("discovery",{}).get("functions") or "structural_insertion_anchors" not in result.get("inspection",{}):raise RuntimeError("agent-facing discovery did not expose verified function and boundary handles")
  if [r.get("code") for r in result.get("controls",[])]!=["MISSION_EDIT_SCOPE","INVALID_INSERTION_ANCHOR","STALE_REVISION","MISSION_DEPENDENCY_FORBIDDEN","MISSION_IF_CONDITION"]:
   raise RuntimeError(f"host authorization controls failed: {[r.get('code') for r in result.get('controls',[])]}")
  if not result.get("preview",{}).get("ok") or not result["preview"].get("candidate_is_preview_only"):raise RuntimeError("typed preview failed or mutated committed revision")
  if result.get("committed",{}).get("revision")!=8 or not result.get("validation",{}).get("mission_complete"):raise RuntimeError("disposable commit/MIR/replay validation failed")
  host=gateway_call("127.0.0.1",ready["port"],"host_validate",{"expected_revision":8})
  if not host.get("mission_complete"):raise RuntimeError("independent host validation failed")
  # The same real handler must reject whole-body/delete/reorder fields at its schema boundary.
  malformed=request();malformed["replace_function_body"]=True
  bad=dispatch(out,ready["port"],{"authoring_mode":"structural_edit","correlation_id":f"cycle25-schema-deny-{time.time_ns()}","preview_args":malformed})
  if bad.get("schema_ok") is not False or bad.get("stage")!="pi_typescript_schema":raise RuntimeError("whole-body replacement field was not rejected by the active schema")
  write(out/"whole-body-rejection.json",bad)
  runtime=HERE/".runtime/cycle25/preflight";source=pathlib.Path(os.environ.get("PI_CODING_AGENT_DIR",pathlib.Path.home()/".sushi/pi")).expanduser()
  models,key_env=isolated_config(runtime,source);pi_env=os.environ.copy();pi_env.update(key_env);pi_env["PI_CODING_AGENT_DIR"]=str(runtime)
  pi_env["PI_CODING_AGENT_SESSION_DIR"]=str(out/"rpc-sessions");pi_env["BASIC_WS_PI_GATEWAY"]=f"127.0.0.1:{ready['port']}"
  pi_env["BASIC_WS_AUTHORING_MODE"]="structural_edit"
  base=["pi","--provider","sushi","--model",MODEL,"--thinking","low","--extension",str(HERE/"extension.ts"),
   "--no-extensions","--no-mcp","--no-skills","--no-context-files","--no-prompt-templates","--no-builtin-tools","--no-tools","--tools",",".join(TOOLS)]
  rpc_preflight(pi_env,base,out,TOOLS)
  summary={"schema":"basic-workspace.cycle25-preflight","version":1,"inference_performed":False,
   "baseline":{"revision":7,"authentic_cycle24_operations":6,"portable_identities":17,"reconstruction":"passed"},
   "active_tools":inventory,"schema_bytes":(out/"tool-schemas.json").stat().st_size,
   "production_typescript_jsonl_dispatch":"passed","preview_non_mutating":True,"rejected_controls":[r["code"] for r in result["controls"]],
   "disposable_commit_revision":result["committed"]["revision"],"new_statement_handle":result["committed"]["new_statement_handle"],
   "host_validation":host["mission_complete"],"interpreter_jit":host["engines_agree"],"fresh_replay":host["replay"]["passed"],
   "pi_model_available":json.loads((out/"pi-rpc-preflight.json").read_text()).get("model_available"),
   "whole_body_edit_schema_rejected":True}
  write(out/"summary.json",summary);print(json.dumps(summary,indent=2))
 finally:stop(proc)
if __name__=="__main__":main()
