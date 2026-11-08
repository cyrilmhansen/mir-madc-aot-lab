#!/usr/bin/env python3
"""Run one Pi JSON-event session against the loopback BASIC gateway and viewer."""
from __future__ import annotations
import argparse, json, os, pathlib, socket, subprocess, sys, time, urllib.request, webbrowser

HERE=pathlib.Path(__file__).resolve().parent
ROOT=HERE.parent
MODEL="Qwen3.8-Flash-Next-Sushi-STQ-2.75bpw"
TOOLS=["workspace_discover_functions","workspace_inspect_program","workspace_preview_function","workspace_commit_preview","workspace_validate_mission"]

def atomic_json(path:pathlib.Path,data):path.write_text(json.dumps(data,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def isolated_config(runtime:pathlib.Path,source_dir:pathlib.Path):
    models_path=source_dir/"models.json"
    if not models_path.is_file():raise RuntimeError("Pi provider models.json is unavailable in the configured local Pi directory")
    data=json.loads(models_path.read_text(encoding="utf-8")); provider=data.get("providers",{}).get("sushi")
    if not isinstance(provider,dict):raise RuntimeError("Local Pi configuration has no sushi provider")
    models=[m for m in provider.get("models",[]) if isinstance(m,dict) and m.get("id")==MODEL]
    if len(models)!=1:raise RuntimeError("Requested Sushi/Qwen model is missing or ambiguous in local Pi models.json")
    out_provider={k:provider[k] for k in ("baseUrl","api","headers","compat") if k in provider}
    out_provider["models"]=[models[0]]
    child_env={}
    key=provider.get("apiKey")
    if isinstance(key,str) and key:
        if key.startswith("$"):
            out_provider["apiKey"]=key
        else:
            child_env["BASIC_WS_PI_API_KEY_RUNTIME"]=key
            out_provider["apiKey"]="$BASIC_WS_PI_API_KEY_RUNTIME"
    config={"$schema":"https://pi.dev/schemas/models.schema.json","providers":{"sushi":out_provider}}
    runtime.mkdir(parents=True,exist_ok=True); target=runtime/"models.json"
    atomic_json(target,config); target.chmod(0o600)
    return target,child_env

def rpc_preflight(env,base_args,output):
    command=base_args+["--mode","rpc","--no-session"]
    stderr=(output/"pi-preflight.stderr.log").open("w",encoding="utf-8")
    proc=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=stderr,text=True,bufsize=1,env=env)
    responses={}; transcript=[]; start=time.monotonic()
    try:
        for request_id,kind in (("models","get_available_models"),("state","get_state")):
            proc.stdin.write(json.dumps({"id":request_id,"type":kind})+"\n");proc.stdin.flush()
            deadline=time.monotonic()+15
            while time.monotonic()<deadline:
                line=proc.stdout.readline()
                if not line:break
                try:row=json.loads(line)
                except json.JSONDecodeError:continue
                transcript.append(row)
                if row.get("type")=="response" and row.get("id")==request_id:
                    responses[request_id]=row;break
        if any(not row.get("success") for row in responses.values()) or len(responses)!=2:
            raise RuntimeError("Pi RPC preflight could not inspect model inventory and state")
    finally:
        try:proc.stdin.close()
        except Exception:pass
        if proc.poll() is None:proc.terminate()
        try:proc.wait(timeout=4)
        except subprocess.TimeoutExpired:proc.kill();proc.wait()
        stderr.close()
    model_rows=responses["models"].get("data",{}).get("models",[])
    model_match=any(m.get("provider")=="sushi" and m.get("id")==MODEL for m in model_rows if isinstance(m,dict))
    inventory_path=output/"tool-inventory.json"
    deadline=time.monotonic()+4
    while not inventory_path.exists() and time.monotonic()<deadline:time.sleep(.05)
    inventory=json.loads(inventory_path.read_text()) if inventory_path.exists() else {"tools":[]}
    (output/"pi-rpc-preflight.json").write_text(json.dumps({"mode":"rpc","model_available":model_match,
        "model_count":len(model_rows),"active_tools":inventory.get("tools"),"expected_tools":TOOLS,
        "tool_inventory_exact":inventory.get("tools")==TOOLS,"elapsed_ms":round((time.monotonic()-start)*1000,2),
        "model_endpoint_called":False},indent=2)+"\n")
    if not model_match:raise RuntimeError("Pi RPC did not list the configured Sushi/Qwen model")
    if inventory.get("tools")!=TOOLS:raise RuntimeError(f"Pi tool inventory does not match the semantic allowlist: {inventory.get('tools')}")

def gateway_call(host,port,method,params,timeout=120):
    with socket.create_connection((host,port),timeout=timeout) as sock:
        sock.settimeout(timeout); sock.sendall((json.dumps({"request_id":f"host-{time.time_ns()}","method":method,"params":params})+"\n").encode())
        data=b""
        while b"\n" not in data:
            chunk=sock.recv(65536)
            if not chunk:raise RuntimeError("gateway closed during request")
            data+=chunk
            if len(data)>1024*1024:raise RuntimeError("gateway response exceeds one MiB")
    row=json.loads(data.split(b"\n",1)[0])
    if not row.get("ok"):raise RuntimeError(f"gateway {row.get('error',{}).get('code')}: {row.get('error',{}).get('message')}")
    return row["result"]

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument("--output",type=pathlib.Path,default=HERE/"results/real-pi-01")
    ap.add_argument("--timeout",type=int,default=240);ap.add_argument("--open-browser",action="store_true")
    ap.add_argument("--preflight-only",action="store_true",help="start Python/viewer and verify Pi's configured model and active tools, without inference")
    args=ap.parse_args();out=args.output.resolve()
    if out.exists() and any(out.iterdir()):raise SystemExit(f"output directory already contains evidence: {out}")
    out.mkdir(parents=True,exist_ok=True)
    source=pathlib.Path(os.environ.get("PI_CODING_AGENT_DIR",pathlib.Path.home()/".sushi/pi")).expanduser()
    models_file,key_env=isolated_config(HERE/".runtime/pi-config",source)
    env=os.environ.copy();env.update(key_env)
    env["PI_CODING_AGENT_DIR"]=str(models_file.parent)
    env["PI_CODING_AGENT_SESSION_DIR"]=str(out/"pi-sessions")
    bridge_log=(out/"gateway-stderr.log").open("w",encoding="utf-8")
    bridge=subprocess.Popen([sys.executable,str(HERE/"gateway.py"),"--output",str(out),"--port","0"],
        stdout=subprocess.PIPE,stderr=bridge_log,text=True,env=env)
    viewer=None; pi_proc=None
    try:
        ready=json.loads(bridge.stdout.readline())
        if not ready.get("ready") or ready.get("host")!="127.0.0.1":raise RuntimeError("gateway startup failed")
        env["BASIC_WS_PI_GATEWAY"]=f"127.0.0.1:{ready['port']}"
        (out/"gateway-ready.json").write_text(json.dumps({"host":"127.0.0.1","port":ready["port"],"revision":ready["revision"]},indent=2)+"\n")
        viewer_err=(out/"viewer-stderr.log").open("w",encoding="utf-8")
        viewer=subprocess.Popen([sys.executable,str(ROOT/"scripts/basic-visual.py"),"live",str(out),"--port","0"],
            stdout=subprocess.PIPE,stderr=viewer_err,text=True,env=env)
        banner=viewer.stdout.readline().strip()
        if not banner.startswith("Read-only viewer: http://127.0.0.1:"):raise RuntimeError("live viewer did not start on loopback")
        url=banner.split(": ",1)[1];(out/"viewer-url.txt").write_text(url+"\n")
        print("Live semantic viewer is ready at",url,flush=True)
        base=["pi","--provider","sushi","--model",MODEL,"--thinking","low","--extension",str(HERE/"extension.ts"),
              "--no-extensions","--no-mcp","--no-skills","--no-context-files","--no-prompt-templates",
              "--no-builtin-tools","--no-tools","--tools",",".join(TOOLS)]
        rpc_preflight(env,base,out)
        print("Pi RPC preflight passed: exact model available; only the five semantic tools are active.",flush=True)
        if args.preflight_only:
            atomic_json(out/"preflight-summary.json",{"pi_version":"1.5.0","model":MODEL,"rpc_model_inventory":True,
                "active_tools":json.loads((out/"tool-inventory.json").read_text()).get("tools"),
                "inference_started":False,"provider_endpoint_tested":False,"seed_revision":ready["revision"]})
            return 0
        if args.open_browser:webbrowser.open(url)
        prompt=("Mission: Create IS_ADULT(ID), returning 1 when AGE_BY_ID(ID) is at least 18 and 0 otherwise, "
          "including unknown IDs. Preserve AGE_BY_ID, IS_SENIOR, arrays and existing data.\n\n"
          "Use only the semantic Workspace tools. First discover the callable function and inspect the live structure. "
          "Then propose a numeric function with one numeric ID parameter through the typed constructor, preview it, "
          "commit only an accepted preview, and validate the committed revision through MIR interpreter and JIT. "
          "The call must bind to the discovered AGE_BY_ID identity. Do not provide BASIC source text. "
          "Typed expressions use number, local_ref, call, binary, and unary objects; statements use typed result assignments and IF blocks. "
          "The gateway enforces the mission and revision. Stop and report any rejection instead of bypassing it.")
        (out/"mission-prompt.txt").write_text(prompt+"\n",encoding="utf-8")
        pi_command=base+["--mode","json","--session-dir",str(out/"pi-sessions"),"--name","Cycle 16 IS_ADULT semantic mission",
                        "--print","--",prompt]
        pi_err=(out/"pi-stderr.log").open("w",encoding="utf-8")
        pi_started=time.monotonic()
        with (out/"pi-session.jsonl").open("w",encoding="utf-8") as pi_out:
            try:pi_proc=subprocess.run(pi_command,stdout=pi_out,stderr=pi_err,env=env,timeout=args.timeout,check=False)
            except subprocess.TimeoutExpired:
                pi_proc=None;(out/"pi-timeout.json").write_text(json.dumps({"timeout_seconds":args.timeout,"timed_out":True},indent=2)+"\n")
        elapsed=(time.monotonic()-pi_started)*1000;pi_err.close()
        status=gateway_call("127.0.0.1",ready["port"],"get_status",{})
        validation=None
        if status["committed"]:
            validation=gateway_call("127.0.0.1",ready["port"],"validate_mission",{"expected_revision":status["revision"]})
        outcome=gateway_call("127.0.0.1",ready["port"],"finalize_mission",{
            "timed_out":pi_proc is None,"pi_exit_code":None if pi_proc is None else pi_proc.returncode,
            "validation":validation})
        try:subprocess.run([sys.executable,str(ROOT/"scripts/basic-visual.py"),"replay",str(out)],check=True,capture_output=True,text=True)
        except Exception as exc:(out/"replay-error.txt").write_text(str(exc)+"\n")
        raw=[]
        for line in (out/"pi-session.jsonl").read_text(encoding="utf-8").splitlines():
            try:raw.append(json.loads(line))
            except json.JSONDecodeError:continue
        tool_events=[e for e in raw if e.get("type")=="tool_execution_start"]
        turns=[e for e in raw if e.get("type")=="turn_end"]
        usages=[]
        for e in raw:
            msg=e.get("message") or e.get("assistantMessageEvent",{}).get("message")
            use=(msg or {}).get("usage") if isinstance(msg,dict) else None
            if isinstance(use,dict):usages.append(use)
        totals={}
        for key in ("input","output","cacheRead","cacheWrite","totalTokens"):
            vals=[u.get(key) for u in usages if isinstance(u.get(key),(int,float))]
            totals[key]=sum(vals) if vals else None
        schemas=out/"tool-schemas.json"
        summary={"schema":"basic-workspace.pi-cycle16-summary","version":1,"campaign_kind":"genuine_pi_model",
            "provider":"sushi","model":MODEL,"pi_version":"1.5.0","workspace_revision":status["revision"],
            "committed":status["committed"],"pi_exit_code":None if pi_proc is None else pi_proc.returncode,
            "timed_out":pi_proc is None,"turn_end_events":len(turns),"tool_calls":len(tool_events),
            "tool_calls_by_name":{n:sum(e.get("toolName")==n for e in tool_events) for n in TOOLS},
            "provider_usage_from_pi_events":totals,"inference_and_process_wall_ms":round(elapsed,2),
            "mission_status":outcome.get("mission_status"),
            "active_tools":json.loads((out/"tool-inventory.json").read_text()).get("tools",[]) if (out/"tool-inventory.json").exists() else [],
            "tool_schema_bytes":schemas.stat().st_size if schemas.exists() else None,
            "pi_event_stream_bytes":(out/"pi-session.jsonl").stat().st_size,
            "validation":validation,"viewer_url":url,"provider_preflight":"RPC model/tool inventory verified; actual endpoint/tool compatibility is the genuine mission request"}
        atomic_json(out/"summary.json",summary)
        print(json.dumps({"summary":str(out/"summary.json"),"viewer":url,"committed":status["committed"],
            "revision":status["revision"],"turns":len(turns),"tool_calls":len(tool_events),"mission_status":outcome.get("mission_status"),
            "validation_passed":bool(validation and validation.get("mission_complete"))},indent=2))
        if pi_proc is None:return 2
        return 0 if validation and validation.get("mission_complete") else (0 if not status["committed"] else 1)
    finally:
        for proc in (pi_proc,viewer):
            if proc is not None and isinstance(proc,subprocess.Popen) and proc.poll() is None:proc.terminate()
        if viewer is not None and isinstance(viewer,subprocess.Popen):
            try:viewer.wait(timeout=3)
            except subprocess.TimeoutExpired:viewer.kill();viewer.wait()
        if bridge.poll() is None:bridge.terminate()
        try:bridge.wait(timeout=4)
        except subprocess.TimeoutExpired:bridge.kill();bridge.wait()
        bridge_log.close()

if __name__=="__main__":raise SystemExit(main())
