#!/usr/bin/env python3
"""Run one bounded genuine Pi/Sushi Cycle 25 structural maintenance mission."""
from __future__ import annotations
import argparse,json,os,pathlib,select,socket,subprocess,sys,time,urllib.request,webbrowser
HERE=pathlib.Path(__file__).resolve().parent;ROOT=HERE.parent
sys.path.insert(0,str(HERE))
from run_cycle16 import MODEL,isolated_config,rpc_preflight,gateway_call
from pi_lifecycle import run_pi_observed
TOOLS=["workspace_discover_functions","workspace_inspect_program","workspace_commit_preview","workspace_validate_mission","workspace_preview_structural_edit"]
def write(p,v):pathlib.Path(p).write_text(json.dumps(v,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
def wait_http(url,timeout=10):
 end=time.monotonic()+timeout
 while time.monotonic()<end:
  try:
   with urllib.request.urlopen(url,timeout=1) as r:
    if r.status==200:return
  except Exception:time.sleep(.1)
 raise RuntimeError(f"loopback viewer did not become ready: {url}")
def stop(proc):
 if proc and proc.poll() is None:
  proc.terminate()
  try:proc.wait(timeout=5)
  except subprocess.TimeoutExpired:proc.kill();proc.wait()
def session_metrics(path,lifecycle):
 events=[json.loads(line) for line in pathlib.Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
 usage=[]
 for event in events:
  msg=event.get("message") or event.get("assistantMessageEvent",{}).get("message")
  if isinstance(msg,dict) and isinstance(msg.get("usage"),dict):usage.append(msg["usage"])
 totals={key:sum(row[key] for row in usage if isinstance(row.get(key),(int,float))) if any(isinstance(row.get(key),(int,float)) for row in usage) else None
  for key in ("input","output","cacheRead","cacheWrite","totalTokens")}
 starts=[e for e in events if e.get("type")=="tool_execution_start"]
 ends=[e for e in events if e.get("type")=="tool_execution_end"]
 return {"turns":sum(e.get("type")=="turn_end" for e in events),"tool_call_starts":len(starts),"tool_call_ends":len(ends),
  "tool_calls_by_name":{tool:sum(e.get("toolName")==tool for e in starts) for tool in TOOLS},
  "usage_reported_by_pi":totals,"event_count":len(events),"event_stream_bytes":pathlib.Path(path).stat().st_size,
  "elapsed_ms":lifecycle.get("elapsed_ms"),"timed_out":lifecycle.get("timed_out"),"exit_code":lifecycle.get("exit_code"),
  "observer":lifecycle.get("observer"),"pending_tool_ids":lifecycle.get("pending_tool_ids",[])}
def main():
 ap=argparse.ArgumentParser();ap.add_argument("--output",type=pathlib.Path,default=HERE/"results/cycle25-structural-edit/real-agent-01")
 ap.add_argument("--timeout",type=int,default=240);ap.add_argument("--open-browser",action="store_true");a=ap.parse_args();out=a.output.resolve()
 if out.exists() and any(out.iterdir()):raise SystemExit(f"refusing to overwrite evidence: {out}")
 out.mkdir(parents=True,exist_ok=True)
 runtime=HERE/".runtime/cycle25/real-agent-01";source=pathlib.Path(os.environ.get("PI_CODING_AGENT_DIR",pathlib.Path.home()/".sushi/pi")).expanduser()
 _,key_env=isolated_config(runtime,source);env=os.environ.copy();env.update(key_env);env["PI_CODING_AGENT_DIR"]=str(runtime)
 env["PI_CODING_AGENT_SESSION_DIR"]=str(out/"pi-sessions");env["BASIC_WS_AUTHORING_MODE"]="structural_edit"
 with socket.socket() as reserve:reserve.bind(("127.0.0.1",0));port=reserve.getsockname()[1]
 err=(out/"gateway-stderr.log").open("w",encoding="utf-8")
 gateway=subprocess.Popen([sys.executable,str(HERE/"cycle25_gateway.py"),"--output",str(out),"--port",str(port)],
  stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=err,text=True,env=env)
 viewer=pi=None
 try:
  deadline=time.monotonic()+20
  while time.monotonic()<deadline and gateway.poll() is None:
   if select.select([gateway.stdout],[],[],.1)[0]:break
  else:raise RuntimeError("Cycle25 revision-7 reconstruction gateway failed to start")
  ready=json.loads(gateway.stdout.readline())
  if not ready.get("ready") or ready.get("revision")!=7 or ready.get("identity_count")!=17:raise RuntimeError(f"verified baseline mismatch: {ready}")
  env["BASIC_WS_PI_GATEWAY"]=f"127.0.0.1:{ready['port']}"
  write(out/"gateway-ready.json",{k:v for k,v in ready.items() if k!="port"}|{"host":"127.0.0.1","port":ready["port"]})
  viewer=subprocess.Popen([sys.executable,str(ROOT/"scripts/basic-visual.py"),"live",str(out),"--port","0"],
   stdout=subprocess.PIPE,stderr=(out/"viewer-stderr.log").open("w",encoding="utf-8"),text=True,env=env)
  banner=viewer.stdout.readline().strip();url=banner.split(": ",1)[-1]
  if not url.startswith("http://127.0.0.1:"):raise RuntimeError("read-only live viewer did not start on loopback")
  (out/"viewer-url.txt").write_text(url+"\n",encoding="utf-8");wait_http(url)
  base=["pi","--provider","sushi","--model",MODEL,"--thinking","low","--extension",str(HERE/"extension.ts"),
   "--no-extensions","--no-mcp","--no-skills","--no-context-files","--no-prompt-templates","--no-builtin-tools","--no-tools","--tools",",".join(TOOLS)]
  rpc_preflight(env,base,out,TOOLS)
  schemas=json.loads((out/"tool-schemas.json").read_text(encoding="utf-8"))
  inventory=json.loads((out/"tool-inventory.json").read_text(encoding="utf-8"))
  write(out/"preflight-verification.json",{"inference_started":False,"model":MODEL,"pi_version":"1.5.0",
   "active_tools":inventory.get("tools"),"expected_tools":TOOLS,"tool_schema_bytes":(out/"tool-schemas.json").stat().st_size,
   "structural_tool_schema":next((s for s in schemas if s.get("name")=="workspace_preview_structural_edit"),None),
   "revision7_baseline_verified":True,"live_viewer_url":url})
  if a.open_browser:webbrowser.open(url)
  prompt=("Mission: Extend SCORE_CLASS(X) with one additional category: return 0 for normalized scores below 20, "
   "1 for 20 through 44, 2 for 45 through 49, and 3 for 50. CLAMP_SCORE and IS_PASSING must remain unchanged. "
   "Use a bound call to the discovered CLAMP_SCORE function.\n\n"
   "First discover the functions and inspect SCORE_CLASS and its semantic statement handles. Use the inspected function-body "
   "boundary anchor to propose exactly one typed IF insertion. Do not replace the function body, edit other functions, or use BASIC source text. "
   "Preview first, commit only an accepted preview, then request MIR interpreter/JIT validation at the committed revision. "
   "The host checks the complete candidate and an independent numeric oracle.")
  (out/"mission-prompt.txt").write_text(prompt+"\n",encoding="utf-8")
  command=base+["--mode","json","--session-dir",str(out/"pi-sessions"),"--name","Cycle 25 structural insertion","--print","--",prompt]
  pi_err=(out/"pi-stderr.log").open("w",encoding="utf-8")
  def publish(state,info):
   try:gateway_call("127.0.0.1",ready["port"],"record_agent_status",{"state":state,"info":info},timeout=5)
   except Exception:pass
  lifecycle=run_pi_observed(command,env=env,timeout_seconds=a.timeout,raw_event_path=out/"pi-session.jsonl",
   lifecycle_path=out/"pi-lifecycle.jsonl",stderr_file=pi_err,on_status=publish,no_progress_seconds=15,shutdown_grace_seconds=3)
  pi_err.close();metrics=session_metrics(out/"pi-session.jsonl",lifecycle)
  status=gateway_call("127.0.0.1",ready["port"],"get_status",{})
  validation=gateway_call("127.0.0.1",ready["port"],"host_validate",{"expected_revision":status["revision"]}) if status["committed"] else None
  write(out/"host-validation.json",validation or {"mission_complete":False,"not_run":True,"revision":status["revision"]})
  completion=gateway_call("127.0.0.1",ready["port"],"finalize_mission",{"timed_out":lifecycle["timed_out"],
   "pi_exit_code":lifecycle["exit_code"],"validation":validation,"pi_lifecycle":lifecycle.get("observer",{})})
  write(out/"completion-states.json",completion)
  replay=subprocess.run([sys.executable,str(ROOT/"scripts/basic-visual.py"),"replay",str(out)],capture_output=True,text=True)
  if replay.returncode:(out/"visual-replay-error.txt").write_text(replay.stderr,encoding="utf-8")
  tool_events=[e for e in json.loads((out/"pi-session.jsonl").read_text().splitlines()[0]).get("events",[])] if False else []
  timing=rows=([json.loads(line) for line in (out/"gateway-tool-timings.jsonl").read_text().splitlines() if line.strip()] if (out/"gateway-tool-timings.jsonl").exists() else [])
  pi_events=[json.loads(line) for line in (out/"pi-session.jsonl").read_text().splitlines() if line.strip()]
  previews=[e for e in pi_events if e.get("type")=="tool_execution_end" and e.get("toolName")=="workspace_preview_structural_edit"]
  rejected=sum(bool((e.get("result") or {}).get("details",{}).get("ok") is False) for e in previews)
  summary={"schema":"basic-workspace.cycle25-session-summary","version":1,"campaign_kind":"genuine_pi_model",
   "mission_id":"cycle25.score-class-fourth-category.v1","model":MODEL,"pi_version":"1.5.0","base_revision":7,
   "workspace_revision":status["revision"],"committed":status["committed"],"host_validation":validation,
   "completion_states":completion.get("completion_states"),"session":metrics,"active_tools":TOOLS,
   "tool_schema_bytes":(out/"tool-schemas.json").stat().st_size,
   "gateway_tool_processing_ms":round(sum(x.get("elapsed_ms",0) for x in timing if x.get("agent_tool")),3),
   "preview_attempts":len(previews),"pi_preview_tool_errors":rejected,"automatic_retries":0,"timeout_seconds":a.timeout,
   "constructive_stream_bytes":(out/"constructive-operations.json").stat().st_size if (out/"constructive-operations.json").exists() else 0,
   "visual_html":str(out/"visual-replay-generic.html") if replay.returncode==0 else None,"viewer_url":url}
  write(out/"summary.json",summary)
  print(json.dumps({"revision":status["revision"],"committed":status["committed"],"mission_complete":bool(validation and validation.get("mission_complete")),
   "pi_timed_out":lifecycle["timed_out"],"pi_exit_code":lifecycle["exit_code"],"summary":str(out/"summary.json")},indent=2))
  if lifecycle["timed_out"]:return 2
  return 0 if validation and validation.get("mission_complete") else (0 if not status["committed"] else 1)
 finally:
  stop(pi);stop(viewer);stop(gateway);err.close()
if __name__=="__main__":raise SystemExit(main())
