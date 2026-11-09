#!/usr/bin/env python3
"""Run Cycle 29's two bounded genuine Pi sessions against one Workspace."""
from __future__ import annotations
import argparse,json,os,pathlib,select,socket,subprocess,sys,time,urllib.request,shutil

HERE=pathlib.Path(__file__).resolve().parent;ROOT=HERE.parent
sys.path.insert(0,str(HERE))
from run_cycle16 import MODEL,isolated_config,rpc_preflight,gateway_call
from pi_lifecycle import run_pi_observed,completion_states

ATOMIC=["workspace_discover_functions","workspace_inspect_program","workspace_commit_preview","workspace_validate_mission","workspace_preview_function"]
BLOCK=["workspace_discover_functions","workspace_inspect_program","workspace_commit_preview","workspace_validate_mission","workspace_preview_block_replacement"]

def write(path,data):
    path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def stop(proc):
    if proc is None or proc.poll() is not None:return
    proc.terminate()
    try:proc.wait(timeout=5)
    except subprocess.TimeoutExpired:proc.kill();proc.wait()

def wait_http(url,timeout=15):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        try:
            with urllib.request.urlopen(url,timeout=1) as response:
                if response.status==200:return
        except Exception:time.sleep(.1)
    raise RuntimeError("loopback replay viewer did not start")

def session(*,phase,tools,mode,prompt,out,root_out,env,port,timeout):
    session_dir=out/"pi-sessions";session_dir.mkdir(parents=True,exist_ok=True)
    runtime=HERE/".runtime"/"cycle29"/f"mission-{phase}"
    source=pathlib.Path(os.environ.get("PI_CODING_AGENT_DIR",pathlib.Path.home()/".sushi/pi")).expanduser()
    _models,key_env=isolated_config(runtime,source)
    child_env=os.environ.copy();child_env.update(key_env)
    child_env.update(env)
    child_env["PI_CODING_AGENT_DIR"]=str(runtime)
    child_env["PI_CODING_AGENT_SESSION_DIR"]=str(session_dir)
    child_env["BASIC_WS_AUTHORING_MODE"]=mode
    child_env["BASIC_WS_PI_GATEWAY"]=f"127.0.0.1:{port}"
    child_env["PYTHONPATH"]=str(ROOT)+os.pathsep+str(HERE)+os.pathsep+child_env.get("PYTHONPATH","")
    base=["pi","--provider","sushi","--model",MODEL,"--thinking","low","--extension",str(HERE/"extension.ts"),
        "--no-extensions","--no-mcp","--no-skills","--no-context-files","--no-prompt-templates",
        "--no-builtin-tools","--no-tools","--tools",",".join(tools)]
    rpc_preflight(child_env,base,root_out,tools)
    # Pi's session_start event is captured by the authoritative campaign
    # gateway. Snapshot the active per-session schemas separately here.
    for name in ("tool-inventory.json","tool-schemas.json","pi-rpc-preflight.json","pi-preflight.stderr.log"):
        source=root_out/name
        if source.exists():shutil.copy2(source,out/name)
    write(out/"preflight-verification.json",{"provider":"sushi","model":MODEL,"pi_version":"1.5.0",
        "active_tools":json.loads((out/"tool-inventory.json").read_text()).get("tools"),"expected_tools":tools,
        "schema_bytes":(out/"tool-schemas.json").stat().st_size,"inference_started":False})
    write(out/"mission-prompt.txt",{"mission":phase,"prompt":prompt})
    command=base+["--mode","json","--session-dir",str(session_dir),"--name",f"Cycle 29 mission {phase}","--print","--",prompt]
    stderr=(out/"pi-stderr.log").open("w",encoding="utf-8")
    def publish(state,info):
        try:gateway_call("127.0.0.1",port,"record_agent_status",{"state":state,"info":info},timeout=5)
        except Exception:pass
    started=time.monotonic()
    lifecycle=run_pi_observed(command,env=child_env,timeout_seconds=timeout,
        raw_event_path=out/"pi-session.jsonl",lifecycle_path=out/"pi-lifecycle.jsonl",stderr_file=stderr,
        on_status=publish,no_progress_seconds=15,shutdown_grace_seconds=3)
    stderr.close()
    observer=lifecycle.get("observer",{})
    final_state=("agent_session_completed" if observer.get("agent_settled_seen") else
        "agent_timed_out" if lifecycle.get("timed_out") else "agent_process_exited_without_settlement")
    gateway_call("127.0.0.1",port,"record_agent_status",{"state":final_state,"info":{
        "description":"Host recorded the completed Pi lifecycle observation after process exit.",
        "agent_end_seen":observer.get("agent_end_seen"),"agent_settled_seen":observer.get("agent_settled_seen"),
        "timed_out":lifecycle.get("timed_out"),"exit_code":lifecycle.get("exit_code")}},timeout=5)
    events=[json.loads(line) for line in (out/"pi-session.jsonl").read_text().splitlines() if line.strip()]
    usage=[]
    for event in events:
        message=event.get("message") or event.get("assistantMessageEvent",{}).get("message")
        if isinstance(message,dict) and isinstance(message.get("usage"),dict):usage.append(message["usage"])
    totals={key:sum(row.get(key,0) for row in usage if isinstance(row.get(key),(int,float))) if any(isinstance(row.get(key),(int,float)) for row in usage) else None
        for key in ("input","output","cacheRead","cacheWrite","totalTokens")}
    starts=[event for event in events if event.get("type")=="tool_execution_start"]
    writes=[json.loads(line) for line in (root_out/"gateway-tool-timings.jsonl").read_text().splitlines() if line.strip()] if (root_out/"gateway-tool-timings.jsonl").exists() else []
    expected_phase=1 if phase=="A" else 2
    timing=[row for row in writes if row.get("phase")==expected_phase]
    result={"mission":phase,"turns":sum(event.get("type")=="turn_end" for event in events),"tool_calls":len(starts),
        "tool_calls_by_name":{tool:sum(row.get("toolName")==tool for row in starts) for tool in tools},
        "tool_schema_pretty_bytes":(out/"tool-schemas.json").stat().st_size,"provider_usage":totals,
        "wall_time_ms":round((time.monotonic()-started)*1000,2),"pi_elapsed_ms":lifecycle.get("elapsed_ms"),
        "timed_out":lifecycle.get("timed_out"),"exit_code":lifecycle.get("exit_code"),"lifecycle":lifecycle,
        "gateway_tool_processing_ms":round(sum(row.get("elapsed_ms",0) for row in timing if row.get("agent_tool")),3),
        "events":len(events),"tool_errors":sum(bool(event.get("isError")) for event in events if event.get("type")=="tool_execution_end")}
    write(out/"session-summary.json",result)
    return result

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=pathlib.Path,default=HERE/"results/cycle29-function-extraction/real-agent-01")
    parser.add_argument("--timeout",type=int,default=240)
    args=parser.parse_args();out=args.output.resolve()
    if out.exists() and any(out.iterdir()):raise SystemExit(f"refusing to overwrite evidence: {out}")
    out.mkdir(parents=True,exist_ok=True)
    env=os.environ.copy();env["PYTHONPATH"]=str(ROOT)+os.pathsep+str(HERE)+os.pathsep+env.get("PYTHONPATH","")
    with socket.socket() as sock:sock.bind(("127.0.0.1",0));port=sock.getsockname()[1]
    gateway_err=(out/"gateway-stderr.log").open("w",encoding="utf-8")
    gateway=subprocess.Popen([sys.executable,str(HERE/"cycle29_gateway.py"),"--output",str(out),"--port",str(port)],
        stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=gateway_err,text=True,env=env)
    viewer=None
    try:
        if not select.select([gateway.stdout],[],[],60)[0]:raise RuntimeError("Cycle 29 baseline reconstruction timed out")
        ready=json.loads(gateway.stdout.readline())
        if not ready.get("ready") or ready.get("revision")!=11 or ready.get("identity_count")!=23:
            raise RuntimeError(f"Verified Cycle 28 baseline failed: {ready}")
        write(out/"gateway-ready.json",{key:value for key,value in ready.items() if key!="port"}|{"host":"127.0.0.1","port":ready["port"]})
        viewer_err=(out/"viewer-stderr.log").open("w",encoding="utf-8")
        viewer=subprocess.Popen([sys.executable,str(ROOT/"scripts/basic-visual.py"),"live",str(out),"--port","0"],
            stdout=subprocess.PIPE,stderr=viewer_err,text=True,env=env)
        banner=viewer.stdout.readline().strip();url=banner.split(": ",1)[-1]
        if not url.startswith("http://127.0.0.1:"):raise RuntimeError("live viewer did not bind to loopback")
        (out/"viewer-url.txt").write_text(url+"\n");wait_http(url)
        print("Live semantic replay is ready at",url,flush=True)

        prompt_a=("Mission A: Create the numeric function BASE_SCORE_CLASS(X). It returns 0 when the normalized score is below 20, and 1 otherwise. "+
            "Use a genuine bound call to the discovered NORMALIZE_SCORE function with portable handle clamp_score.function. Preserve every existing function and data item. "+
            "Discover and inspect the current Workspace first. Construct the function only with the typed constructor tool, preview it, commit only an accepted preview, then request MIR interpreter/JIT validation. Do not send BASIC source text.")
        a=session(phase="A",tools=ATOMIC,mode="atomic_create",prompt=prompt_a,out=out/"mission-a",root_out=out,env=env,port=ready["port"],timeout=args.timeout)
        status=gateway_call("127.0.0.1",ready["port"],"get_status",{})
        host_a=gateway_call("127.0.0.1",ready["port"],"host_validate",{"expected_revision":status["revision"]}) if status["committed"] else {"mission_complete":False,"not_run":True}
        write(out/"mission-a-host-validation.json",host_a)
        states_a=completion_states(committed=status["committed"],validation=host_a,timed_out=a["timed_out"],
            exit_code=a["exit_code"],agent_end_seen=bool(a["lifecycle"].get("observer",{}).get("agent_end_seen")),
            agent_settled_seen=bool(a["lifecycle"].get("observer",{}).get("agent_settled_seen")),
            pending_tool_count=len(a["lifecycle"].get("pending_tool_ids",[])),authorization_status="authorized" if status["committed"] else "not_attempted")
        write(out/"mission-a-completion-states.json",states_a)
        if not status["committed"] or not host_a.get("mission_complete"):
            write(out/"mission-outcome.json",{"mission_a":a,"mission_a_commit":status["committed"],"mission_a_host_validation":host_a,
                "mission_b":"not_started; Mission A did not commit and validate"})
            return 1

        checkpoint=gateway_call("127.0.0.1",ready["port"],"create_mission_b_checkpoint",{})
        if not checkpoint.get("ok"):raise RuntimeError("Host could not create a validated Mission A recovery checkpoint")
        boundary=gateway_call("127.0.0.1",ready["port"],"prepare_mission_b",{"checkpoint":checkpoint["checkpoint"]})
        if not boundary.get("checkpoint_verified") or boundary.get("revision")!=12:raise RuntimeError(f"Mission B recovery checkpoint rejected: {boundary}")
        prompt_b=("Mission B: In SCORE_CLASS(X), replace only the first below-20 classification IF block with a result assignment that calls BASE_SCORE_CLASS(X). "+
            "The helper is already committed and must be discovered under its stable semantic handle. Preserve every later SCORE_CLASS control and all other functions. "+
            "The verified recovery checkpoint is: "+json.dumps(checkpoint["checkpoint"],separators=(",",":"))+"\n\n"+
            "Start by discovering functions and inspecting the current typed structure, target path, semantic fingerprint and child assignment anchors. "+
            "Use the typed block-replacement tool, preview, commit only an accepted candidate, then request MIR interpreter/JIT validation. Do not edit source text.")
        b=session(phase="B",tools=BLOCK,mode="block_replace",prompt=prompt_b,out=out/"mission-b",root_out=out,env=env,port=ready["port"],timeout=args.timeout)
        status=gateway_call("127.0.0.1",ready["port"],"get_status",{})
        host_b=gateway_call("127.0.0.1",ready["port"],"host_validate",{"expected_revision":status["revision"]}) if status["committed"] else {"mission_complete":False,"not_run":True}
        write(out/"mission-b-host-validation.json",host_b)
        history=[json.loads(line) for line in (out/"history.jsonl").read_text().splitlines() if line.strip()]
        mission_b_events=[row for row in history if row.get("mission_id")=="cycle29.replace-score-classification-block.v1"]
        denied=any(row.get("event")=="transaction_rejected" for row in mission_b_events)
        states_b=completion_states(committed=status["committed"],validation=host_b,timed_out=b["timed_out"],
            exit_code=b["exit_code"],agent_end_seen=bool(b["lifecycle"].get("observer",{}).get("agent_end_seen")),
            agent_settled_seen=bool(b["lifecycle"].get("observer",{}).get("agent_settled_seen")),
            pending_tool_count=len(b["lifecycle"].get("pending_tool_ids",[])),
            authorization_status="authorized" if status["committed"] else "denied" if denied else "not_attempted")
        write(out/"mission-b-completion-states.json",states_b)
        summary={"schema":"basic-workspace.cycle29-real-agent-campaign","version":1,"campaign_kind":"genuine_pi_two_session_semantic_extraction",
            "model":MODEL,"pi_version":"1.5.0","baseline_revision":11,"mission_a":a,"mission_a_commit_revision":12 if host_a.get("mission_complete") else None,
            "mission_a_host_validation":host_a,"checkpoint_verified":bool(boundary.get("checkpoint_verified")),"mission_b":b,
            "mission_b_commit_revision":status["revision"] if status["committed"] else None,"mission_b_host_validation":host_b,
            "mission_a_completion_states":states_a,"mission_b_completion_states":states_b,
            "semantic_correctness":bool(host_b.get("mission_complete")),"authorization_commit_host_validation_separate":True,
            "pi_settlement_separate_per_mission":True,"viewer_url":url,"automatic_retries":0}
        write(out/"summary.json",summary);write(out/"mission-outcome.json",summary)
        render=subprocess.run([sys.executable,str(ROOT/"scripts/basic-visual.py"),"replay",str(out)],capture_output=True,text=True)
        write(out/"offline-render.json",{"returncode":render.returncode,"stdout":render.stdout,"stderr":render.stderr})
        if render.returncode:raise RuntimeError("offline code-first replay generation failed")
        print(json.dumps({"mission_a_validated":host_a.get("mission_complete"),"mission_b_validated":host_b.get("mission_complete"),
            "revision":status["revision"],"pi_a_exit":a.get("exit_code"),"pi_b_exit":b.get("exit_code"),"output":str(out)},indent=2))
        return 0 if host_b.get("mission_complete") else 1
    finally:
        stop(viewer);stop(gateway);gateway_err.close()

if __name__=="__main__":raise SystemExit(main())
