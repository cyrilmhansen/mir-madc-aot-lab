#!/usr/bin/env python3
"""Run one bounded genuine Pi/Sushi Cycle 28 conditional refactor."""
from __future__ import annotations
import argparse,json,os,pathlib,select,socket,subprocess,sys,time,urllib.request
HERE=pathlib.Path(__file__).resolve().parent;ROOT=HERE.parent
sys.path.insert(0,str(HERE))
from run_cycle16 import MODEL,isolated_config,rpc_preflight,gateway_call
from pi_lifecycle import run_pi_observed
TOOLS=["workspace_discover_functions","workspace_inspect_program","workspace_commit_preview","workspace_validate_mission","workspace_preview_conditional_edit"]

def write(p,v):pathlib.Path(p).write_text(json.dumps(v,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
def stop(p):
 if p and p.poll() is None:
  p.terminate()
  try:p.wait(timeout=5)
  except subprocess.TimeoutExpired:p.kill();p.wait()
def wait_http(url,timeout=10):
 end=time.monotonic()+timeout
 while time.monotonic()<end:
  try:
   with urllib.request.urlopen(url,timeout=1) as r:
    if r.status==200:return
  except Exception:time.sleep(.1)
 raise RuntimeError("live loopback viewer did not start")
def main():
 ap=argparse.ArgumentParser();ap.add_argument("--output",type=pathlib.Path,default=HERE/"results/cycle28-conditional-refactor/real-agent-01");ap.add_argument("--timeout",type=int,default=240);a=ap.parse_args();out=a.output.resolve()
 if out.exists() and any(out.iterdir()):raise SystemExit(f"refusing to overwrite evidence: {out}")
 out.mkdir(parents=True,exist_ok=True)
 source=pathlib.Path(os.environ.get("PI_CODING_AGENT_DIR",pathlib.Path.home()/".sushi/pi")).expanduser()
 runtime=HERE/".runtime/cycle28/real-agent-01";_,key_env=isolated_config(runtime,source)
 env=os.environ.copy();env.update(key_env);env["PI_CODING_AGENT_DIR"]=str(runtime);env["PI_CODING_AGENT_SESSION_DIR"]=str(out/"pi-sessions");env["BASIC_WS_AUTHORING_MODE"]="conditional_edit"
 env["PYTHONPATH"]=str(ROOT)+os.pathsep+str(HERE)+os.pathsep+env.get("PYTHONPATH","")
 with socket.socket() as s:s.bind(("127.0.0.1",0));port=s.getsockname()[1]
 gerr=(out/"gateway-stderr.log").open("w",encoding="utf-8")
 gateway=subprocess.Popen([sys.executable,str(HERE/"cycle28_gateway.py"),"--output",str(out),"--contract",str(HERE/"results/cycle28-conditional-refactor/contracts/mission.json"),"--port",str(port)],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=gerr,text=True,env=env)
 viewer=None
 try:
  if not select.select([gateway.stdout],[],[],60)[0]:raise RuntimeError("cycle28 verified baseline gateway startup timed out")
  ready=json.loads(gateway.stdout.readline())
  if not ready.get("ready") or ready.get("revision")!=10 or ready.get("identity_count")!=23:raise RuntimeError(f"baseline verification failed: {ready}")
  env["BASIC_WS_PI_GATEWAY"]=f"127.0.0.1:{ready['port']}";write(out/"gateway-ready.json",{k:v for k,v in ready.items() if k!="port"}|{"host":"127.0.0.1","port":ready["port"]})
  viewer=subprocess.Popen([sys.executable,str(ROOT/"scripts/basic-visual.py"),"live",str(out),"--port","0"],stdout=subprocess.PIPE,stderr=(out/"viewer-stderr.log").open("w"),text=True,env=env)
  banner=viewer.stdout.readline().strip();url=banner.split(": ",1)[-1]
  if not url.startswith("http://127.0.0.1:"):raise RuntimeError("loopback viewer did not bind")
  (out/"viewer-url.txt").write_text(url+"\n");wait_http(url)
  base=["pi","--provider","sushi","--model",MODEL,"--thinking","low","--extension",str(HERE/"extension.ts"),"--no-extensions","--no-mcp","--no-skills","--no-context-files","--no-prompt-templates","--no-builtin-tools","--no-tools","--tools",",".join(TOOLS)]
  rpc_preflight(env,base,out,TOOLS)
  inventory=json.loads((out/"tool-inventory.json").read_text());schemas=json.loads((out/"tool-schemas.json").read_text());write(out/"preflight-verification.json",{"model":MODEL,"pi_version":"1.5.0","active_tools":inventory.get("tools"),"expected_tools":TOOLS,"tool_schema_bytes":(out/"tool-schemas.json").stat().st_size,"baseline_revision":10,"portable_identity_count":23,"inference_started":False})
  prompt=("Mission: Refactor SCORE_CLASS(X) to reuse the existing IS_AT_CAP(X) helper for the final category. Preserve its behavior: normalized scores below 20 return 0; 20 through 44 return 1; 45 through 49 return 2; and 50 returns 3. Preserve every assignment, branch and all other functions. Do not replace a function body or edit BASIC source text.\n\n"
    "Discover the functions and inspect SCORE_CLASS's typed control structure, current condition and assignment anchor. Identify the existing helper by its discovered portable semantic handle. Propose only a condition replacement, with the inspected old condition as its precondition. Preview first, commit only if accepted, then call MIR interpreter/JIT validation at the committed revision.")
  (out/"mission-prompt.txt").write_text(prompt+"\n",encoding="utf-8")
  command=base+["--mode","json","--session-dir",str(out/"pi-sessions"),"--name","Cycle 28 conditional refactor","--print","--",prompt]
  perr=(out/"pi-stderr.log").open("w",encoding="utf-8")
  def publish(state,info):
   try:gateway_call("127.0.0.1",ready["port"],"record_agent_status",{"state":state,"info":info},timeout=5)
   except Exception:pass
  lifecycle=run_pi_observed(command,env=env,timeout_seconds=a.timeout,raw_event_path=out/"pi-session.jsonl",lifecycle_path=out/"pi-lifecycle.jsonl",stderr_file=perr,on_status=publish,no_progress_seconds=15,shutdown_grace_seconds=3);perr.close()
  events=[json.loads(x) for x in (out/"pi-session.jsonl").read_text().splitlines() if x.strip()]
  usage=[]
  for e in events:
   m=e.get("message") or e.get("assistantMessageEvent",{}).get("message")
   if isinstance(m,dict) and isinstance(m.get("usage"),dict):usage.append(m["usage"])
  totals={k:sum(u[k] for u in usage if isinstance(u.get(k),(int,float))) if any(isinstance(u.get(k),(int,float)) for u in usage) else None for k in ("input","output","cacheRead","cacheWrite","totalTokens")}
  status=gateway_call("127.0.0.1",ready["port"],"get_status",{})
  validation=gateway_call("127.0.0.1",ready["port"],"host_validate",{"expected_revision":status["revision"]}) if status["committed"] else {"mission_complete":False,"not_run":True,"revision":status["revision"]}
  write(out/"host-validation.json",validation)
  completion=gateway_call("127.0.0.1",ready["port"],"finalize_session",{"timed_out":lifecycle["timed_out"],"pi_exit_code":lifecycle["exit_code"],"validation":validation,"pi_lifecycle":lifecycle.get("observer",{})});write(out/"completion-states.json",completion)
  replay=subprocess.run([sys.executable,str(ROOT/"scripts/basic-visual.py"),"replay",str(out)],capture_output=True,text=True);(out/"replay-render.stdout.log").write_text(replay.stdout);(out/"replay-render.stderr.log").write_text(replay.stderr)
  starts=[e for e in events if e.get("type")=="tool_execution_start"]
  timing=[json.loads(x) for x in (out/"gateway-tool-timings.jsonl").read_text().splitlines() if x.strip()] if (out/"gateway-tool-timings.jsonl").exists() else []
  summary={"schema":"basic-workspace.cycle28-real-agent-summary","version":1,"campaign_kind":"genuine_pi_model","mission_id":"cycle28.score-class-use-is-at-cap.v1","model":MODEL,"pi_version":"1.5.0","base_revision":10,"current_revision":status["revision"],"accepted_preview_count":sum(e.get("event")=="preview_accepted" for e in map(json.loads,(out/"history.jsonl").read_text().splitlines())),"commit":status["committed"],"host_validation":validation,"completion_states":completion.get("completion_states"),"model_turns":sum(e.get("type")=="turn_end" for e in events),"tool_calls":len(starts),"tool_calls_by_name":{n:sum(e.get("toolName")==n for e in starts) for n in TOOLS},"provider_usage_reported_by_pi":totals,"inference_elapsed_ms":lifecycle.get("elapsed_ms"),"timed_out":lifecycle.get("timed_out"),"exit_code":lifecycle.get("exit_code"),"tool_schema_pretty_bytes":(out/"tool-schemas.json").stat().st_size,"gateway_tool_processing_ms":round(sum(x.get("elapsed_ms",0) for x in timing if x.get("agent_tool")),3),"constructive_stream_bytes":(out/"constructive-operations.json").stat().st_size if (out/"constructive-operations.json").exists() else 0,"journal_bytes":(out/"history.jsonl").stat().st_size,"visual_events":sum(1 for x in (out/"visual-events.jsonl").read_text().splitlines() if x.strip()),"html":"visual-replay-generic.html" if replay.returncode==0 else None,"viewer_url":url,"automatic_retries":0}
  write(out/"summary.json",summary);print(json.dumps({"revision":status["revision"],"committed":status["committed"],"mission_complete":validation.get("mission_complete"),"timed_out":lifecycle.get("timed_out"),"exit_code":lifecycle.get("exit_code"),"summary":str(out/"summary.json")},indent=2))
  return 0 if validation.get("mission_complete") else 1
 finally:
  stop(viewer);stop(gateway);gerr.close()
if __name__=="__main__":raise SystemExit(main())
