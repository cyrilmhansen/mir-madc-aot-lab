#!/usr/bin/env python3
"""Model-free Cycle37 rename missions through Cycle19, Cycle36 handoff and Pi JSONL tools."""
from __future__ import annotations
import argparse, copy, json, os, pathlib, socket, subprocess, sys, time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
RESULTS = HERE / "results/cycle37-reusable-rename"
sys.path[:0] = [str(ROOT), str(HERE)]
from basic_workspace.model import Workspace, WorkspaceError
from basic_workspace.projection import build_projection, projection_semantics
from basic_workspace.portable_replay import replay_constructive_stream
from basic_workspace.mir_execution import MirExecutionService
from cycle20_gateway import senior, _call_edges
from cycle26_gateway import Cycle26Gateway
from run_cycle16 import gateway_call
from verified_handoff import build_handoff
from verified_handoff import _fingerprint as handoff_fingerprint

PROFILE = "basic-workspace.numeric-composition.v1"
CREATION_TOOLS = {"workspace_discover_functions", "workspace_inspect_program", "workspace_preview_function",
    "workspace_commit_preview", "workspace_validate_mission"}
RENAME_TOOLS = {"workspace_discover_functions", "workspace_inspect_program", "workspace_preview_rename",
    "workspace_commit_preview", "workspace_validate_mission"}
EXECUTOR = MirExecutionService(timeout=20)
INPUTS = {"mission-a": [-20, -1, 0, 1, 59, 60, 61, 89, 90, 99, 100, 101, 150],
    "mission-b": [-10, -1, 0, 1, 17, 18, 19, 30, 100]}


def read(path): return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
def write(path, value):
    path = pathlib.Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
def stop(proc):
    if proc and proc.poll() is None:
        proc.terminate()
        try: proc.wait(timeout=5)
        except subprocess.TimeoutExpired: proc.kill(); proc.wait(timeout=5)


def oracle(label, x):
    if label == "mission-a":
        score = min(100, max(0, x)); excellent = int(score >= 90)
        return {"bounded_score": float(score), "is_passing": float(score >= 60),
            "is_excellent": float(excellent), "high_priority": float(excellent)}
    return {"has_credit": float(x >= 0), "is_minor": float(x < 18),
        "can_apply": float(x >= 18), "approval_flag": float(x >= 18)}


def fn_request(label, name):
    ref = lambda: {"kind": "local_ref", "name": "X"}
    number = lambda n: {"kind": "number", "value": n}
    call = lambda handle: {"kind": "call", "function_handle": handle, "arguments": [ref()]}
    binary = lambda op, left, right: {"kind": "binary", "operator": op, "left": left, "right": right}
    assign = lambda value: {"kind": "assign", "target": {"kind": "result"}, "expression": value}
    branch = lambda cond, value: {"kind": "if", "condition": cond, "then": [assign(number(value))]}
    if label == "mission-a":
        if name == "BOUNDED_SCORE":
            body = [assign(ref()), branch(binary("<", ref(), number(0)), 0), branch(binary(">", ref(), number(100)), 100)]
        elif name == "IS_PASSING":
            body = [assign(number(0)), branch(binary(">=", call("bounded_score.function"), number(60)), 1)]
        elif name == "IS_EXCELLENT":
            body = [assign(number(0)), branch(binary(">=", call("bounded_score.function"), number(90)), 1)]
        elif name == "HIGH_PRIORITY":
            body = [assign(number(0)), branch(binary(">=", call("is_excellent.function"), number(1)), 1)]
        else: raise ValueError(name)
    else:
        if name == "HAS_CREDIT":
            body = [assign(number(0)), branch(binary(">=", ref(), number(0)), 1)]
        elif name == "IS_MINOR":
            body = [assign(number(0)), branch(binary("<", ref(), number(18)), 1)]
        elif name == "CAN_APPLY":
            body = [assign(number(0)), branch(binary(">=", call("has_credit.function"), number(1)), 1),
                branch(binary(">=", call("is_minor.function"), number(1)), 0)]
        elif name == "APPROVAL_FLAG":
            body = [assign(number(0)), branch(binary(">=", call("can_apply.function"), number(1)), 1)]
        else: raise ValueError(name)
    return {"name": name, "parameters": ["X"], "body": body}


def dispatch(outdir, port, mode, request):
    outdir = pathlib.Path(outdir); outdir.mkdir(parents=True, exist_ok=True)
    inp, result = outdir / "dispatch-input.json", outdir / "dispatch-output.json"
    write(inp, request)
    env = os.environ.copy(); env.update({"BASIC_WS_AUTHORING_MODE": mode,
        "BASIC_WS_PI_GATEWAY": f"127.0.0.1:{port}", "BASIC_WS_DISPATCH_PROBE_INPUT": str(inp),
        "BASIC_WS_DISPATCH_PROBE_OUTPUT": str(result),
        "NODE_PATH": "/usr/lib/node_modules/@earendil-works/pi-coding-agent/node_modules"})
    proc = subprocess.run(["bun", str(HERE / "cycle20b_dispatch_probe.ts")], env=env,
        capture_output=True, text=True, timeout=90)
    (outdir / "dispatch.stdout.log").write_text(proc.stdout, encoding="utf-8")
    (outdir / "dispatch.stderr.log").write_text(proc.stderr, encoding="utf-8")
    if proc.returncode or not result.is_file(): raise RuntimeError(f"TypeScript/JSONL dispatch failed: {proc.stderr[-1500:]}")
    return read(result)


def create_program(label, out):
    source = RESULTS / ("MISSION-A.json" if label == "mission-a" else "MISSION-B.json")
    if not source.is_file():
        source = HERE.parent / "pi-integration/results/cycle35-sequential-creation" / ("MISSION-A.json" if label == "mission-a" else "MISSION-B.json")
    sequence = read(source); seq_path = out / label / "creation-sequence.json"; write(seq_path, sequence)
    arm = out / label / "creation"; evidence = arm / "gateway-evidence"; arm.mkdir(parents=True, exist_ok=True)
    stderr = (arm / "gateway.stderr.log").open("w", encoding="utf-8")
    env = os.environ.copy(); env["PYTHONPATH"] = os.pathsep.join((str(ROOT), str(HERE), env.get("PYTHONPATH", "")))
    proc = subprocess.Popen([sys.executable, str(HERE / "cycle19_gateway.py"), "--output", str(evidence),
        "--port", "0", "--creation-sequence", str(seq_path)], stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=stderr, text=True, env=env)
    step_results=[]; schemas=None
    try:
        line=proc.stdout.readline()
        if not line: raise RuntimeError(f"Cycle19 creation gateway failed: {arm/'gateway.stderr.log'}")
        ready=json.loads(line)
        if not ready.get("ready") or ready.get("revision")!=1: raise RuntimeError(f"Expected empty revision-1 Workspace: {ready}")
        early=gateway_call("127.0.0.1",ready["port"],"host_advance_creation_sequence",{"checkpoint":{}})
        if early.get("code")!="SEQUENCE_STEP_NOT_VALIDATED": raise RuntimeError(f"Unvalidated progression was not rejected: {early}")
        for index,step in enumerate(sequence["steps"]):
            args={"expected_revision":step["expected_base_revision"],**fn_request(label,step["function"]["name"])}
            controls=[{**args,"name":"UNAUTHORIZED_FUNCTION"},{**args,"expected_revision":args["expected_revision"]-1}]
            if step["required_callees"]:
                bad=copy.deepcopy(args)
                def corrupt(value):
                    if isinstance(value,dict):
                        if value.get("kind")=="call": value["function_handle"]="invented.function"; return True
                        return any(corrupt(v) for v in value.values())
                    if isinstance(value,list): return any(corrupt(v) for v in value)
                    return False
                corrupt(bad["body"]); controls.append(bad)
            request={"authoring_mode":"atomic_create","correlation_id":f"cycle37-{label}-create-{index}-{time.time_ns()}",
                "preview_args":args,"controls":controls,"commit":True}
            result=dispatch(arm/f"step-{index+1:02d}",ready["port"],"atomic_create",request)
            if not result.get("schema_ok") or set(result.get("active_tools",[]))!=CREATION_TOOLS:
                raise RuntimeError("Cycle35 constructor tool inventory/schema mismatch")
            if schemas is None: schemas=result["schemas"]
            expected_codes=["MISSION_SIGNATURE","STALE_REVISION"]
            if step["required_callees"]: expected_codes.append("MISSION_DEPENDENCY_REQUIRED")
            codes=[row.get("code") for row in result.get("controls",[])]
            if codes!=expected_codes: raise RuntimeError(f"Creation authorization controls failed: {codes}")
            if not result.get("preview",{}).get("candidate_is_preview_only"):
                raise RuntimeError("Constructor preview was not a preview-only candidate")
            committed=result.get("committed",{})
            if not committed.get("committed") or committed.get("revision")!=index+2:
                raise RuntimeError(f"Constructor did not advance one revision: {committed}")
            validation=gateway_call("127.0.0.1",ready["port"],"host_validate",{"expected_revision":index+2})
            expected=step["validation"]["expected_results"]
            if (not validation.get("mission_complete") or validation.get("observed_results",{}).get("interp")!=expected
                    or validation.get("observed_results",{}).get("jit")!=expected):
                raise RuntimeError(f"Cycle35 host oracle failed at revision {index+2}")
            checkpoint=gateway_call("127.0.0.1",ready["port"],"create_checkpoint",{})
            advanced=gateway_call("127.0.0.1",ready["port"],"host_advance_creation_sequence",{"checkpoint":checkpoint.get("checkpoint",{})})
            if not checkpoint.get("ok") or not advanced.get("ok"): raise RuntimeError("Validated creation checkpoint failed progression")
            step_results.append({"revision":index+2,"function":step["function"],"expected":expected,
                "interpreter":validation["observed_results"]["interp"],"jit":validation["observed_results"]["jit"],
                "fingerprint":checkpoint["checkpoint"]["semantic_fingerprint"],"progression":advanced})
        status=gateway_call("127.0.0.1",ready["port"],"get_status",{})
        if not status.get("sequence_complete") or status.get("revision")!=len(sequence["steps"])+1:
            raise RuntimeError(f"Creation sequence did not finish: {status}")
        stream=read(evidence/"constructive-operations.json")
        if len(stream["operations"])!=len(sequence["steps"]): raise RuntimeError("Creation history did not contain one constructor per step")
        return {"sequence":sequence,"sequence_path":evidence/"creation-sequence.json","arm":arm,"evidence":evidence,
            "steps":step_results,"final_revision":status["revision"],"portable_handles":sorted(stream["portable_handles"]),
            "schema":schemas,"premature_advance_rejected":early.get("code")}
    finally:
        stop(proc); stderr.close()


def rename_contract(label, creation, out):
    source_name,target_handle,new_name=("BOUNDED_SCORE","bounded_score.function","NORMALIZED_SCORE") if label=="mission-a" else (
        "HAS_CREDIT","has_credit.function","HAS_NONNEGATIVE_CREDIT")
    functions=[step["function"]["portable_handle"] for step in creation["sequence"]["steps"]]
    inputs=creation["sequence"]["steps"][-1]["validation"]["inputs"]
    contract={"schema":"basic-workspace.semantic-rename-contract","version":2,
        "mission_id":f"cycle37.{label}.provider-rename.v2","objective":f"Rename {source_name} to {new_name}, preserving identity, bindings and behavior.",
        "base_document_revision":creation["final_revision"],"execution_profile_id":PROFILE,
        "target_handle":target_handle,"expected_source_name":source_name,"new_source_name":new_name,
        "unchanged_function_handles":[handle for handle in functions if handle!=target_handle],
        "unchanged_dependency_edges":True,"required_revision_increment":1,"validation_inputs":inputs}
    path=out/"rename-contract.json";write(path,contract);return path,contract


def run_rename(label, creation, out):
    mission=out/label;contract_path,contract=rename_contract(label,creation,mission)
    handoff_dir=mission/"handoff";handoff=handoff_dir/"handoff.json";anchor=handoff_dir/"host-trust-anchor.json"
    bundle,trust=build_handoff(creation["evidence"],creation["sequence_path"],contract_path,handoff,anchor)
    evidence=mission/"rename"/"gateway-evidence";evidence.parent.mkdir(parents=True,exist_ok=True)
    stderr=(mission/"rename"/"gateway.stderr.log").open("w",encoding="utf-8")
    env=os.environ.copy();env["PYTHONPATH"]=os.pathsep.join((str(ROOT),str(HERE),env.get("PYTHONPATH","")))
    proc=subprocess.Popen([sys.executable,str(HERE/"cycle26_gateway.py"),"--output",str(evidence),"--contract",str(contract_path),
        "--verified-handoff",str(handoff),"--handoff-anchor",str(anchor),"--handoff-evidence-root",str(creation["evidence"]),"--port","0"],
        stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=stderr,text=True,env=env)
    try:
        line=proc.stdout.readline()
        if not line: raise RuntimeError(f"Cycle36 verified rename gateway failed to initialize; see {stderr.name}")
        ready=json.loads(line);base_rev=creation["final_revision"]
        if not ready.get("ready") or ready.get("revision")!=base_rev or ready.get("identity_count")!=len(creation["portable_handles"]):
            raise RuntimeError(f"Rename gateway did not authenticate reconstructed baseline: {ready}")
        verifier=read(evidence/"verified-handoff.json")
        if verifier.get("passed") is not True: raise RuntimeError("Missing positive handoff verification receipt")
        baseline=read(evidence/"baseline-observations.json");expected_before={str(x):oracle(label,x) for x in INPUTS[label]}
        from_names={step["function"]["name"].lower():step["function"]["portable_handle"] for step in creation["sequence"]["steps"]}
        converted=baseline["expected_portable_handle_results"]
        expected_by_handle={str(x):{handle:expected_before[str(x)][name] for name,handle in from_names.items()} for x in INPUTS[label]}
        if converted["interp"]!=expected_by_handle or converted["jit"]!=expected_by_handle:
            raise RuntimeError("Independent arithmetic oracle differs from authenticated Cycle35 expectations")
        before_source=read(evidence/"visual-source.json")["initial"]["code"]
        base_request={"expected_revision":base_rev,"function_handle":contract["target_handle"],
            "expected_name":contract["expected_source_name"],"new_name":contract["new_source_name"]}
        controls=[{**base_request,"function_handle":"invented.function"},
            {**base_request,"expected_name":"WRONG_NAME"},
            {**base_request,"new_name":"UNAUTHORIZED_NAME"},
            {**base_request,"function_handle":creation["sequence"]["steps"][1]["function"]["portable_handle"]},
            {**base_request,"expected_revision":base_rev-1}]
        result=dispatch(mission/"rename",ready["port"],"rename",{"authoring_mode":"rename",
            "correlation_id":f"cycle37-{label}-rename-{time.time_ns()}","preview_args":base_request,
            "controls":controls,"commit":True,"duplicate_commit":True})
        if not result.get("schema_ok") or set(result.get("active_tools",[]))!=RENAME_TOOLS:
            raise RuntimeError("Rename Pi schema or active tool allowlist mismatch")
        codes=[row.get("code") for row in result.get("controls",[])]
        expected_codes=["MISSION_RENAME_SCOPE","RENAME_PRECONDITION_FAILED","MISSION_RENAME_NAME","MISSION_RENAME_SCOPE","STALE_REVISION"]
        if codes!=expected_codes: raise RuntimeError(f"Rename contract controls failed: {codes}")
        if not result["preview"].get("candidate_is_preview_only") or result["preview"].get("base_revision")!=base_rev:
            raise RuntimeError("Rename preview mutated or advanced the committed baseline")
        if result["committed"].get("revision")!=base_rev+1 or result["duplicate_commit"].get("committed") is not False:
            raise RuntimeError("Rename did not commit exactly once or duplicate commit was accepted")
        if "CLAMP_SCORE" in before_source and label=="mission-a": pass
        validation=result.get("validation",{})
        if not validation.get("mission_complete"): raise RuntimeError("Typed production bridge rename validation failed")
        host=gateway_call("127.0.0.1",ready["port"],"host_validate",{"expected_revision":base_rev+1})
        if not host.get("mission_complete"): raise RuntimeError("Independent host rename validation failed")
        malformed={**base_request,"unknown_semantic_field":True}
        schema_result=dispatch(mission/"schema-negative",ready["port"],"rename",{"authoring_mode":"rename",
            "correlation_id":f"cycle37-{label}-unknown-field-{time.time_ns()}","preview_args":malformed})
        if schema_result.get("schema_ok") is not False or schema_result.get("stage")!="pi_typescript_schema":
            raise RuntimeError("TypeScript rename schema accepted an unknown semantic field")
        final_stream=read(evidence/"constructive-operations.json")
        final_ws=Workspace();doc=final_ws.create_empty_document(f"memory://cycle37/{label}/final-replay.bas")["document_id"]
        replay=replay_constructive_stream(final_ws,doc,final_stream["operations"],expected_start_revision=1,
            expected_final_handles=final_stream["portable_handles"],expected_retired_handles=[])
        norm=senior.normalized_state(projection_semantics(build_projection(final_ws,doc,replay.revision)),replay.live_handles)
        observed={engine:{} for engine in ("interp","jit")}
        for engine in observed:
            for x in INPUTS[label]:
                observed[engine][str(x)]={handle:EXECUTOR.execute_function(final_ws,doc,replay.revision,replay.live_handles[handle],[x],engine)["result"]
                    for handle in sorted(replay.live_handles) if handle.endswith(".function")}
        if observed!=host["observed_results_by_portable_handle"]: raise RuntimeError("Independent fresh replay differs from gateway host observations")
        if observed["interp"]!=expected_by_handle or observed["jit"]!=expected_by_handle:
            raise RuntimeError("Fresh replay does not match independent function oracle")
        after_aliases=read(evidence/"constructive-operations.json")["portable_handles"]
        if sorted(after_aliases)!=creation["portable_handles"]: raise RuntimeError("Rename changed portable handle set")
        target=contract["target_handle"]
        # Candidate authorization already compares exact normalized baseline modulo the one target name.
        if (not host["normalized_structure_modulo_target_name"] or not host["dependency_identity_edges_unchanged"]
                or not host["token_identity_set_preserved"] or not host["all_portable_identities_preserved"]):
            raise RuntimeError("Host structural or dependency invariant failed")
        prefix_rows={};creation_count=len(creation["sequence"]["steps"])
        result_keys={step["function"]["portable_handle"]:step["function"]["name"].lower() for step in creation["sequence"]["steps"]}
        for prefix in range(1,len(final_stream["operations"])+1):
            prefix_ws=Workspace();prefix_doc=prefix_ws.create_empty_document(f"memory://cycle37/{label}/prefix-{prefix}.bas")["document_id"]
            prefix_replay=replay_constructive_stream(prefix_ws,prefix_doc,final_stream["operations"][:prefix],expected_start_revision=1)
            prefix_state=senior.normalized_state(projection_semantics(build_projection(prefix_ws,prefix_doc,prefix_replay.revision)),prefix_replay.live_handles)
            prefix_observed={engine:{} for engine in ("interp","jit")}
            for engine in prefix_observed:
                for x in INPUTS[label]:
                    prefix_observed[engine][str(x)]={handle:EXECUTOR.execute_function(prefix_ws,prefix_doc,prefix_replay.revision,
                        prefix_replay.live_handles[handle],[x],engine)["result"] for handle in sorted(prefix_replay.live_handles)
                        if handle.endswith(".function")}
            available={result_keys[h] for h in prefix_replay.live_handles if h in result_keys}
            prefix_expected={str(x):{handle:oracle(label,x)[result_keys[handle]] for handle in sorted(prefix_replay.live_handles)
                if handle in result_keys} for x in INPUTS[label]}
            if prefix_observed["interp"]!=prefix_expected or prefix_observed["jit"]!=prefix_expected:
                raise RuntimeError(f"Prefix revision {prefix_replay.revision} differs from independent oracle")
            checkpoint_ok=None
            if prefix<=creation_count:
                checkpoint=read(creation["evidence"]/f"checkpoint-step-{prefix:02d}.json")
                checkpoint_ok=handoff_fingerprint(prefix_replay.revision,prefix_state)==checkpoint["semantic_fingerprint"]
                if not checkpoint_ok: raise RuntimeError(f"Creation checkpoint mismatch at revision {prefix_replay.revision}")
            if prefix==len(final_stream["operations"]) and prefix_state!=norm:
                raise RuntimeError("Complete constructive stream normalized state differs from committed rename gateway")
            prefix_rows[str(prefix_replay.revision)]={"operation_prefix":prefix,"normalized_semantics":prefix_state,
                "function_signatures":[{"handle":row["handle"],"name":row["name"],"parameters":row["parameters"],
                    "return_type":row["return_type"]} for row in prefix_state["functions"]],
                "dependencies":_call_edges(prefix_state),"portable_handles":sorted(prefix_replay.live_handles),
                "interpreter":prefix_observed["interp"],"jit":prefix_observed["jit"],"oracle_match":True,
                "creation_checkpoint_match":checkpoint_ok}
        write(mission/"revision-snapshots.json",{"prefixes":prefix_rows,"passed":True})
        write(mission/"identity-ledger.json",{"initial_mapping":read(evidence/"baseline-reconstruction.json")["identity_mapping"],
            "maintenance_to_replay_mapping":host["replay"]["identity_mapping"],
            "live_handles_before":sorted(creation["portable_handles"]),"live_handles_after":sorted(after_aliases),
            "retired_handles":host["replay"]["retired_handles"],"new_handles":[],"preserved":True,
            "token_identity_set_preserved":host["token_identity_set_preserved"]})
        write(mission/"independent-oracle-observations.json",{"input_corpus":INPUTS[label],"expected":expected_by_handle,
            "before_interpreter":converted["interp"],"before_jit":converted["jit"],
            "after_interpreter":host["observed_results_by_portable_handle"]["interp"],
            "after_jit":host["observed_results_by_portable_handle"]["jit"],"all_agree":True,
            "oracle_source":"Cycle35 final step host contract, independently recomputed arithmetic reference"})
        write(mission/"replay-equivalence.json",{"revision":replay.revision,"expected_revision":base_rev+1,
            "operation_count":len(final_stream["operations"]),"portable_handles":sorted(replay.live_handles),
            "retired_handles":replay.retired_handles,"normalized_semantics":norm,"bindings":_call_edges(norm),
            "interpreter":observed["interp"],"jit":observed["jit"],"passed":True})
        summary={"mission":label,"handoff_verified":True,"base_revision":base_rev,"final_revision":replay.revision,
            "construction_operations":len(creation["steps"]),"rename_operations":1,"portable_identity_count":len(replay.live_handles),
            "active_tools":sorted(result["active_tools"]),"schema_bytes_compact":len(json.dumps(result["schemas"],separators=(",",":")).encode()),
            "preview_non_mutating":True,"rejected_controls":codes,"unknown_field_rejected":True,
            "duplicate_commit_code":result["duplicate_commit"].get("code"),"host_validation":host["mission_complete"],
            "replay_passed":True,"inference_performed":False}
        write(mission/"bridge-validation.json",summary)
        return {"contract":contract,"creation":creation,"handoff":bundle,"anchor":trust,"bridge":summary,
            "host_validation":host,"gateway_evidence":evidence,"normalized":norm,"observed":observed}
    finally:
        stop(proc); stderr.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--output",type=pathlib.Path,default=RESULTS/"production-bridge-attempt-04")
    args=parser.parse_args();out=args.output.resolve()
    if out.exists() and any(out.iterdir()):raise SystemExit(f"refusing to overwrite evidence: {out}")
    if not os.path.exists("/usr/bin/bun") and not __import__("shutil").which("bun"):raise SystemExit("Bun is required for production bridge validation")
    out.mkdir(parents=True,exist_ok=True)
    summaries={}
    for label in ("mission-a","mission-b"):
        creation=create_program(label,out); renamed=run_rename(label,creation,out);summaries[label]=renamed["bridge"]
    write(out/"bridge-validation.json",{"schema":"basic-workspace.cycle37-production-bridge","version":1,
        "inference_performed":False,"missions":summaries,"passed":True})
    print(json.dumps(summaries,indent=2))

if __name__=="__main__":main()
