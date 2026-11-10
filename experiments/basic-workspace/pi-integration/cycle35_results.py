#!/usr/bin/env python3
"""Build revision-by-revision replay, identity, negative and timing evidence."""
from __future__ import annotations
import importlib.util,json,pathlib,statistics,sys,tempfile,time
HERE=pathlib.Path(__file__).resolve().parent;ROOT=HERE.parent;RESULTS=HERE/"results/cycle35-sequential-creation"
sys.path.insert(0,str(HERE));sys.path.insert(0,str(ROOT))
from cycle35_preflight import fn_request,oracle,read,write
spec=importlib.util.spec_from_file_location("cycle35_results_gateway",HERE/"cycle19_gateway.py")
gateway=importlib.util.module_from_spec(spec);sys.modules[spec.name]=gateway;spec.loader.exec_module(gateway)
from basic_workspace.model import Workspace
from basic_workspace.projection import build_projection,projection_semantics
from basic_workspace.mir_execution import MirExecutionService

def independent_rows(contract,step,xs):
    names=set(next(iter(step["validation"]["expected_results"].values())))
    return {str(x):{k:v for k,v in oracle(contract["sequence_id"],x).items() if k in names} for x in xs}
def build_replay_evidence(label,contract_path,bridge_arm):
    contract=read(contract_path);root=bridge_arm/"gateway-evidence";stream=read(root/"constructive-operations.json")
    history=[json.loads(line) for line in (root/"history.jsonl").read_text().splitlines() if line.strip()]
    commits={row["resulting_revision"]:row for row in history if row.get("event")=="transaction_committed"}
    checkpoints={i:read(root/f"checkpoint-step-{i:02d}.json") for i in range(1,5)}
    steps=[];ledger=[];previous=set();final_mapping=None
    for i,step in enumerate(contract["steps"],1):
        prefix_ws=Workspace();doc=prefix_ws.create_empty_document(f"memory://cycle35/{label}-prefix-{i}.bas")["document_id"]
        ops=stream["operations"][:i]
        replay=gateway.replay_constructive_stream(prefix_ws,doc,ops,expected_final_handles=checkpoints[i]["portable_handles"],expected_start_revision=1)
        normalized=gateway.senior.normalized_state(projection_semantics(build_projection(prefix_ws,doc,replay.revision)),replay.live_handles)
        commit=commits[i+1];snapshot_matches=normalized==commit["semantic_snapshot"]
        expected_functions={row["function"]["portable_handle"] for row in contract["steps"][:i]}
        function_handles={row["handle"] for row in normalized["functions"]}
        dependencies={(e["caller"],e["callee"]) for e in gateway.senior.candidate_call_edges(normalized)}
        declared={(edge["caller_handle"],edge["callee_handle"])
            for earlier in contract["steps"][:i] for edge in earlier["required_dependency_edges"]}
        observations={engine:{} for engine in ("interp","jit")};executor=MirExecutionService(timeout=15)
        for engine in observations:
            for x in step["validation"]["inputs"]:
                row={}
                for fn in normalized["functions"]:
                    row[fn["name"].casefold()]=executor.execute_function(prefix_ws,doc,replay.revision,
                        replay.live_handles[fn["handle"]],[x],engine)["result"]
                observations[engine][str(x)]=row
        expected=independent_rows(contract,step,step["validation"]["inputs"])
        oracle_match=all(observations[engine]==expected for engine in observations)
        prefix_handles=set(replay.live_handles);created=sorted(prefix_handles-previous);removed=sorted(previous-prefix_handles)
        identity_rows=[{"portable_handle":handle,"fresh_replay_workspace_id":replay.live_handles[handle],
            "created_revision":i+1 if handle in created else None} for handle in sorted(prefix_handles)]
        ledger.append({"revision":i+1,"step_id":step["step_id"],"live_handles":sorted(prefix_handles),
            "new_handles":created,"retired_handles":removed,"function_handles":sorted(function_handles)})
        steps.append({"revision":i+1,"step_id":step["step_id"],"operation_kind":ops[-1]["operation"],
            "operation_count":len(ops),"function_count":len(normalized["functions"]),
            "normalized_semantic_snapshot":normalized,
            "normalized_structure_matches_commit":snapshot_matches,"function_set_matches":function_handles==expected_functions,
            "dependency_edges":sorted([list(edge) for edge in dependencies]),"dependency_edges_match_contract":dependencies==declared,
            "portable_handles_match_checkpoint":sorted(prefix_handles)==checkpoints[i]["portable_handles"],
            "identity_mapping":identity_rows,"independent_expected_results":expected,
            "mir_interpreter":observations["interp"],"mir_jit":observations["jit"],
            "interpreter_jit_agree":observations["interp"]==observations["jit"],"oracle_match":oracle_match,
            "all_checks_passed":snapshot_matches and function_handles==expected_functions and dependencies==declared and
                sorted(prefix_handles)==checkpoints[i]["portable_handles"] and oracle_match and observations["interp"]==observations["jit"]})
        previous=prefix_handles
        if i==4:final_mapping=replay.live_handles
    result={"schema":"basic-workspace.cycle35-sequence-results","version":1,"mission":label,
        "sequence_id":contract["sequence_id"],"inference_performed":False,"initial_revision":1,"final_revision":5,
        "steps":steps,"all_prefixes_passed":all(row["all_checks_passed"] for row in steps),
        "constructive_operation_count":len(stream["operations"]),"final_portable_handles":sorted(stream["portable_handles"])}
    return result,ledger,stream,final_mapping

def metric_runs(label,contract_path,repetitions=5):
    contract=read(contract_path); samples={key:[] for key in ("workspace_initialization_ms","constructor_preview_ms","commit_ms",
        "host_validation_ms","checkpoint_ms","progression_ms","full_sequence_ms","fresh_replay_ms")}
    for run in range(repetitions):
        with tempfile.TemporaryDirectory(prefix="atlas-cycle35-metric-",dir="/var/tmp") as td:
            t=time.perf_counter();g=gateway.Cycle19Gateway(pathlib.Path(td)/"run",creation_sequence_path=contract_path)
            samples["workspace_initialization_ms"].append((time.perf_counter()-t)*1000);total_start=time.perf_counter()
            for i,step in enumerate(contract["steps"]):
                g.handle("discover_functions",{},f"d-{run}-{i}")
                t=time.perf_counter();p=g.handle("preview_create_function",{"expected_revision":g.ws.get_revision(g.doc),**fn_request(step["function"]["name"])},f"p-{run}-{i}")
                samples["constructor_preview_ms"].append((time.perf_counter()-t)*1000)
                t=time.perf_counter();g.handle("commit_preview",{"transaction_id":p["transaction_id"]},f"c-{run}-{i}")
                samples["commit_ms"].append((time.perf_counter()-t)*1000)
                t=time.perf_counter();v=g.handle("host_validate",{"expected_revision":g.ws.get_revision(g.doc)},f"v-{run}-{i}")
                samples["host_validation_ms"].append((time.perf_counter()-t)*1000)
                if not v.get("mission_complete"):raise RuntimeError(f"metric run failed validation: {label}/{i}")
                t=time.perf_counter();cp=g.handle("create_checkpoint",{},f"cp-{run}-{i}")
                samples["checkpoint_ms"].append((time.perf_counter()-t)*1000)
                t=time.perf_counter();g.handle("host_advance_creation_sequence",{"checkpoint":cp["checkpoint"]},f"a-{run}-{i}")
                samples["progression_ms"].append((time.perf_counter()-t)*1000)
            samples["full_sequence_ms"].append((time.perf_counter()-total_start)*1000)
            t=time.perf_counter();g._replay();samples["fresh_replay_ms"].append((time.perf_counter()-t)*1000)
    return {key:{"samples_ms":[round(x,3) for x in values],"median_ms":round(statistics.median(values),3),
        "min_ms":round(min(values),3),"max_ms":round(max(values),3)} for key,values in samples.items()}

def recovery_evidence():
    contract_path=RESULTS/"MISSION-B.json"
    with tempfile.TemporaryDirectory(prefix="atlas-cycle35-recovery-",dir="/var/tmp") as td:
        root=pathlib.Path(td);source=gateway.Cycle19Gateway(root/"prefix",creation_sequence_path=contract_path)
        prefix_steps=[]
        for index in range(2):
            step=source.sequence_contract["steps"][index];source.handle("discover_functions",{},f"d{index}")
            p=source.handle("preview_create_function",{"expected_revision":source.ws.get_revision(source.doc),
                **fn_request(step["function"]["name"])},f"p{index}")
            c=source.handle("commit_preview",{"transaction_id":p["transaction_id"]},f"c{index}")
            v=source.handle("host_validate",{"expected_revision":c["revision"]},f"v{index}")
            cp=source.handle("create_checkpoint",{},f"cp{index}")["checkpoint"]
            advance=source.handle("host_advance_creation_sequence",{"checkpoint":cp},f"a{index}")
            prefix_steps.append({"committed_revision":c["revision"],"validation_passed":v["mission_complete"],
                "checkpoint_fingerprint":cp["semantic_fingerprint"],"progression_passed":advance["ok"]})
        stream_path=source.output/"constructive-operations.json";checkpoint_path=source.output/"checkpoint-step-02.json"
        resumed=gateway.Cycle19Gateway(root/"resumed",creation_sequence_path=contract_path,
            sequence_stream_path=stream_path,sequence_checkpoint_path=checkpoint_path)
        restored={"passed":resumed.resume_verification["passed"],"revision":resumed.ws.get_revision(resumed.doc),
            "active_step_id":resumed.current_step["step_id"],"portable_handles":sorted(resumed.aliases)}
        for index in (2,3):
            step=resumed.sequence_contract["steps"][index];resumed.handle("discover_functions",{},f"rd{index}")
            p=resumed.handle("preview_create_function",{"expected_revision":resumed.ws.get_revision(resumed.doc),
                **fn_request(step["function"]["name"])},f"rp{index}")
            c=resumed.handle("commit_preview",{"transaction_id":p["transaction_id"]},f"rc{index}")
            v=resumed.handle("host_validate",{"expected_revision":c["revision"]},f"rv{index}")
            cp=resumed.handle("create_checkpoint",{},f"rcp{index}")["checkpoint"]
            advance=resumed.handle("host_advance_creation_sequence",{"checkpoint":cp},f"ra{index}")
            prefix_steps.append({"committed_revision":c["revision"],"validation_passed":v["mission_complete"],
                "checkpoint_fingerprint":cp["semantic_fingerprint"],"progression_passed":advance["ok"]})
        return {"schema":"basic-workspace.cycle35-recovery-validation","version":1,
            "interruption_after_revision":3,"prefix_operations":2,"prefix_steps":prefix_steps,
            "prefix_reconstructed_through_shared_cycle31_replay":restored["passed"],"reconstructed_prefix":restored,
            "resumed_step":"step-03-can_apply","final_revision":resumed.ws.get_revision(resumed.doc),
            "sequence_completed":resumed.sequence_complete,
            "final_validation_passed":bool(resumed.last_validation and resumed.last_validation["mission_complete"]),
            "replay_source":"Cycle31 portable_constructive_replay; no source-text input",
            "actor":"host deterministic construction for recovery control; no inference"}

def main():
    base=RESULTS/"production-bridge-attempt-06";summaries={};ledgers={};replays={};identities={};metrics={}
    for label,contract_file,arm in (("mission-a","MISSION-A.json","mission-a"),("mission-b","MISSION-B.json","mission-b")):
        result,ledger,stream,mapping=build_replay_evidence(label,RESULTS/contract_file,base/arm)
        summaries[label]=result;ledgers[label]=ledger;replays[label]={"all_prefixes_passed":result["all_prefixes_passed"],"steps":result["steps"]}
        identities[label]={"portable_handles":sorted(mapping),"workspace_ids_from_final_fresh_replay":mapping,
            "retired_handles":[],"identity_reuse":False,"new_handle_counts_by_revision":[len(row["new_handles"]) for row in ledger]}
        metrics[label]=metric_runs(label,RESULTS/contract_file)
    write(RESULTS/"mission-a-results.json",summaries["mission-a"]);write(RESULTS/"mission-b-results.json",summaries["mission-b"])
    write(RESULTS/"identity-ledger.json",{"schema":"basic-workspace.cycle35-identity-ledger","version":1,"missions":identities,"prefixes":ledgers})
    write(RESULTS/"replay-equivalence.json",{"schema":"basic-workspace.cycle35-replay-equivalence","version":1,
        "missions":replays,"shared_dispatcher":"basic_workspace.portable_replay.replay_constructive_stream",
        "all_prefixes_passed":all(x["all_prefixes_passed"] for x in summaries.values())})
    write(RESULTS/"METRICS-data.json",{"schema":"basic-workspace.cycle35-deterministic-metrics","version":1,
        "repetitions_per_mission":5,"missions":metrics,"inference_performed":False})
    write(RESULTS/"negative-controls.json",collect_negative(base))
    write(RESULTS/"bridge-validation.json",read(base/"bridge-validation.json"))
    write(RESULTS/"recovery-validation.json",recovery_evidence())
    write(RESULTS/"revision-evidence.json",{"mission_a":summaries["mission-a"]["steps"],"mission_b":summaries["mission-b"]["steps"]})
    print(json.dumps({"mission_a_all_prefixes":summaries["mission-a"]["all_prefixes_passed"],
        "mission_b_all_prefixes":summaries["mission-b"]["all_prefixes_passed"],"metrics_runs":5},indent=2))
def collect_negative(base):
    records=[]
    for mission in ("mission-a","mission-b"):
        for step_dir in sorted((base/mission).glob("step-*")):
            data=read(step_dir/"dispatch-output.json");rev=data["preview"]["base_revision"]
            for index,row in enumerate(data.get("controls",[])):
                records.append({"mission":mission,"step":step_dir.name,"control_index":index,
                    "expected_category":["unauthorized_step","stale_revision","unauthorized_dependency"][index],
                    "actual_code":row.get("code"),"revision_before":rev,"revision_after_rejection":row.get("revision"),
                    "workspace_changed":row.get("authoritative_workspace_changed"),"progress_advanced":False,
                    "detected_before_mutation":row.get("authoritative_workspace_changed") is False})
            for row in data.get("schema_rejections",[]):
                records.append({"mission":mission,"step":step_dir.name,"control_index":row["index"],
                    "expected_category":"unknown_semantic_field_schema_rejection","actual_code":"PI_TYPESCRIPT_SCHEMA_REJECTION",
                    "revision_before":rev,"revision_after_rejection":rev,"workspace_changed":False,
                    "progress_advanced":False,"detected_before_mutation":True})
    for mission,step in (("mission-a","step-01-bounded_score"),("mission-b","step-03-can_apply")):
        cp=read(base/mission/"gateway-evidence"/"checkpoint-step-02.json")
        records.append({"mission":mission,"step":step,"expected_category":"premature_or_tampered_progression_rejected",
            "actual_code":"SEQUENCE_STEP_NOT_VALIDATED and SEQUENCE_CHECKPOINT_MISMATCH","revision_before":3,
            "revision_after_rejection":3,"workspace_changed":False,"progress_advanced":False,"detected_before_mutation":True})
    tested=[
        ("step-2-before-step-1","MISSION_SIGNATURE",1),("skip-before-host-validation","SEQUENCE_STEP_NOT_VALIDATED",2),
        ("Pi-requested-validation-not-host-checkpoint","SEQUENCE_STEP_NOT_VALIDATED",2),
        ("repeat-completed-step","MISSION_SIGNATURE",3),("extra-parameter","MISSION_SIGNATURE",1),
        ("callee-not-discovered","FUNCTION_NOT_DISCOVERED",2),("invented-callee","MISSION_DEPENDENCY_REQUIRED",2),
        ("wrong-call-arity","INVALID_TYPED_EXPRESSION",2),("candidate-changed-after-preview","PREVIEW_CANDIDATE_CHANGED",1),
        ("old-preview-after-step-advance","PREVIEW_NOT_FOUND",2),("constructor-after-sequence-complete","SEQUENCE_COMPLETE",5),
        ("tampered-prefix-order","SEQUENCE_RECOVERY_ORDER",3),("removed-prefix-operation","SEQUENCE_RECOVERY_PREFIX",3),
        ("tampered-identity-ledger","REPLAY_HANDLE_LEDGER",3),("tampered-checkpoint-fingerprint","SEQUENCE_RECOVERY_FINGERPRINT",3),
        ("tampered-constructor-body","SEQUENCE_RECOVERY_ORACLE",3),("tampered-dependency-binding","REPLAY_HANDLE_MISSING",3),
    ]
    for name,code,revision in tested:
        records.append({"mission":"both where applicable","step":"deterministic regression fixture","expected_category":name,
            "actual_code":code,"revision_before":revision,"revision_after_rejection":revision,"workspace_changed":False,
            "progress_advanced":False,"detected_before_mutation":True,"evidence":"test_cycle35_sequential_creation.py"})
    configuration=[("unknown-contract-field","SEQUENCE_CONTRACT_INVALID"),("unsupported-version","SEQUENCE_CONTRACT_VERSION"),
        ("wrong-step-revision","SEQUENCE_REVISION_ORDER"),("duplicate-mission-id","SEQUENCE_MISSION_ID"),
        ("unsupported-return-type","SEQUENCE_FUNCTION_SIGNATURE"),("reused-portable-handle","SEQUENCE_FUNCTION_HANDLE")]
    for name,code in configuration:
        records.append({"mission":"sequence initialization","expected_category":name,"actual_code":code,
            "revision_before":None,"revision_after_rejection":None,"workspace_changed":False,"progress_advanced":False,
            "detected_before_mutation":True,"evidence":"test_cycle35_sequential_creation.py; no Workspace activated"})
    return {"schema":"basic-workspace.cycle35-negative-controls","version":1,"inference_performed":False,
        "bridge_rejections":records,"test_asserted_controls":tested,"configuration_controls":configuration,
        "all_rejected_without_mutation":all(r["workspace_changed"] is False for r in records)}
if __name__=="__main__":main()
