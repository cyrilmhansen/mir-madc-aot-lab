#!/usr/bin/env python3
"""No-inference production TypeScript-handler -> JSONL gateway preflight."""
from __future__ import annotations
import argparse,json,os,pathlib,socket,subprocess,sys,time
HERE=pathlib.Path(__file__).resolve().parent; ROOT=HERE.parent
OUT=HERE/"results/cycle28-conditional-refactor/deterministic-preflight/production-bridge"
CONTRACT=HERE/"results/cycle28-conditional-refactor/contracts/mission.json"
TOOLS=["workspace_discover_functions","workspace_inspect_program","workspace_commit_preview","workspace_validate_mission","workspace_preview_conditional_edit"]

def write(path,value):pathlib.Path(path).parent.mkdir(parents=True,exist_ok=True);pathlib.Path(path).write_text(json.dumps(value,indent=2,ensure_ascii=False)+"\n")
def dispatch(out,port,request,tag):
    ip=out/f"{tag}-input.json";op=out/f"{tag}-output.json";write(ip,request)
    env=os.environ.copy();env.update({"BASIC_WS_AUTHORING_MODE":"conditional_edit","BASIC_WS_PI_GATEWAY":f"127.0.0.1:{port}",
      "BASIC_WS_DISPATCH_PROBE_INPUT":str(ip),"BASIC_WS_DISPATCH_PROBE_OUTPUT":str(op),
      "NODE_PATH":"/usr/lib/node_modules/@earendil-works/pi-coding-agent/node_modules"})
    p=subprocess.run(["bun",str(HERE/"cycle20b_dispatch_probe.ts")],env=env,capture_output=True,text=True,timeout=120)
    (out/f"{tag}.stdout.log").write_text(p.stdout);(out/f"{tag}.stderr.log").write_text(p.stderr)
    if p.returncode or not op.is_file():raise RuntimeError(f"production dispatch failed: {p.stderr[-1500:]}")
    return json.loads(op.read_text())

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--output",type=pathlib.Path,default=OUT);a=ap.parse_args();out=a.output.resolve()
    if out.exists() and any(out.iterdir()):raise SystemExit(f"refusing to overwrite {out}")
    out.mkdir(parents=True,exist_ok=True)
    env=os.environ.copy();env["PYTHONPATH"]=str(ROOT)+os.pathsep+str(HERE)+os.pathsep+env.get("PYTHONPATH","")
    with socket.socket() as s:s.bind(("127.0.0.1",0));port=s.getsockname()[1]
    err=(out/"gateway-stderr.log").open("w")
    gw=subprocess.Popen([sys.executable,str(HERE/"cycle28_gateway.py"),"--output",str(out/"gateway-evidence"),"--contract",str(CONTRACT),"--port",str(port)],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=err,text=True,env=env)
    try:
        ready=json.loads(gw.stdout.readline())
        if not ready.get("ready") or ready.get("revision")!=10 or ready.get("identity_count")!=23:raise RuntimeError(f"Cycle 27 baseline reconstruction failed: {ready}")
        good={"expected_revision":10,"function_handle":"score_class.function","control_path":[{"block":"body","index":2}],"anchor_statement_handle":"score_class.statement.category50",
          "expected_condition":{"kind":"binary","operator":"=","left":{"kind":"call","function_handle":"clamp_score.function","arguments":[{"kind":"local_ref","name":"X"}]},"right":{"kind":"number","value":50}},
          "condition":{"kind":"binary","operator":"=","left":{"kind":"call","function_handle":"is_at_cap.function","arguments":[{"kind":"local_ref","name":"X"}]},"right":{"kind":"number","value":1}}}
        controls=[]
        def clone():return json.loads(json.dumps(good))
        wrong_target=clone();wrong_target["control_path"][0]["index"]=1;controls.append(wrong_target)
        wrong_old=clone();wrong_old["expected_condition"]["right"]["value"]=49;controls.append(wrong_old)
        unknown_callee=clone();unknown_callee["condition"]["left"]["function_handle"]="not-discovered.function";controls.append(unknown_callee)
        bad_arity=clone();bad_arity["condition"]["left"]["arguments"]=[];controls.append(bad_arity)
        unauthorized=clone();unauthorized["condition"]["left"]["function_handle"]="is_passing.function";controls.append(unauthorized)
        assignment_target=clone();assignment_target["statement_handle"]="score_class.statement.category50";controls.append(assignment_target)
        stale=clone();stale["expected_revision"]=9;controls.append(stale)
        req={"authoring_mode":"conditional_edit","correlation_id":f"cycle28-preflight-{time.time_ns()}","preview_args":good,"controls":controls,"commit":True,"duplicate_commit":True}
        got=dispatch(out,ready["port"],req,"actual-production-dispatch")
        schemas=got["schemas"];write(out/"tool-inventory.json",{"source":"actual ExtensionAPI registry via deterministic handler harness","tools":got["active_tools"]});write(out/"tool-schemas.json",schemas)
        if not got.get("schema_ok") or sorted(got["active_tools"])!=sorted(TOOLS):raise RuntimeError("active tool inventory mismatch")
        if got["discovery"]["revision"]!=10:raise RuntimeError("discovery revision mismatch")
        if got["inspection"]["conditional_edit_target"]["anchor_statement_handle"]!="score_class.statement.category50":raise RuntimeError("verified anchor missing")
        schema_rejs=got.get("schema_rejections",[])
        if [x["index"] for x in schema_rejs]!=[3,5]:raise RuntimeError(f"expected bad arity and assignment-shaped requests schema rejection, got {[x['index'] for x in schema_rejs]}")
        controls_result=got["controls"]
        codes=[x.get("code") for x in controls_result]
        expected=["MISSION_TARGET_DENIED","EXPECTED_IF_CONDITION_MISMATCH","FUNCTION_NOT_DISCOVERED","MISSION_CONDITION_DENIED","STALE_REVISION"]
        if codes!=expected:raise RuntimeError(f"unexpected gateway negative outcomes {codes}")
        if any(x.get("revision_unchanged") is not True or x.get("authoritative_workspace_changed") is not False for x in controls_result):raise RuntimeError("rejected preview had side effects")
        preview=got["preview"]
        if not preview.get("ok") or not preview.get("candidate_is_preview_only") or preview.get("base_revision")!=10:raise RuntimeError("candidate preview not accepted/non-mutating")
        if got.get("committed",{}).get("revision")!=11 or not got.get("validation",{}).get("mission_complete"):raise RuntimeError("commit or host oracle failed")
        if got.get("duplicate_commit",{}).get("committed") is not False:raise RuntimeError("duplicate commit not rejected")
        # Unknown top-level semantic/transport fields must be rejected by the same actual TypeBox schema.
        unknown=clone();unknown["toolCallId"]="transport-only"
        bad=dispatch(out,ready["port"],{"authoring_mode":"conditional_edit","correlation_id":f"cycle28-schema-{time.time_ns()}","preview_args":unknown},"schema-boundary")
        if bad.get("schema_ok") is not False or bad.get("stage")!="pi_typescript_schema":raise RuntimeError("unknown field escaped active schema")
        schema_bytes=pathlib.Path(out/"tool-schemas.json").stat().st_size
        compact_bytes=len(json.dumps(schemas,ensure_ascii=False,separators=(",",":")).encode())
        summary={"schema":"basic-workspace.cycle28-preflight","version":1,"inference_performed":False,"baseline_revision":10,"revision_after_commit":11,
          "portable_handles":23,"active_tools":got["active_tools"],"tool_schema_pretty_bytes":schema_bytes,"tool_schema_compact_json_bytes":compact_bytes,
          "typescript_handler_and_jsonl_gateway":"passed","preview_non_mutating":True,"negative_gateway_codes":codes,
          "schema_rejections":[{"index":x["index"],"errors":x["errors"]} for x in schema_rejs],"unknown_semantic_field_rejected":True,
          "commit_once":True,"duplicate_commit_rejected":True,"mir_interpreter_jit":True,"fresh_replay":got["validation"].get("replay"),"passed":True}
        write(out/"summary.json",summary);print(json.dumps(summary,indent=2))
    finally:
        gw.terminate()
        try:gw.wait(timeout=5)
        except subprocess.TimeoutExpired:gw.kill();gw.wait()
        err.close()
if __name__=="__main__":main()
