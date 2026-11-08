#!/usr/bin/env python3
"""Run one Pi JSON-event session against the loopback BASIC gateway and viewer."""
from __future__ import annotations
import argparse, hashlib, json, os, pathlib, socket, subprocess, sys, time, urllib.request, webbrowser

HERE=pathlib.Path(__file__).resolve().parent
ROOT=HERE.parent
MODEL="Qwen3.8-Flash-Next-Sushi-STQ-2.75bpw"
ATOMIC_TOOLS=["workspace_discover_functions","workspace_inspect_program","workspace_preview_function","workspace_commit_preview","workspace_validate_mission"]
DRAFT_TOOLS=["workspace_discover_functions","workspace_inspect_program","workspace_commit_preview","workspace_validate_mission",
    "workspace_begin_function_draft","workspace_apply_draft_operations","workspace_inspect_function_draft","workspace_preview_function_draft"]

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

def rpc_preflight(env,base_args,output,tools):
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
        "model_count":len(model_rows),"active_tools":inventory.get("tools"),"expected_tools":tools,
        "tool_inventory_exact":inventory.get("tools")==tools,"elapsed_ms":round((time.monotonic()-start)*1000,2),
        "model_endpoint_called":False},indent=2)+"\n")
    if not model_match:raise RuntimeError("Pi RPC did not list the configured Sushi/Qwen model")
    if inventory.get("tools")!=tools:raise RuntimeError(f"Pi tool inventory does not match the semantic allowlist: {inventory.get('tools')}")

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
    ap.add_argument("--arm",choices=("atomic","incremental"),default="atomic")
    ap.add_argument("--mission-kind",choices=("adult","category"),default="adult")
    ap.add_argument("--registered-plan",type=pathlib.Path)
    ap.add_argument("--timeout",type=int,default=240);ap.add_argument("--open-browser",action="store_true")
    ap.add_argument("--preflight-only",action="store_true",help="start Python/viewer and verify Pi's configured model and active tools, without inference")
    args=ap.parse_args();out=args.output.resolve()
    if out.exists() and any(out.iterdir()):raise SystemExit(f"output directory already contains evidence: {out}")
    out.mkdir(parents=True,exist_ok=True)
    tools=ATOMIC_TOOLS if args.arm=="atomic" else DRAFT_TOOLS
    plan=None
    if args.registered_plan:
        plan=json.loads(args.registered_plan.read_text(encoding="utf-8"))
        if plan.get("model")!=MODEL or args.arm not in plan.get("arm_specific_instructions",{}) or plan.get("mission_kind",args.mission_kind)!=args.mission_kind:
            raise SystemExit("registered plan model/arm/mission does not match this run")
        if args.timeout>plan.get("max_wall_seconds_per_arm",0):
            raise SystemExit("run timeout exceeds the pre-registered arm limit")
        atomic_json(out/"pre-registration.json",plan)
    source=pathlib.Path(os.environ.get("PI_CODING_AGENT_DIR",pathlib.Path.home()/".sushi/pi")).expanduser()
    models_file,key_env=isolated_config(HERE/".runtime/pi-config",source)
    env=os.environ.copy();env.update(key_env)
    env["PI_CODING_AGENT_DIR"]=str(models_file.parent)
    env["PI_CODING_AGENT_SESSION_DIR"]=str(out/"pi-sessions")
    bridge_log=(out/"gateway-stderr.log").open("w",encoding="utf-8")
    bridge=subprocess.Popen([sys.executable,str(HERE/"gateway.py"),"--output",str(out),"--port","0","--authoring-mode",args.arm,
        "--mission-kind",args.mission_kind],
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
        env["BASIC_WS_AUTHORING_MODE"]=args.arm
        base=["pi","--provider","sushi","--model",MODEL,"--thinking","low","--extension",str(HERE/"extension.ts"),
              "--no-extensions","--no-mcp","--no-skills","--no-context-files","--no-prompt-templates",
              "--no-builtin-tools","--no-tools","--tools",",".join(tools)]
        rpc_preflight(env,base,out,tools)
        print(f"Pi RPC preflight passed: exact model available; only the {len(tools)} {args.arm} semantic tools are active.",flush=True)
        if args.preflight_only:
            atomic_json(out/"preflight-summary.json",{"pi_version":"1.5.0","model":MODEL,"rpc_model_inventory":True,
                "active_tools":json.loads((out/"tool-inventory.json").read_text()).get("tools"),
                "inference_started":False,"provider_endpoint_tested":False,"seed_revision":ready["revision"]})
            return 0
        if args.open_browser:webbrowser.open(url)
        if plan:
            prompt=plan["common_task"]+"\n\n"+plan["common_instructions"]+" "+plan["arm_specific_instructions"][args.arm]
        else:
            prompt=("Mission: Create IS_ADULT(ID), returning 1 when AGE_BY_ID(ID) is at least 18 and 0 otherwise, "
              "including unknown IDs. Preserve AGE_BY_ID, IS_SENIOR, arrays and existing data.\n\n"
              "Use only the semantic Workspace tools. First discover the callable function and inspect the live structure. "
              "The new function must call the discovered AGE_BY_ID identity. Do not provide BASIC source text. "
              + ("Build the complete typed function with the whole-function constructor, preview it, commit only an accepted preview, and validate through MIR interpreter and JIT. "
                 if args.arm=="atomic" else
                 "Begin a revision-bound temporary function draft. Create typed numeric expressions with draft-local handles, append result assignments, and assemble an IF with branch blocks using ordered draft operations. Inspect the draft, preview the whole candidate through the MissionGateway, commit only an accepted preview, and validate through MIR interpreter and JIT. Draft operations are temporary; they do not commit BASIC individually. ")
              + "The gateway enforces mission scope and revisions. Stop and report any rejection instead of bypassing it.")
        (out/"mission-prompt.txt").write_text(prompt+"\n",encoding="utf-8")
        pi_command=base+["--mode","json","--session-dir",str(out/"pi-sessions"),"--name",
                        f"Cycle 18 AGE_CATEGORY {args.arm} authoring" if args.mission_kind=="category" else f"Cycle 17 IS_ADULT {args.arm} authoring",
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
        preview_names={"workspace_preview_function","workspace_preview_function_draft"}
        preview_ends=[e for e in raw if e.get("type")=="tool_execution_end" and e.get("toolName") in preview_names]
        preview_results=[]
        for event in preview_ends:
            result=event.get("result") or {}
            texts=[part.get("text") for part in result.get("content",[]) if isinstance(part,dict) and isinstance(part.get("text"),str)]
            parsed=None
            for text_value in texts:
                try:
                    parsed=json.loads(text_value); break
                except json.JSONDecodeError: pass
            preview_results.append(parsed or {})
        acceptance=bool(validation and validation.get("mission_complete") and validation.get("engines_agree") and
            (validation.get("boundary_oracle") or {}).get("passed") and (validation.get("replay") or {}).get("passed"))
        schemas=out/"tool-schemas.json"
        schema_bytes=schemas.stat().st_size if schemas.exists() else None
        draft_record=json.loads((out/"draft-operation-history.json").read_text()) if (out/"draft-operation-history.json").exists() else None
        trace_rows=[json.loads(line) for line in (out/"history.jsonl").read_text().splitlines() if line.strip()]
        draft_rows=[json.loads(line) for line in (out/"draft-operations.jsonl").read_text().splitlines() if line.strip()] if (out/"draft-operations.jsonl").exists() else []
        gateway_rows=[json.loads(line) for line in (out/"gateway-tool-timings.jsonl").read_text().splitlines() if line.strip()] if (out/"gateway-tool-timings.jsonl").exists() else []
        draft_tool_starts=[e for e in tool_events if e.get("toolName")=="workspace_apply_draft_operations"]
        batch_sizes=[len((e.get("args") or {}).get("operations",[])) for e in draft_tool_starts]
        draft_inspection_starts=[e for e in tool_events if e.get("toolName")=="workspace_inspect_function_draft"]
        draft_inspection_ends=[e for e in raw if e.get("type")=="tool_execution_end" and e.get("toolName")=="workspace_inspect_function_draft"]
        final_draft_revision=draft_record.get("final_draft_revision") if draft_record else None
        incomplete_inspections=0
        for event in draft_inspection_ends:
            result=event.get("result") or {}
            texts=[part.get("text") for part in result.get("content",[]) if isinstance(part,dict) and isinstance(part.get("text"),str)]
            for text_value in texts:
                try:
                    inspected=json.loads(text_value)
                    revision=inspected.get("draft_revision")
                    if isinstance(revision,int) and isinstance(final_draft_revision,int) and revision<final_draft_revision:
                        incomplete_inspections+=1
                    break
                except (json.JSONDecodeError,AttributeError): pass
        reused_handles=[]
        if draft_record:
            known=set()
            for operation in draft_record.get("operations",[]):
                fields={"define_function_call":["arguments"],"define_unary_expression":["operand"],
                    "define_binary_expression":["left","right"],"append_result_assignment":["expression"],
                    "append_if_block":["condition"]}.get(operation.get("kind"),[])
                for field_name in fields:
                    value=operation.get(field_name); values=value if isinstance(value,list) else [value]
                    reused_handles.extend(value for value in values if isinstance(value,str) and value in known)
                if operation.get("kind","").startswith("define_") and isinstance(operation.get("handle"),str):
                    known.add(operation["handle"])
        agent_gateway_rows=[row for row in gateway_rows if row.get("agent_tool")]
        gateway_total_ms=round(sum(row.get("elapsed_ms",0) for row in agent_gateway_rows),3)
        gateway_by_method={}
        for row in agent_gateway_rows:
            item=gateway_by_method.setdefault(row.get("method"),{"calls":0,"elapsed_ms":0.0})
            item["calls"]+=1; item["elapsed_ms"]+=row.get("elapsed_ms",0)
        for item in gateway_by_method.values():item["elapsed_ms"]=round(item["elapsed_ms"],3)
        invalid_tool_calls=sum(bool(e.get("isError")) for e in raw if e.get("type")=="tool_execution_end")
        policy_rejections=sum(row.get("event")=="transaction_rejected" for row in trace_rows)
        rejected_draft_batches=sum(row.get("event")=="operation_batch_rejected" for row in
            (json.loads(line) for line in (out/"draft-operations.jsonl").read_text().splitlines() if line.strip())) if (out/"draft-operations.jsonl").exists() else 0
        summary={"schema":"basic-workspace.pi-cycle16-summary","version":1,"campaign_kind":"genuine_pi_model",
            "provider":"sushi","model":MODEL,"pi_version":"1.5.0","authoring_arm":args.arm,"workspace_revision":status["revision"],
            "committed":status["committed"],"pi_exit_code":None if pi_proc is None else pi_proc.returncode,
            "timed_out":pi_proc is None,"turn_end_events":len(turns),"tool_calls":len(tool_events),
            "tool_calls_by_name":{n:sum(e.get("toolName")==n for e in tool_events) for n in tools},
            "semantic_operation_count":len(draft_record["operations"]) if draft_record else (1 if status["committed"] else 0),
            "draft_revision":draft_record.get("final_draft_revision") if draft_record else None,
            "draft_operation_tool_calls":len(draft_tool_starts),"operations_per_batch":batch_sizes,
            "draft_inspections":len(draft_inspection_starts),"incomplete_draft_inspections":incomplete_inspections,
            "reused_expression_handle_references":reused_handles,
            "invalid_tool_calls":invalid_tool_calls,"policy_rejections":policy_rejections,
            "invalid_draft_batches":rejected_draft_batches,
            # Count only preview tool invocations in this genuine Pi session.
            # Seed construction and deterministic controls are not agent previews.
            "preview_attempts":len(preview_ends),
            "accepted_previews":sum(bool(result.get("ok")) and bool(result.get("transaction_id")) for result in preview_results),
            "rejected_previews":sum(not bool(result.get("ok")) for result in preview_results),
            "provider_usage_from_pi_events":totals,"inference_and_process_wall_ms":round(elapsed,2),
            "gateway_tool_processing_ms":gateway_total_ms,"gateway_tool_processing_by_method":gateway_by_method,
            "mission_status":outcome.get("mission_status"),
            "active_tools":json.loads((out/"tool-inventory.json").read_text()).get("tools",[]) if (out/"tool-inventory.json").exists() else [],
            "tool_schema_bytes":schema_bytes,"tool_schema_tokens_estimate_bytes_div_4":round(schema_bytes/4) if schema_bytes is not None else None,
            "registered_plan_sha256":hashlib.sha256(args.registered_plan.read_bytes()).hexdigest() if args.registered_plan else None,
            "session_timeout_seconds":args.timeout,
            "pi_event_stream_bytes":(out/"pi-session.jsonl").stat().st_size,
            "serialized_request_context_bytes":None,
            "serialized_request_context_bytes_note":"Pi JSON event mode does not expose complete HTTP request bodies; provider-reported token usage and Pi event-stream bytes are reported separately.",
            "tool_schema_bytes_are_model_visible_schema_capture":True,
            "agent_operation_history_bytes":(out/"draft-operations.jsonl").stat().st_size if (out/"draft-operations.jsonl").exists() else 0,
            "visual_presentation_frames":sum(1 for line in (out/"visual-events.jsonl").read_text().splitlines() if line.strip()) if (out/"visual-events.jsonl").exists() else 0,
            "validation":validation,"viewer_url":url,"provider_preflight":"RPC model/tool inventory verified; actual endpoint/tool compatibility is the genuine mission request"}
        atomic_json(out/"summary.json",summary)
        print(json.dumps({"summary":str(out/"summary.json"),"viewer":url,"committed":status["committed"],
            "revision":status["revision"],"turns":len(turns),"tool_calls":len(tool_events),"mission_status":outcome.get("mission_status"),
            "validation_passed":acceptance},indent=2))
        if pi_proc is None:return 2
        return 0 if acceptance else (0 if not status["committed"] else 1)
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
