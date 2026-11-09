#!/usr/bin/env python3
"""Run one bounded Cycle 26 Pi/Sushi semantic rename session."""
from __future__ import annotations
import argparse,json,os,pathlib,select,socket,subprocess,sys,time,urllib.request
HERE=pathlib.Path(__file__).resolve().parent;ROOT=HERE.parent
sys.path.insert(0,str(HERE))
from run_cycle16 import MODEL,isolated_config,rpc_preflight,gateway_call
from pi_lifecycle import run_pi_observed
TOOLS=["workspace_discover_functions","workspace_inspect_program","workspace_commit_preview","workspace_validate_mission","workspace_preview_rename"]
def write(p,v):pathlib.Path(p).write_text(json.dumps(v,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
def stop(proc):
 if proc and proc.poll() is None:
  proc.terminate()
  try:proc.wait(timeout=5)
  except subprocess.TimeoutExpired:proc.kill();proc.wait()
def wait_http(url,timeout=10):
 end=time.monotonic()+timeout
 while time.monotonic()<end:
  try:
   with urllib.request.urlopen(url,timeout=1) as r:
    if r.status==200:return
  except Exception:time.sleep(.1)
 raise RuntimeError("read-only live viewer did not become ready")
def metrics(path,lifecycle):
 events=[json.loads(x) for x in pathlib.Path(path).read_text(encoding="utf-8").splitlines() if x.strip()]
 usage=[]
 for e in events:
  m=e.get("message") or e.get("assistantMessageEvent",{}).get("message")
  if isinstance(m,dict) and isinstance(m.get("usage"),dict):usage.append(m["usage"])
 totals={k:sum(u[k] for u in usage if isinstance(u.get(k),(int,float))) if any(isinstance(u.get(k),(int,float)) for u in usage) else None
         for k in ("input","output","cacheRead","cacheWrite","totalTokens")}
 starts=[e for e in events if e.get("type")=="tool_execution_start"]
 return {"turns":sum(e.get("type")=="turn_end" for e in events),"tool_calls":len(starts),
  "tool_calls_by_name":{n:sum(e.get("toolName")==n for e in starts) for n in TOOLS},"usage_reported_by_pi":totals,
  "event_count":len(events),"event_stream_bytes":pathlib.Path(path).stat().st_size,
  "elapsed_ms":lifecycle.get("elapsed_ms"),"timed_out":lifecycle.get("timed_out"),"exit_code":lifecycle.get("exit_code"),
  "observer":lifecycle.get("observer"),"pending_tool_ids":lifecycle.get("pending_tool_ids",[])}
def main():
 ap=argparse.ArgumentParser();ap.add_argument("--output",type=pathlib.Path,required=True);ap.add_argument("--timeout",type=int,default=240);a=ap.parse_args()
 out=a.output.resolve()
 if out.exists() and any(out.iterdir()):raise SystemExit(f"refusing to overwrite evidence: {out}")
 out.mkdir(parents=True,exist_ok=True)
 runtime=HERE/".runtime/cycle26/real-agent-01";source=pathlib.Path(os.environ.get("PI_CODING_AGENT_DIR",pathlib.Path.home()/".sushi/pi")).expanduser()
 _,key_env=isolated_config(runtime,source);env=os.environ.copy();env.update(key_env)
 env["PI_CODING_AGENT_DIR"]=str(runtime);env["PI_CODING_AGENT_SESSION_DIR"]=str(out/"pi-sessions");env["BASIC_WS_AUTHORING_MODE"]="rename"
 with socket.socket() as reserve:reserve.bind(("127.0.0.1",0));port=reserve.getsockname()[1]
 err=(out/"gateway-stderr.log").open("w",encoding="utf-8")
 gateway=subprocess.Popen([sys.executable,str(HERE/"cycle26_gateway.py"),"--output",str(out),"--port",str(port)],
  stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=err,text=True,env=env)
 viewer=None
 try:
  if not select.select([gateway.stdout],[],[],30)[0]:raise RuntimeError("verified revision-8 rename gateway did not start")
  ready=json.loads(gateway.stdout.readline())
  if not ready.get("ready") or ready.get("revision")!=8 or ready.get("identity_count")!=18:raise RuntimeError(f"Cycle 25 stream reconstruction failed: {ready}")
  env["BASIC_WS_PI_GATEWAY"]=f"127.0.0.1:{ready['port']}"
  write(out/"gateway-ready.json",{k:v for k,v in ready.items() if k!="port"}|{"host":"127.0.0.1","port":ready["port"]})
  viewer=subprocess.Popen([sys.executable,str(ROOT/"scripts/basic-visual.py"),"live",str(out),"--port","0"],
   stdout=subprocess.PIPE,stderr=(out/"viewer-stderr.log").open("w",encoding="utf-8"),text=True,env=env)
  url=viewer.stdout.readline().strip().split(": ",1)[-1]
  if not url.startswith("http://127.0.0.1:"):raise RuntimeError("loopback live viewer failed")
  (out/"viewer-url.txt").write_text(url+"\n",encoding="utf-8");wait_http(url)
  base=["pi","--provider","sushi","--model",MODEL,"--thinking","low","--extension",str(HERE/"extension.ts"),
   "--no-extensions","--no-mcp","--no-skills","--no-context-files","--no-prompt-templates","--no-builtin-tools","--no-tools","--tools",",".join(TOOLS)]
  rpc_preflight(env,base,out,TOOLS)
  schemas=json.loads((out/"tool-schemas.json").read_text());inventory=json.loads((out/"tool-inventory.json").read_text())
  schema_bytes=(out/"tool-schemas.json").stat().st_size
  write(out/"preflight-verification.json",{"model":MODEL,"pi_version":"1.5.0","active_tools":inventory.get("tools"),
   "expected_tools":TOOLS,"schema_bytes":schema_bytes,"baseline_revision":8,"baseline_identity_count":18,"inference_started":False})
  prompt=("Mission: Rename the existing numeric function CLAMP_SCORE to NORMALIZE_SCORE. Preserve the function's semantic identity, its parameter and all statement identities, update every bound reference, and preserve IS_PASSING, SCORE_CLASS, their dependency bindings, and all behavior. Do not create a replacement function or edit source text.\n\n"
   "First discover the functions, then inspect the target's stable semantic handle, current source name, and bound references. Propose the rename against revision 8 using the discovered portable handle and observed current name. Preview before committing; commit only an accepted preview, then request MIR interpreter/JIT validation at the committed revision.")
  (out/"mission-prompt.txt").write_text(prompt+"\n",encoding="utf-8")
  command=base+["--mode","json","--session-dir",str(out/"pi-sessions"),"--name","Cycle 26 identity-preserving rename","--print","--",prompt]
  pi_err=(out/"pi-stderr.log").open("w",encoding="utf-8")
  def publish(state,info):
   try:gateway_call("127.0.0.1",ready["port"],"record_agent_status",{"state":state,"info":info},timeout=5)
   except Exception:pass
  lifecycle=run_pi_observed(command,env=env,timeout_seconds=a.timeout,raw_event_path=out/"pi-session.jsonl",
   lifecycle_path=out/"pi-lifecycle.jsonl",stderr_file=pi_err,on_status=publish,no_progress_seconds=15,shutdown_grace_seconds=3)
  pi_err.close();session=metrics(out/"pi-session.jsonl",lifecycle)
  status=gateway_call("127.0.0.1",ready["port"],"get_status",{})
  validation=gateway_call("127.0.0.1",ready["port"],"host_validate",{"expected_revision":status["revision"]}) if status["committed"] else None
  write(out/"host-validation.json",validation or {"mission_complete":False,"not_run":True,"revision":status["revision"]})
  completion=gateway_call("127.0.0.1",ready["port"],"finalize_mission",{"timed_out":lifecycle["timed_out"],
   "pi_exit_code":lifecycle["exit_code"],"validation":validation,"pi_lifecycle":lifecycle.get("observer",{})})
  write(out/"completion-states.json",completion)
  replay=subprocess.run([sys.executable,str(ROOT/"scripts/basic-visual.py"),"replay",str(out)],capture_output=True,text=True)
  if replay.returncode:write(out/"visual-replay-error.txt",{"error":replay.stderr})
  timings=[json.loads(x) for x in (out/"gateway-tool-timings.jsonl").read_text().splitlines() if x.strip()]
  attempts=[e for e in map(json.loads,(out/"pi-session.jsonl").read_text().splitlines()) if e.get("type")=="tool_execution_end" and e.get("toolName")=="workspace_preview_rename"]
  errors=sum((e.get("result") or {}).get("details",{}).get("ok") is False for e in attempts)
  summary={"schema":"basic-workspace.cycle26-session-summary","version":1,"campaign_kind":"genuine_pi_model",
   "mission_id":"cycle26.rename-normalizer.v1","model":MODEL,"pi_version":"1.5.0","base_revision":8,
   "workspace_revision":status["revision"],"committed":status["committed"],"host_validation":validation,
   "completion_states":completion.get("completion_states"),"session":session,"active_tools":TOOLS,"tool_schema_bytes":schema_bytes,
   "gateway_tool_processing_ms":round(sum(x.get("elapsed_ms",0) for x in timings if x.get("agent_tool")),3),
   "preview_attempts":len(attempts),"rejected_previews":errors,"automatic_retries":0,"timeout_seconds":a.timeout,
   "constructive_stream_bytes":(out/"constructive-operations.json").stat().st_size if (out/"constructive-operations.json").exists() else 0,
   "visual_html":"visual-replay-generic.html" if replay.returncode==0 else None,"viewer_url":url}
  write(out/"summary.json",summary)
  print(json.dumps({"revision":status["revision"],"committed":status["committed"],
   "mission_complete":bool(validation and validation.get("mission_complete")),"timed_out":lifecycle["timed_out"],
   "exit_code":lifecycle["exit_code"],"summary":str(out/"summary.json")},indent=2))
  if lifecycle["timed_out"]:return 2
  return 0 if validation and validation.get("mission_complete") else (0 if not status["committed"] else 1)
 finally:
  stop(viewer);stop(gateway);err.close()
if __name__=="__main__":raise SystemExit(main())
