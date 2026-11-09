#!/usr/bin/env python3
"""Cycle 29 deterministic end-to-end TypeScript handler / JSONL bridge preflight."""
from __future__ import annotations
import argparse,json,os,pathlib,socket,subprocess,sys,time
HERE=pathlib.Path(__file__).resolve().parent;ROOT=HERE.parent
DEFAULT=HERE/"results/cycle29-function-extraction/deterministic-preflight/production-bridge"
TOOLS={"atomic_create":["workspace_discover_functions","workspace_inspect_program","workspace_commit_preview","workspace_validate_mission","workspace_preview_function"],
       "block_replace":["workspace_discover_functions","workspace_inspect_program","workspace_commit_preview","workspace_validate_mission","workspace_preview_block_replacement"]}

def write(path,value):
    path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def gateway(host,port,method,params,timeout=180):
    with socket.create_connection((host,port),timeout=timeout) as sock:
        sock.settimeout(timeout);sock.sendall((json.dumps({"request_id":f"host-{time.time_ns()}","method":method,"params":params})+"\n").encode())
        data=b""
        while b"\n" not in data:
            chunk=sock.recv(65536)
            if not chunk:raise RuntimeError("gateway closed before response")
            data+=chunk
            if len(data)>1024*1024:raise RuntimeError("gateway response exceeded bound")
    row=json.loads(data.split(b"\n",1)[0])
    if not row.get("ok"):raise RuntimeError(f"gateway {row.get('error',{}).get('code')}: {row.get('error',{}).get('message')}")
    return row["result"]

def dispatch(out,port,mode,request,tag):
    ip=out/f"{tag}-input.json";op=out/f"{tag}-output.json";write(ip,request)
    env=os.environ.copy();env.update({"BASIC_WS_AUTHORING_MODE":mode,"BASIC_WS_PI_GATEWAY":f"127.0.0.1:{port}",
        "BASIC_WS_DISPATCH_PROBE_INPUT":str(ip),"BASIC_WS_DISPATCH_PROBE_OUTPUT":str(op),
        "NODE_PATH":"/usr/lib/node_modules/@earendil-works/pi-coding-agent/node_modules"})
    proc=subprocess.run(["bun",str(HERE/"cycle20b_dispatch_probe.ts")],env=env,capture_output=True,text=True,timeout=180)
    (out/f"{tag}.stdout.log").write_text(proc.stdout);(out/f"{tag}.stderr.log").write_text(proc.stderr)
    if proc.returncode or not op.is_file():raise RuntimeError(f"production extension dispatch failed: {proc.stderr[-1600:]}")
    return json.loads(op.read_text())

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--output",type=pathlib.Path,default=DEFAULT);a=ap.parse_args();out=a.output.resolve()
    if out.exists() and any(out.iterdir()):raise SystemExit(f"refusing to overwrite {out}")
    out.mkdir(parents=True,exist_ok=True);env=os.environ.copy();env["PYTHONPATH"]=str(ROOT)+os.pathsep+str(HERE)+os.pathsep+env.get("PYTHONPATH","")
    with socket.socket() as sock:sock.bind(("127.0.0.1",0));port=sock.getsockname()[1]
    err=(out/"gateway-stderr.log").open("w")
    gw=subprocess.Popen([sys.executable,str(HERE/"cycle29_gateway.py"),"--output",str(out/"gateway-evidence"),"--port",str(port)],
        stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=err,text=True,env=env)
    try:
        ready=json.loads(gw.stdout.readline())
        if not ready.get("ready") or ready.get("revision")!=11 or ready.get("identity_count")!=23:raise RuntimeError(f"Cycle 28 baseline reconstruction failed: {ready}")
        # Mission A: known-good typed helper and independent denied variants.
        call={"kind":"call","function_handle":"clamp_score.function","arguments":[{"kind":"local_ref","name":"X"}]}
        helper={"expected_revision":11,"callee_handle":"clamp_score.function","name":"BASE_SCORE_CLASS","parameters":["X"],
            "body":[{"kind":"if","condition":{"kind":"binary","operator":"<","left":call,"right":{"kind":"number","value":20}},
                "then":[{"kind":"assign","target":{"kind":"result"},"expression":{"kind":"number","value":0}}],
                "else":[{"kind":"assign","target":{"kind":"result"},"expression":{"kind":"number","value":1}}]}]}
        wrong_handle=json.loads(json.dumps(helper));wrong_handle["body"][0]["condition"]["left"]["function_handle"]="invented.function"
        wrong_arity=json.loads(json.dumps(helper));wrong_arity["body"][0]["condition"]["left"]["arguments"]=[]
        wrong_signature=json.loads(json.dumps(helper));wrong_signature["name"]="UNRELATED_FUNCTION"
        ares=dispatch(out,ready["port"],"atomic_create",{"authoring_mode":"atomic_create","correlation_id":"cycle29-preflight-a",
            "preview_args":helper,"controls":[wrong_handle,wrong_arity,wrong_signature],"commit":True,"duplicate_commit":True},"mission-a")
        if ares.get("schema_ok") is not True or ares["active_tools"]!=TOOLS["atomic_create"]:raise RuntimeError("Mission A TypeScript tool inventory/schema mismatch")
        if ares["preview"].get("candidate_is_preview_only") is not True or ares["preview"].get("base_revision")!=11:raise RuntimeError("Mission A preview was not non-mutating")
        if ares["committed"].get("revision")!=12 or not ares["validation"].get("mission_complete"):raise RuntimeError("Mission A commit or independent host validation failed")
        if ares["duplicate_commit"].get("committed") is not False:raise RuntimeError("Mission A duplicate commit was not denied")
        if any(x.get("ok") is not False or x.get("revision_unchanged") is not True for x in ares["controls"]):raise RuntimeError("Mission A negative control mutated or was authorized")
        # The contract's function name is a schema-level constant; its
        # rejection must be accounted for before reaching the Python gateway.
        if len(ares["controls"])+len(ares.get("schema_rejections",[])) != 3:raise RuntimeError("Mission A negative controls were not all accounted for")
        write(out/"schema-captures/mission-a-tool-schemas.json",ares["schemas"])
        # The host creates and verifies the compact recovery checkpoint. It is
        # not model activity and it does not alter Workspace state.
        cp=gateway("127.0.0.1",ready["port"],"create_mission_b_checkpoint",{})
        if not cp.get("ok"):raise RuntimeError(f"Mission A checkpoint failed: {cp}")
        boundary=gateway("127.0.0.1",ready["port"],"prepare_mission_b",{"checkpoint":cp["checkpoint"]})
        if not boundary.get("checkpoint_verified") or boundary.get("revision")!=12:raise RuntimeError(f"Mission B checkpoint boundary failed: {boundary}")
        gateway("127.0.0.1",ready["port"],"discover_functions",{})
        inspection=gateway("127.0.0.1",ready["port"],"inspect_program",{})
        target=inspection["extraction_target"]
        base_call={"kind":"call","function_handle":"base_score_class.function","arguments":[{"kind":"local_ref","name":"X"}]}
        replacement=[{"kind":"assign","target":{"kind":"result"},"expression":base_call}]
        block={"expected_revision":12,"function_handle":"score_class.function","control_path":target["control_path"],
            "anchor_statement_handle":target["anchor_statement_handles"][0],"expected_block_fingerprint":target["expected_block_fingerprint"],
            "expected_removed_statement_handles":target["expected_removed_statement_handles"],"replacement_statements":replacement}
        wrong_path=json.loads(json.dumps(block));wrong_path["control_path"]=[{"block":"body","index":1}]
        wrong_fp=json.loads(json.dumps(block));wrong_fp["expected_block_fingerprint"]="0"*64
        unknown_handle=json.loads(json.dumps(block));unknown_handle["replacement_statements"][0]["expression"]["function_handle"]="missing.function"
        wrong_arity=json.loads(json.dumps(block));wrong_arity["replacement_statements"][0]["expression"]["arguments"]=[]
        unauthorized=json.loads(json.dumps(block));unauthorized["replacement_statements"][0]["expression"]["function_handle"]="is_passing.function"
        stale=json.loads(json.dumps(block));stale["expected_revision"]=11
        wrong_retirement=json.loads(json.dumps(block));wrong_retirement["expected_removed_statement_handles"]=["score_class.statement.2"]
        bres=dispatch(out,ready["port"],"block_replace",{"authoring_mode":"block_replace","correlation_id":"cycle29-preflight-b",
            "preview_args":block,"controls":[wrong_path,wrong_fp,unknown_handle,wrong_arity,unauthorized,stale,wrong_retirement],
            "commit":True,"duplicate_commit":True},"mission-b")
        if bres.get("schema_ok") is not True or bres["active_tools"]!=TOOLS["block_replace"]:raise RuntimeError("Mission B TypeScript tool inventory/schema mismatch")
        if bres["preview"].get("base_revision")!=12 or bres["preview"].get("candidate_is_preview_only") is not True:raise RuntimeError("Mission B preview changed committed state")
        if bres["committed"].get("revision")!=13 or not bres["validation"].get("mission_complete"):raise RuntimeError("Mission B commit or independent host validation failed")
        if bres["duplicate_commit"].get("committed") is not False:raise RuntimeError("Mission B duplicate commit was not denied")
        if any(x.get("ok") is not False or x.get("revision_unchanged") is not True for x in bres["controls"]):raise RuntimeError("Mission B negative proposal mutated or was authorized")
        if len(bres["controls"])+len(bres.get("schema_rejections",[])) != 7:raise RuntimeError("Mission B negative controls were not all accounted for")
        write(out/"schema-captures/mission-b-tool-schemas.json",bres["schemas"])
        # A TypeBox-only unknown field fixture proves semantic operation fields
        # remain strict at the model-visible tool boundary.
        extra=json.loads(json.dumps(block));extra["source_text"]="FUNCTION SCORE_CLASS(X)"
        schema_probe=dispatch(out,ready["port"],"block_replace",{"authoring_mode":"block_replace","correlation_id":"cycle29-schema-negative","preview_args":extra},"unknown-field")
        if schema_probe.get("schema_ok") is not False or schema_probe.get("stage")!="pi_typescript_schema":raise RuntimeError("Unknown semantic field escaped TypeScript schema")
        summary={"schema":"basic-workspace.cycle29-production-preflight","version":1,"inference_performed":False,
            "baseline_revision":11,"mission_a_revision":12,"mission_b_revision":13,"baseline_portable_handles":23,
            "mission_a_tools":ares["active_tools"],"mission_b_tools":bres["active_tools"],
            "mission_a_schema_pretty_bytes":len(json.dumps(ares["schemas"],indent=2).encode()),
            "mission_b_schema_pretty_bytes":len(json.dumps(bres["schemas"],indent=2).encode()),
            "mission_a_schema_compact_bytes":len(json.dumps(ares["schemas"],separators=(",",":")).encode()),
            "mission_b_schema_compact_bytes":len(json.dumps(bres["schemas"],separators=(",",":")).encode()),
            "extension_handler_and_jsonl_gateway":"passed for function creation and typed block replacement",
            "mission_a":{"preview_non_mutating":True,"commit":True,"validation":True,"replay":ares["validation"].get("replay"),
                "rejections":[row.get("code") for row in ares["controls"]],"schema_rejections":len(ares.get("schema_rejections",[]))},
            "mission_b":{"preview_non_mutating":True,"commit":True,"validation":True,"replay":bres["validation"].get("replay"),
                "retired_statement_handles":bres["committed"].get("retired_statement_handles"),
                "new_statement_handle":bres["committed"].get("new_statement_handle"),"rejections":[row.get("code") for row in bres["controls"]],
                "schema_rejections":len(bres.get("schema_rejections",[]))},
            "unknown_semantic_field_schema_rejected":True,"mission_b_checkpoint_verified":True,"passed":True}
        write(out/"summary.json",summary);print(json.dumps(summary,indent=2))
    finally:
        gw.terminate()
        try:gw.wait(timeout=5)
        except subprocess.TimeoutExpired:gw.kill();gw.wait()
        err.close()

if __name__=="__main__":main()
