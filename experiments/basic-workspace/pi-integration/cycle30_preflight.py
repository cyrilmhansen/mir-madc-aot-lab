#!/usr/bin/env python3
"""Cycle 30 deterministic production-handler and JSONL bridge preflight."""
from __future__ import annotations
import json, os, pathlib, socket, subprocess, sys, time, tempfile
import argparse
HERE=pathlib.Path(__file__).resolve().parent
ROOT=HERE.parent
sys.path.insert(0,str(ROOT))
from basic_workspace.model import Workspace
from basic_workspace.portable_replay import replay_constructive_stream
OUT=HERE/"results/cycle30-post-extraction-maintenance"
CONTRACT=OUT/"mission-contract.json"
STREAM=HERE/"results/cycle29-function-extraction/real-agent-01/constructive-operations.json"
HISTORY=HERE/"results/cycle29-function-extraction/real-agent-01/history.jsonl"
VALIDATION=HERE/"results/cycle29-function-extraction/real-agent-01/mission-2-validation-host.json"
TOOLS=["workspace_discover_functions","workspace_inspect_program","workspace_preview_semantic_edit","workspace_commit_preview","workspace_validate_mission"]

def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

def end(proc,err):
    if proc.poll() is None:
        proc.terminate()
        try:proc.wait(timeout=5)
        except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=5)
    err.close()

def dispatch(case,port,request):
    inp=case/"dispatch-input.json"; out=case/"dispatch-output.json"
    write(inp,request)
    env=os.environ.copy(); env.update({"BASIC_WS_AUTHORING_MODE":"semantic_edit","BASIC_WS_PI_GATEWAY":f"127.0.0.1:{port}",
        "BASIC_WS_DISPATCH_PROBE_INPUT":str(inp.resolve()),"BASIC_WS_DISPATCH_PROBE_OUTPUT":str(out.resolve()),
        "NODE_PATH":"/usr/lib/node_modules/@earendil-works/pi-coding-agent/node_modules"})
    run=subprocess.run(["bun",str(HERE/"cycle20b_dispatch_probe.ts")],env=env,capture_output=True,text=True,timeout=45)
    (case/"dispatch.stdout.log").write_text(run.stdout,encoding="utf-8")
    (case/"dispatch.stderr.log").write_text(run.stderr,encoding="utf-8")
    if run.returncode or not out.is_file():raise RuntimeError(f"real extension/bridge probe failed: {run.stderr[-1200:]}")
    return json.loads(out.read_text())

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=pathlib.Path,default=OUT/"production-bridge-preflight-05")
    parser.add_argument("--pi-schema-dir",type=pathlib.Path,default=OUT/"pi-preflight")
    parser.add_argument("--contract",type=pathlib.Path,default=CONTRACT)
    args=parser.parse_args()
    case=args.output.resolve()
    case.mkdir(parents=True,exist_ok=False)
    err=(case/"gateway.stderr.log").open("w",encoding="utf-8")
    cmd=[sys.executable,str(HERE/"cycle20_gateway.py"),"--output",str(case/"gateway-evidence"),"--contract",str(args.contract.resolve()),
        "--baseline-stream",str(STREAM),"--baseline-history",str(HISTORY),"--baseline-validation",str(VALIDATION),"--port","0"]
    proc=subprocess.Popen(cmd,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=err,text=True)
    try:
        ready=json.loads(proc.stdout.readline())
        if not ready.get("ready") or ready.get("revision")!=13 or not ready.get("baseline_verified") or not ready.get("contract_verified"):
            raise RuntimeError(f"revision-13 replay preflight failed: {ready}")
        # One genuine-shaped production tool dispatch has TypeScript validate the exact schema,
        # then discover/inspect/preview/commit/validate through the Python JSONL server.
        edit={"target":{"function_handle":"base_score_class.function","control_path":[{"block":"body","index":0}],"expression_path":[1]},
            "expected_value":20,"replacement_value":25}
        proposal={"expected_revision":13,"function_handle":"base_score_class.function","edits":[edit]}
        controls=[]
        retired="score_class.statement.0"
        for label,mutate in [
            ("retired_statement_handle",lambda p:p["edits"][0].update(target={"function_handle":"score_class.function","statement_handle":retired,"expression_path":[]})),
            ("incorrect_old_literal",lambda p:p["edits"][0].update(expected_value=19)),
            ("wrong_function",lambda p:p["edits"][0]["target"].update(function_handle="clamp_score.function")),
            ("stale_revision",lambda p:p.update(expected_revision=12)),
            ("unauthorized_additional_edit",lambda p:p["edits"].append(json.loads(json.dumps(edit)))),
            ("unknown_semantic_field",lambda p:p.update(source_text="FUNCTION BASE_SCORE_CLASS(X)")),
        ]:
            candidate=json.loads(json.dumps(proposal)); mutate(candidate); controls.append({"label":label,"args":candidate})
        result=dispatch(case,ready["port"],{"correlation_id":"cycle30-deterministic-preflight-01","preview_args":proposal,
            "controls":[x["args"] for x in controls],"commit":True,"duplicate_commit":True})
        pi_schema_path=case/"pi-schema-capture.json"
        active_schemas=result.get("schemas",[])
        write(pi_schema_path,active_schemas)
        captured_pi=json.loads((args.pi_schema_dir.resolve()/"tool-schemas.json").read_text(encoding="utf-8"))
        if active_schemas != captured_pi:
            raise RuntimeError("Production TypeScript registration differs from Pi's active schema capture")
        if not result.get("schema_ok") or set(result.get("active_tools",[]))!=set(TOOLS):
            raise RuntimeError("actual TypeScript handler did not expose the five expected semantic tools")
        if sorted(result.get("inspection",{}).get("retired_portable_handles",[])) != ["score_class.statement.0","score_class.statement.1"]:
            raise RuntimeError("Inspection did not report the current retired-handle set")
        preview=result["preview"]
        if not preview.get("accepted") or preview.get("base_revision")!=13 or not preview.get("candidate_is_preview_only"):
            raise RuntimeError(f"candidate preview was not accepted and non-mutating: {preview}")
        if result.get("committed",{}).get("revision")!=14 or not result.get("validation",{}).get("mission_complete"):
            raise RuntimeError("disposable production-path commit or independent validation failed")
        if not result.get("validation",{}).get("replay",{}).get("passed"):
            raise RuntimeError("fresh-workspace constructive replay failed")
        if result.get("duplicate_commit",{}).get("committed") is not False:
            raise RuntimeError("duplicate commit was not rejected")
        if len(result.get("controls",[]))+len(result.get("schema_rejections",[]))!=len(controls):
            raise RuntimeError("some deterministic negative controls were not accounted for")
        if any(row.get("ok") is not False or row.get("revision_unchanged") is not True or row.get("authoritative_workspace_changed") is not False
            for row in result.get("controls",[])):
            raise RuntimeError("a prohibited proposal was authorized or mutated the Workspace")
        final=result["validation"]
        # Check the expected propagation and unchanged graph directly in independent MIR observations.
        expected={"20":0.0,"24":0.0,"25":1.0,"45":2.0,"50":3.0}
        for engine in ("interp","jit"):
            for x,want in expected.items():
                if final["observed_results"][engine][x]["score_class"]!=want:
                    raise RuntimeError(f"contract oracle mismatch for {engine} SCORE_CLASS({x})")
        if final["observed_results"]["interp"]!=final["observed_results"]["jit"]:
            raise RuntimeError("MIR interpreter and JIT disagree")
        # Exercise target and anchor resolution through the same gateway object.
        import importlib.util
        sys.path.insert(0,str(HERE))
        spec=importlib.util.spec_from_file_location("cycle20_gateway_cycle30",HERE/"cycle20_gateway.py")
        mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod;spec.loader.exec_module(mod)
        with tempfile.TemporaryDirectory(prefix="atlas-cycle30-retired-check-",dir="/var/tmp") as td:
            direct=mod.Cycle20Gateway(pathlib.Path(td)/"gateway",contract_path=args.contract.resolve(),
                baseline_stream_path=STREAM,baseline_history_path=HISTORY,baseline_validation_path=VALIDATION)
            retired_rows=json.loads(STREAM.read_text())["retired_handles"]
            before_revision=direct.ws.get_revision(direct.doc)
            direct.handle("discover_functions",{},"cycle30-retired-discovery")
            inspected=direct.handle("inspect_program",{},"cycle30-retired-inspection")
            if set(retired_rows)&set(direct.aliases): raise RuntimeError("retired identity entered active alias map")
            if set(inspected.get("retired_portable_handles",[]))!=set(retired_rows): raise RuntimeError("inspection omitted retired identities")
            for retired_handle in retired_rows:
                retired_target={"function_handle":"score_class.function","statement_handle":retired_handle,"expression_path":[]}
                try: direct._target_expression(direct.baseline,retired_target)
                except Exception as exc: target_error=getattr(exc,"code",type(exc).__name__)
                else: raise RuntimeError("retired statement unexpectedly resolved as a live edit target")
                retired_block=json.loads(STREAM.read_text())["operations"][-1]
                retired_block["anchor_statement_handle"]=retired_handle
                retired_ops=json.loads(STREAM.read_text())["operations"]
                retired_ops.append(retired_block)
                try:
                    test_ws=Workspace();test_doc=test_ws.create_empty_document("memory://cycle30/retired-anchor-preflight.bas")["document_id"]
                    replay_constructive_stream(test_ws,test_doc,retired_ops)
                except Exception as exc: anchor_error=getattr(exc,"code",type(exc).__name__)
                else: raise RuntimeError("retired statement unexpectedly resolved as a live anchor")
            if direct.ws.get_revision(direct.doc)!=before_revision:
                raise RuntimeError("retired identity rejection changed the authoritative revision")
        baseline=json.loads((case/"gateway-evidence/baseline-reconstruction.json").read_text())
        migration={"schema":"basic-workspace.cycle30.identity-state","version":1,"revisions":{
            "11":{"note":"authentic Cycle 28 state before helper creation","active_count":23,"retired":[]},
            "12":{"created":["base_score_class.function","base_score_class.parameter.id","base_score_class.statement.0","base_score_class.statement.1","base_score_class.statement.2"],"active_count":28,"retired":[]},
            "13":{"created":["score_class.statement.extracted-base-call"],"retired":["score_class.statement.0","score_class.statement.1"],"active_count":27},
            "14":{"created":[],"retired":["score_class.statement.0","score_class.statement.1"],"active_count":27}},
            "reconstructed_revision":baseline["resulting_revision"],"live_handles":baseline["portable_identity_count"],
            "retired_handles_unresolvable":True}
        write(case/"identity-state-ledger.json",migration)
        summary={"schema":"basic-workspace.cycle30.production-preflight","version":1,"inference_performed":False,
            "baseline_revision":13,"disposable_commit_revision":14,"active_tools":result["active_tools"],
            "tool_schema_pretty_bytes":len(json.dumps(active_schemas,ensure_ascii=False,indent=2).encode()),
            "tool_schema_compact_bytes":len(json.dumps(active_schemas,ensure_ascii=False,separators=(",",":")).encode()),
            "proposal_schema_valid":True,"preview_non_mutating":True,"commit_atomic":True,"host_oracle_passed":True,
            "interpreter_jit_agree":True,"fresh_replay_passed":True,"retired_statement_handles":["score_class.statement.0","score_class.statement.1"],
            "controls":[{"index":i,"label":control["label"]} for i,control in enumerate(controls)],
            "retired_identity_checks":{"active_alias_absent":True,"discovery_inspection_reported_retirement":True,
                "edit_target_rejection_codes":sorted({target_error}),"insertion_anchor_rejection_codes":sorted({anchor_error}),
                "revision_unchanged":True,"model_visible_insertion_tool":False},
            "transport_correlation":"real TypeScript tool-call IDs were sent as JSONL transport metadata and did not enter semantic params",
            "production_handler_and_bridge":"passed","passed":True}
        write(case/"summary.json",summary)
        print(json.dumps(summary,indent=2))
    finally:
        end(proc,err)

if __name__=="__main__":main()
