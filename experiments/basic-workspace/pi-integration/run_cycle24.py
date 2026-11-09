#!/usr/bin/env python3
"""Run one bounded Pi/Sushi numeric-function creation mission from a verified seed."""
from __future__ import annotations
import argparse,json,os,pathlib,select,socket,subprocess,sys,time,urllib.request
HERE=pathlib.Path(__file__).resolve().parent;ROOT=HERE.parent
sys.path.insert(0,str(HERE))
from run_cycle16 import ATOMIC_TOOLS,MODEL,gateway_call,isolated_config,rpc_preflight
from run_cycle19 import run_session,summarize_session

def write(path,value):path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
def wait_http(url,timeout=10):
 deadline=time.monotonic()+timeout
 while time.monotonic()<deadline:
  try:
   with urllib.request.urlopen(url,timeout=1) as r:
    if r.status==200:return
  except Exception:time.sleep(.1)
 raise RuntimeError("read-only viewer did not become ready")
def stop(proc):
 if proc and proc.poll() is None:
  proc.terminate()
  try:proc.wait(timeout=4)
  except subprocess.TimeoutExpired:proc.kill();proc.wait()
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument("--output",type=pathlib.Path,default=HERE/"results/cycle24-dependency-propagation/mission-1-real-agent-01")
 ap.add_argument("--creation-contract",type=pathlib.Path)
 ap.add_argument("--seed-contract",type=pathlib.Path)
 ap.add_argument("--baseline-stream",type=pathlib.Path)
 ap.add_argument("--baseline-history",type=pathlib.Path)
 ap.add_argument("--baseline-validation",type=pathlib.Path)
 ap.add_argument("--timeout",type=int,default=240);ap.add_argument("--open-browser",action="store_true")
 ap.add_argument("--preflight-only",action="store_true");a=ap.parse_args()
 out=a.output.resolve()
 if out.exists() and any(out.iterdir()):raise SystemExit(f"refusing to overwrite evidence: {out}")
 out.mkdir(parents=True,exist_ok=True)
 defaults=HERE/"results/cycle24-dependency-propagation/contracts";baseline=HERE/"results/cycle21-reusable-maintenance/real-agent-01"
 creation_contract=a.creation_contract or defaults/"mission-1-score-class.json"
 seed_contract=a.seed_contract or defaults/"seed-revision5.json"
 baseline_stream=a.baseline_stream or baseline/"constructive-operations.json"
 baseline_history=a.baseline_history or baseline/"history.jsonl"
 baseline_validation=a.baseline_validation or baseline/"validation.json"
 runtime=HERE/f".runtime/function-create/{out.name}";config=pathlib.Path(os.environ.get("PI_CODING_AGENT_DIR",pathlib.Path.home()/".sushi/pi")).expanduser()
 _models,key_env=isolated_config(runtime,config);env=os.environ.copy();env.update(key_env)
 env["PI_CODING_AGENT_DIR"]=str(runtime);env["PI_CODING_AGENT_SESSION_DIR"]=str(out/"pi-sessions");env["BASIC_WS_AUTHORING_MODE"]="atomic"
 with socket.socket() as reserved:reserved.bind(("127.0.0.1",0));port=reserved.getsockname()[1]
 stderr=(out/"gateway-stderr.log").open("w",encoding="utf-8")
 proc=subprocess.Popen([sys.executable,str(HERE/"cycle19_gateway.py"),"--output",str(out),"--port",str(port),
  "--creation-contract",str(creation_contract),"--seed-contract",str(seed_contract),
  "--baseline-stream",str(baseline_stream),"--baseline-history",str(baseline_history),
  "--baseline-validation",str(baseline_validation)],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=stderr,text=True,env=env)
 viewer=None
 try:
  until=time.monotonic()+30
  while time.monotonic()<until and proc.poll() is None:
   if select.select([proc.stdout],[],[],.1)[0]:break
  else:raise RuntimeError("verified replay gateway failed to start")
  ready=json.loads(proc.stdout.readline())
  mission=json.loads(creation_contract.read_text(encoding="utf-8"))
  if not ready.get("ready") or ready.get("revision")!=mission.get("base_document_revision") or ready.get("phase")!=3 or not ready.get("resume_verification",{}).get("passed"):
   raise RuntimeError(f"baseline verification failed; inference not started: {ready}")
  host,port="127.0.0.1",ready["port"];env["BASIC_WS_PI_GATEWAY"]=f"{host}:{port}"
  write(out/"gateway-ready.json",{k:v for k,v in ready.items() if k!="port"}|{"host":host,"port":port})
  viewer=subprocess.Popen([sys.executable,str(ROOT/"scripts/basic-visual.py"),"live",str(out),"--port","0"],
   stdout=subprocess.PIPE,stderr=(out/"viewer-stderr.log").open("w",encoding="utf-8"),text=True)
  url=viewer.stdout.readline().strip().split(": ",1)[-1]
  if not url.startswith("http://127.0.0.1:"):raise RuntimeError("loopback code-first viewer failed")
  (out/"viewer-url.txt").write_text(url+"\n",encoding="utf-8");wait_http(url)
  base=["pi","--provider","sushi","--model",MODEL,"--thinking","low","--extension",str(HERE/"extension.ts"),
   "--no-extensions","--no-mcp","--no-skills","--no-context-files","--no-prompt-templates","--no-builtin-tools","--no-tools","--tools",",".join(ATOMIC_TOOLS)]
  rpc_preflight(env,base,out,ATOMIC_TOOLS)
  schemas=json.loads((out/"tool-schemas.json").read_text())
  constructor=next((x for x in schemas if x.get("name")=="workspace_preview_function"),None)
  schema=json.dumps(constructor or {},separators=(",",":"),ensure_ascii=False)
  if '"function_handle"' not in schema or '"call"' not in schema:raise RuntimeError("active typed constructor schema omits semantic call expression")
  write(out/"preflight-verification.json",{"provider":"sushi","model":MODEL,"pi_version":"1.5.0","active_tools":ATOMIC_TOOLS,
   "tool_schema_bytes":(out/"tool-schemas.json").stat().st_size,"baseline_revision":mission["base_document_revision"],"baseline_reconstruction_verified":True,
   "mission_contract":mission["mission_id"],"inference_started":False,
   "model_preflight_source":json.loads((out/"pi-rpc-preflight.json").read_text())})
  if a.preflight_only:
   write(out/"preflight-complete.json",{"passed":True,"inference_started":False,"model":MODEL,
    "active_tools":ATOMIC_TOOLS,"tool_schema_bytes":(out/"tool-schemas.json").stat().st_size})
   print(json.dumps({"preflight_passed":True,"inference_started":False,"output":str(out)},indent=2));return 0
  if a.open_browser:
   import webbrowser;webbrowser.open(url)
  contract=mission; fn=contract["function"]
  prompt=("Mission: "+contract["objective"]+" Start by discovering the current functions and inspecting the program. "
   "Use the discovered stable portable function handles in typed call expressions. A handle may retain an older spelling after its source function is renamed; inspect both handle and current source name and use the handle in calls. "
   f"Construct only {fn['name']}({fn['parameter']}), using the available numeric assignments, comparisons and structured IF statements. "
   "Preview the complete function, commit only an accepted preview, then request MIR interpreter/JIT validation at the current revision. "
   "The host gateway independently checks both dependency bindings, the preserved existing functions, and the finite behavior oracle. "
   "Do not use source text or modify existing definitions.")
  (out/"mission-prompt.txt").write_text(prompt+"\n",encoding="utf-8")
  session=run_session(phase=3,prompt=prompt,output=out,base=base,env=env,host=host,port=port,timeout=a.timeout)
  metrics=summarize_session(out,3,session);write(out/"session-metrics.json",metrics)
  status=gateway_call(host,port,"get_status",{})
  validation=gateway_call(host,port,"host_validate",{"expected_revision":status["revision"]}) if status["committed"] else None
  if validation:write(out/"mission-3-validation-host.json",validation)
  else:write(out/"mission-3-validation-host.json",{"mission_complete":False,"not_run":True,"revision":status["revision"]})
  completion=gateway_call(host,port,"finalize_session",{"timed_out":bool(session.get("timed_out")),"pi_exit_code":session.get("exit_code"),
   "validation":validation,"pi_lifecycle":session.get("observer",{})})
  write(out/"completion-states.json",completion)
  replay=subprocess.run([sys.executable,str(ROOT/"scripts/basic-visual.py"),"replay",str(out)],capture_output=True,text=True)
  if replay.returncode:(out/"visual-replay-error.txt").write_text(replay.stderr,encoding="utf-8")
  timings=[json.loads(x) for x in (out/"gateway-tool-timings.jsonl").read_text().splitlines() if x.strip()]
  write(out/"summary.json",{"schema":"basic-workspace.cycle24-creation-session","version":1,"campaign_kind":"genuine_pi",
   "mission_id":contract["mission_id"],"model":MODEL,"pi_version":"1.5.0",
   "baseline_revision":contract["base_document_revision"],
   "workspace_revision":status["revision"],"committed":status["committed"],"host_validation":validation,
   "completion_states":completion.get("completion_states"),"session":metrics,"active_tools":ATOMIC_TOOLS,
   "tool_schema_bytes":(out/"tool-schemas.json").stat().st_size,"gateway_tool_processing_ms":round(sum(r.get("elapsed_ms",0) for r in timings if r.get("agent_tool")),3),
   "constructive_stream_bytes":(out/"constructive-operations.json").stat().st_size if (out/"constructive-operations.json").exists() else 0,
   "visual_html":str(out/"visual-replay-generic.html") if replay.returncode==0 else None,"viewer_url":url,
   "automatic_retries":0,"timeout_seconds":a.timeout})
  print(json.dumps({"workspace_revision":status["revision"],"committed":status["committed"],
   "mission_complete":bool(validation and validation.get("mission_complete")),"completion_states":completion.get("completion_states"),
   "summary":str(out/"summary.json")},indent=2))
  return 0 if validation and validation.get("mission_complete") else 1
 finally:
  stop(proc);stop(viewer);stderr.close()
if __name__=="__main__":raise SystemExit(main())
