#!/usr/bin/env python3
"""No-inference production TypeScript/JSONL preflight for Cycle 26 rename."""
from __future__ import annotations
import argparse,json,os,pathlib,socket,subprocess,sys,time
HERE=pathlib.Path(__file__).resolve().parent;ROOT=HERE.parent
sys.path.insert(0,str(HERE))
from run_cycle16 import MODEL,isolated_config,rpc_preflight,gateway_call
TOOLS=["workspace_discover_functions","workspace_inspect_program","workspace_commit_preview","workspace_validate_mission","workspace_preview_rename"]
def write(path,value):pathlib.Path(path).write_text(json.dumps(value,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
def dispatch(out,port,body,tag):
 inp=out/f"{tag}-input.json";result=out/f"{tag}-output.json";write(inp,body)
 env=os.environ.copy();env.update({"BASIC_WS_AUTHORING_MODE":"rename","BASIC_WS_PI_GATEWAY":f"127.0.0.1:{port}",
  "BASIC_WS_DISPATCH_PROBE_INPUT":str(inp),"BASIC_WS_DISPATCH_PROBE_OUTPUT":str(result),
  "NODE_PATH":"/usr/lib/node_modules/@earendil-works/pi-coding-agent/node_modules"})
 proc=subprocess.run(["bun",str(HERE/"cycle20b_dispatch_probe.ts")],env=env,capture_output=True,text=True,timeout=90)
 (out/f"{tag}.stdout.log").write_text(proc.stdout);(out/f"{tag}.stderr.log").write_text(proc.stderr)
 if proc.returncode or not result.exists():raise RuntimeError(f"TypeScript/JSONL dispatch failed: {proc.stderr[-1000:]}")
 return json.loads(result.read_text())
def main():
 ap=argparse.ArgumentParser();ap.add_argument("--output",type=pathlib.Path,required=True);a=ap.parse_args();out=a.output.resolve()
 if out.exists() and any(out.iterdir()):raise SystemExit(f"refusing to overwrite evidence: {out}")
 out.mkdir(parents=True,exist_ok=True);env=os.environ.copy();env["PYTHONPATH"]=str(ROOT)+os.pathsep+str(HERE)+os.pathsep+env.get("PYTHONPATH","")
 with socket.socket() as s:s.bind(("127.0.0.1",0));port=s.getsockname()[1]
 gateway=subprocess.Popen([sys.executable,str(HERE/"cycle26_gateway.py"),"--output",str(out/"gateway-evidence"),"--port",str(port)],
  stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=(out/"gateway-stderr.log").open("w"),text=True,env=env)
 try:
  ready=json.loads(gateway.stdout.readline())
  if not ready.get("ready") or ready.get("revision")!=8 or ready.get("identity_count")!=18:raise RuntimeError(f"revision-8 reconstruction failed: {ready}")
  good={"expected_revision":8,"function_handle":"clamp_score.function","expected_name":"CLAMP_SCORE","new_name":"NORMALIZE_SCORE"}
  controls=[
   {**good,"function_handle":"unknown.function"},
   {**good,"new_name":"IS_PASSING"},
   {**good,"new_name":"BAD NAME"},
   {**good,"function_handle":"is_passing.function"},
   {**good,"expected_revision":7},
   {**good,"expected_name":"NOT_CLAMP_SCORE"},
  ]
  # Keep this direct Workspace control on the isolated revision-8 fixture,
  # before the separate production-path preview/commit advances it.
  collision=gateway_call("127.0.0.1",ready["port"],"deterministic_workspace_control",{"case":"name_collision"})
  invalid=gateway_call("127.0.0.1",ready["port"],"deterministic_workspace_control",{"case":"invalid_identifier"})
  if collision.get("code")!="NAME_COLLISION" or invalid.get("code")!="INVALID_NAME":
   raise RuntimeError(f"Workspace rename collision/identifier checks failed: {collision} {invalid}")
  result=dispatch(out,ready["port"],{"authoring_mode":"rename","correlation_id":f"cycle26-preflight-{time.time_ns()}",
   "preview_args":good,"controls":controls,"commit":True,"duplicate_commit":True},"production-dispatch")
  schemas=result["schemas"];inventory=result["active_tools"]
  write(out/"tool-inventory.json",{"tools":inventory,"source":"Pi extension active tool registry"});write(out/"tool-schemas.json",schemas)
  if inventory!=TOOLS or not result.get("schema_ok"):raise RuntimeError("actual active Pi tools/schema mismatch")
  codes=[row.get("code") for row in result.get("controls",[])]
  if codes!=["MISSION_RENAME_SCOPE","MISSION_RENAME_NAME","MISSION_RENAME_NAME","MISSION_RENAME_SCOPE","STALE_REVISION","RENAME_PRECONDITION_FAILED"]:
   raise RuntimeError(f"rename negative controls failed: {codes}")
  if not result.get("preview",{}).get("candidate_is_preview_only") or result["preview"].get("semantic_identity_preserved") is not True:
   raise RuntimeError("rename preview was not accepted or mutated authority")
  if result.get("committed",{}).get("revision")!=9 or not result.get("validation",{}).get("mission_complete"):
   raise RuntimeError("production-path rename commit/host validation failed")
  if result.get("duplicate_commit",{}).get("committed") is not False:
   raise RuntimeError("duplicate commit was not rejected")
  bad={**good,"unrelated_field":1}
  denied=dispatch(out,ready["port"],{"authoring_mode":"rename","correlation_id":f"cycle26-schema-{time.time_ns()}","preview_args":bad},"unknown-field")
  if denied.get("schema_ok") is not False or denied.get("stage")!="pi_typescript_schema":raise RuntimeError("unknown semantic field passed Pi schema")
  write(out/"unknown-field-rejection.json",denied)
  cfg=HERE/".runtime/cycle26/preflight";source=pathlib.Path(os.environ.get("PI_CODING_AGENT_DIR",pathlib.Path.home()/".sushi/pi")).expanduser()
  _,key_env=isolated_config(cfg,source);pi_env=os.environ.copy();pi_env.update(key_env);pi_env["PI_CODING_AGENT_DIR"]=str(cfg)
  pi_env["PI_CODING_AGENT_SESSION_DIR"]=str(out/"rpc-sessions");pi_env["BASIC_WS_PI_GATEWAY"]=f"127.0.0.1:{ready['port']}";pi_env["BASIC_WS_AUTHORING_MODE"]="rename"
  base=["pi","--provider","sushi","--model",MODEL,"--thinking","low","--extension",str(HERE/"extension.ts"),
   "--no-extensions","--no-mcp","--no-skills","--no-context-files","--no-prompt-templates","--no-builtin-tools","--no-tools","--tools",",".join(TOOLS)]
  rpc_preflight(pi_env,base,out,TOOLS)
  schema_bytes=(out/"tool-schemas.json").stat().st_size
  write(out/"summary.json",{"schema":"basic-workspace.cycle26-preflight","version":1,"inference_performed":False,
   "baseline_revision":8,"baseline_handles":18,"active_tools":inventory,"schema_bytes":schema_bytes,
   "production_typescript_jsonl_dispatch":"passed","preview_non_mutating":True,"negative_control_codes":codes,
   "commit_revision":9,"duplicate_commit_rejected":True,"unknown_field_rejected_by_schema":True,
   "interpreter_jit_and_replay":result["validation"]["replay"]["passed"],
   "pi_model_available":json.loads((out/"pi-rpc-preflight.json").read_text()).get("model_available")})
  print((out/"summary.json").read_text())
 finally:
  if gateway.poll() is None:gateway.terminate();gateway.wait(timeout=5)
if __name__=="__main__":main()
