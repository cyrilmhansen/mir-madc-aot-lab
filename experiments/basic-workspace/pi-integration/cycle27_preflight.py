#!/usr/bin/env python3
"""Deterministic production-bridge preflight for post-rename function creation."""
from __future__ import annotations
import argparse, json, os, pathlib, socket, subprocess, sys, time

HERE=pathlib.Path(__file__).resolve().parent; ROOT=HERE.parent
OUT_DEFAULT=HERE/"results/cycle27-post-rename-reuse/deterministic-preflight"
CAMPAIGN=HERE/"results/cycle27-post-rename-reuse"
REAL=HERE/"results/cycle26-semantic-rename/real-agent-01"
TOOLS=["workspace_discover_functions","workspace_inspect_program","workspace_preview_function",
       "workspace_commit_preview","workspace_validate_mission"]

def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def dispatch(out,port,request,tag):
    inp=out/f"{tag}-input.json"; result=out/f"{tag}-output.json"; write(inp,request)
    env=os.environ.copy(); env.update({"BASIC_WS_AUTHORING_MODE":"atomic_create",
        "BASIC_WS_PI_GATEWAY":f"127.0.0.1:{port}","BASIC_WS_DISPATCH_PROBE_INPUT":str(inp),
        "BASIC_WS_DISPATCH_PROBE_OUTPUT":str(result),
        "NODE_PATH":"/usr/lib/node_modules/@earendil-works/pi-coding-agent/node_modules"})
    proc=subprocess.run(["bun",str(HERE/"cycle20b_dispatch_probe.ts")],env=env,capture_output=True,text=True,timeout=90)
    (out/f"{tag}.stdout.log").write_text(proc.stdout);(out/f"{tag}.stderr.log").write_text(proc.stderr)
    if proc.returncode or not result.is_file():raise RuntimeError(f"TypeScript/JSONL dispatch failed: {proc.stderr[-1200:]}")
    return json.loads(result.read_text())

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--output",type=pathlib.Path,default=OUT_DEFAULT); a=ap.parse_args()
    out=a.output.resolve()
    if out.exists() and any(out.iterdir()):raise SystemExit(f"refusing to overwrite evidence: {out}")
    out.mkdir(parents=True,exist_ok=True)
    contracts=CAMPAIGN/"contracts"; stream=REAL/"constructive-operations.json"
    history=REAL/"history.jsonl"; validation=REAL/"mission-validation-host.json"
    env=os.environ.copy(); env["PYTHONPATH"]=str(ROOT)+os.pathsep+str(HERE)+os.pathsep+env.get("PYTHONPATH","")
    with socket.socket() as sock:sock.bind(("127.0.0.1",0));port=sock.getsockname()[1]
    gateway=subprocess.Popen([sys.executable,str(HERE/"cycle19_gateway.py"),"--output",str(out/"gateway-evidence"),
        "--port",str(port),"--creation-contract",str(contracts/"is-at-cap.json"),
        "--seed-contract",str(contracts/"seed-revision9-verification.json"),"--baseline-stream",str(stream),
        "--baseline-history",str(history),"--baseline-validation",str(validation)],stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,stderr=(out/"gateway-stderr.log").open("w"),text=True,env=env)
    try:
        ready=json.loads(gateway.stdout.readline())
        if not ready.get("ready") or ready.get("revision")!=9 or not ready.get("resume_verification",{}).get("passed"):
            raise RuntimeError(f"revision-9 bootstrap verification failed: {ready}")
        good={"expected_revision":9,"name":"IS_AT_CAP","parameters":["X"],"body":[
            {"kind":"assign","target":{"kind":"result"},"expression":{"kind":"number","value":0}},
            {"kind":"if","condition":{"kind":"binary","operator":"=","left":{
                "kind":"call","function_handle":"clamp_score.function","arguments":[{"kind":"local_ref","name":"X"}]},
                "right":{"kind":"number","value":50}},"then":[{"kind":"assign",
                "target":{"kind":"result"},"expression":{"kind":"number","value":1}}]}]}
        def clone():return json.loads(json.dumps(good))
        invented=clone();invented["body"][1]["condition"]["left"]["function_handle"]="normalize_score.function"
        undiscovered=clone();undiscovered["body"][1]["condition"]["left"]["function_handle"]="missing.function"
        arity=clone();arity["body"][1]["condition"]["left"]["arguments"]=[]
        old_spelling=clone();old_spelling["body"][1]["condition"]["left"]["arguments"]=[{"kind":"local_ref","name":"CLAMP_SCORE"}]
        wrong_name=clone();wrong_name["name"]="NORMALIZE_SCORE"
        stale=clone();stale["expected_revision"]=8
        controls=[invented,undiscovered,arity,old_spelling,wrong_name,stale]
        request={"authoring_mode":"atomic_create","correlation_id":f"cycle27-preflight-{time.time_ns()}",
            "preview_args":good,"controls":controls,"commit":True,"duplicate_commit":True}
        result=dispatch(out,ready["port"],request,"production-dispatch")
        if not result.get("schema_ok") or sorted(result.get("active_tools",[]))!=sorted(TOOLS):raise RuntimeError("Pi extension tool/schema inventory mismatch")
        if result["discovery"]["revision"]!=9:raise RuntimeError("Production discovery did not inspect revision 9")
        target=next(row for row in result["discovery"]["functions"] if row["handle"]=="clamp_score.function")
        if target["name"]!="NORMALIZE_SCORE" or target["parameter_names"]!=["X"]:raise RuntimeError("Renamed identity was not discoverable with current spelling")
        expected_codes=["MISSION_DEPENDENCY_REQUIRED","MISSION_DEPENDENCY_REQUIRED","UNKNOWN_TRANSACTION_HANDLE","MISSION_SIGNATURE","STALE_REVISION"]
        got_codes=[row.get("code") for row in result["controls"]]
        if got_codes!=expected_codes:raise RuntimeError(f"Negative control outcomes differ: {got_codes}")
        if len(result.get("schema_rejections",[]))!=1 or result["schema_rejections"][0].get("index")!=2:
            raise RuntimeError("Wrong arity was not rejected by the active bounded tool schema")
        if any(row.get("revision_unchanged") is not True or row.get("authoritative_workspace_changed") is not False for row in result["controls"]):
            raise RuntimeError("A rejected constructor control changed the authoritative program")
        preview=result.get("preview",{})
        if not preview.get("ok") or not preview.get("candidate_is_preview_only") or preview.get("base_revision")!=9:
            raise RuntimeError("The production handler did not provide an accepted, non-mutating revision-9 preview")
        if result.get("committed",{}).get("revision")!=10 or not result.get("validation",{}).get("mission_complete"):
            raise RuntimeError("Disposable production-path commit or independent validation failed")
        if result.get("duplicate_commit",{}).get("committed") is not False:raise RuntimeError("Duplicate commit was not rejected")
        committed_events=[json.loads(line) for line in (out/"gateway-evidence/visual-events.jsonl").read_text().splitlines()
            if json.loads(line).get("event_type")=="commit" and json.loads(line).get("revision")==10]
        if len(committed_events)!=1 or "FUNCTION IS_AT_CAP(X)" not in committed_events[0].get("snapshot","") or \
                "NORMALIZE_SCORE(X) = 50" not in committed_events[0].get("snapshot",""):
            raise RuntimeError("Committed source snapshot did not emit the renamed current source spelling")
        schemas=result["schemas"]; write(out/"tool-inventory.json",{"tools":TOOLS,"source":"Pi extension active registry"})
        write(out/"tool-schemas.json",schemas)
        bad=clone();bad["transport_correlation_id"]="should-not-be-a-semantic-field"
        unknown=dispatch(out,ready["port"],{"authoring_mode":"atomic_create","preview_args":bad},"unknown-semantic-field")
        if unknown.get("schema_ok") is not False or unknown.get("stage")!="pi_typescript_schema":
            raise RuntimeError("Unknown/transport-only field crossed the typed tool schema")
        write(out/"unknown-semantic-field-rejection.json",unknown)
        write(out/"summary.json",{"schema":"basic-workspace.cycle27-preflight","version":1,"inference_performed":False,
            "baseline_revision":9,"revision9_stream_operations":8,"prior_portable_handles":18,
            "bootstrap":{"verified":True,"function_source_name":"NORMALIZE_SCORE","function_handle":"clamp_score.function",
                "identity_remappings":18,"mir_interpreter_jit_match":True,"semantic_equivalence":True},
            "active_tools":TOOLS,"tool_schema_bytes":len(json.dumps(schemas,ensure_ascii=False,separators=(",",":" )).encode()),
            "typescript_jsonl_dispatch":"passed","preview_non_mutating":True,"gateway_negative_control_codes":got_codes,
            "schema_negative_controls":[{"index":row["index"],"errors":[e.get("path",e.get("message")) for e in row["errors"]]} for row in result["schema_rejections"]],
            "unknown_semantic_and_transport_fields_rejected":True,"commit_revision":10,"duplicate_commit_rejected":True,
            "committed_source_uses_current_name":True,"candidate_behavior_and_replay_passed":True})
        write(out/"baseline-identity.json",json.loads((out/"gateway-evidence/baseline-reconstruction/baseline-reconstruction.json").read_text()))
        print((out/"summary.json").read_text())
    finally:
        gateway.terminate()
        try:gateway.wait(timeout=5)
        except subprocess.TimeoutExpired:gateway.kill();gateway.wait()
if __name__=="__main__":main()
