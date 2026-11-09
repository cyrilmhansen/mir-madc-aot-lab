#!/usr/bin/env python3
"""Reproduce Cycle 31 shared replay and historical checkpoint verification."""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, sys, time
from pathlib import Path

BASIC=Path(__file__).resolve().parents[1]
PI=BASIC/"pi-integration"
RESULTS=PI/"results"
sys.path[:0]=[str(BASIC),str(PI)]
from basic_workspace.model import Workspace
from basic_workspace.model import WorkspaceError
from basic_workspace.portable_replay import replay_constructive_stream
from basic_workspace.projection import build_projection, projection_semantics
from basic_workspace.mir_execution import MirExecutionService
from cycle20_gateway import senior

DEFAULT_OUT=RESULTS/"cycle31-portable-replay"
SOURCE=RESULTS/"cycle30-post-extraction-maintenance/real-agent-01"
INPUTS=[-100,-1,0,1,19,20,21,24,25,26,39,40,44,45,49,50,51,60,100,200]

def read(path): return json.loads(path.read_text(encoding="utf-8"))
def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,sort_keys=True)+"\n",encoding="utf-8")
def fingerprint(value):
    body=json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()
    return hashlib.sha256(body).hexdigest()
def history(path): return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

def failure_controls(operations):
    cases=[]
    def check(name,items,expected=None,start=1):
        ws=Workspace();doc=ws.create_empty_document(f"memory://cycle31/control-{name}.bas")["document_id"]
        try:
            replay_constructive_stream(ws,doc,items,expected_start_revision=start)
            cases.append({"control":name,"rejected":False,"final_revision":ws.get_revision(doc),"code":None})
        except WorkspaceError as error:
            cases.append({"control":name,"rejected":True,"final_revision":ws.get_revision(doc),"code":error.code,
                "matches_expected_code":error.code==expected if expected else None})
    check("unknown-operation",[{"operation":"execute_arbitrary_code"}],"REPLAY_OPERATION_UNSUPPORTED")
    bad=__import__("copy").deepcopy(operations[:2]);bad[1]["arguments"]["body"][0]["condition"]["left"]["function_handle"]="invented.function"
    check("invented-renamed-handle",bad,"REPLAY_HANDLE_MISSING")
    bad=__import__("copy").deepcopy(operations);bad[-1]["edits"][0]["expected_value"]=999
    check("wrong-expected-literal",bad)
    bad=__import__("copy").deepcopy(operations);bad[-1]["edits"][0]["target"]["function_handle"]="missing.function"
    check("missing-portable-target",bad,"REPLAY_HANDLE_MISSING")
    bad=__import__("copy").deepcopy(operations);bad[-1]["edits"][0]["target"]["control_path"][0]["index"]=99
    check("stale-semantic-target",bad)
    bad=__import__("copy").deepcopy(operations);bad[-2]["expected_removed_statement_handles"]=["score_class.statement.2"]
    check("incorrect-retirement-set",bad,"REPLAY_RETIREMENT_MISMATCH")
    bad=__import__("copy").deepcopy(operations);bad[-2]["expected_block_fingerprint"]="0"*64
    check("tampered-block-fingerprint",bad,"REPLAY_BLOCK_MISMATCH")
    check("wrong-start-revision",operations,"REPLAY_START_REVISION",start=2)
    check("wrong-operation-order",[operations[1]],"REPLAY_HANDLE_MISSING")
    bad=__import__("copy").deepcopy(operations);bad[-2]["created_statement_handle"]="score_class.statement.0"
    check("retired-handle-reuse",bad,"REPLAY_IDENTITY_REUSE")
    bad=__import__("copy").deepcopy(operations);call=bad[1]["arguments"]["body"][0]["condition"]["left"];call["arguments"]=[]
    check("incompatible-call-signature",bad,"REPLAY_SIGNATURE_MISMATCH")
    after=__import__("copy").deepcopy(operations[-1]);after.update(operation="create_numeric_function",portable_handle="probe.function")
    after.pop("mission_id",None);after.pop("function_handle",None);after.pop("edits",None)
    after["arguments"]={"name":"PROBE","parameters":["X"],"body":[{"kind":"if","condition":{"kind":"binary","operator":"=","left":{"kind":"call","function_handle":"score_class.statement.0","arguments":[{"kind":"local_ref","name":"X"}]},"right":{"kind":"number","value":1}},"then":[{"kind":"assign","target":{"kind":"result"},"expression":{"kind":"number","value":1}}]}]}
    check("reference-after-retirement",operations+[after],"REPLAY_HANDLE_RETIRED")
    return {"schema":"basic-workspace.portable-replay-negative-controls","version":1,
        "controls":cases,"all_rejected":all(row["rejected"] for row in cases),
        "note":"Replay is sequential; final_revision records the last successfully replayed prefix before each rejected operation."}

def replay_prefix(operations,count):
    ws=Workspace();doc=ws.create_empty_document(f"memory://cycle31/checkpoint-{count}.bas")["document_id"]
    result=replay_constructive_stream(ws,doc,operations[:count],expected_start_revision=1)
    normalized=senior.normalized_state(projection_semantics(build_projection(ws,doc,result.revision)),result.live_handles)
    return result,normalized

def main():
    parser=argparse.ArgumentParser();parser.add_argument("--output",type=Path,default=DEFAULT_OUT);args=parser.parse_args()
    started=time.perf_counter();stream=read(SOURCE/"constructive-operations.json")
    ws=Workspace();doc=ws.create_empty_document("memory://cycle31/final.bas")["document_id"]
    replay=replay_constructive_stream(ws,doc,stream["operations"],expected_start_revision=1,
        expected_final_handles=stream["portable_handles"],expected_retired_handles=stream["retired_handles"])
    raw=projection_semantics(build_projection(ws,doc,replay.revision))
    normalized=senior.normalized_state(raw,replay.live_handles)
    prior_validation=read(SOURCE/"validation.json")
    previous_mapping=read(SOURCE/"full-replay-identity-mapping.json")["mappings"]
    previous_ids={row["portable_handle"]:row["committed_workspace_id"] for row in previous_mapping}
    identity=[{"portable_handle":handle,"committed_workspace_id":previous_ids.get(handle),
        "replay_workspace_id":workspace_id,"remapped":previous_ids.get(handle)!=workspace_id}
        for handle,workspace_id in sorted(replay.live_handles.items())]
    if any(row["committed_workspace_id"] is None for row in identity):
        raise RuntimeError("Historical identity evidence is missing a current portable handle")
    observed={"interp":{},"jit":{}};executor=MirExecutionService(timeout=20)
    for engine in observed:
        for x in INPUTS:
            row={}
            for handle,symbol_id in replay.live_handles.items():
                if handle.endswith(".function"):
                    name=ws.documents[doc].symbols[symbol_id].name.casefold()
                    row[name]=executor.execute_function(ws,doc,replay.revision,symbol_id,[x],engine)["result"]
            observed[engine][str(x)]=row
    if observed != prior_validation["observed_results"]:
        raise RuntimeError("Cycle 30 saved host observations do not match fresh shared replay")
    if observed["interp"] != observed["jit"]:
        raise RuntimeError("MIR interpreter and JIT observations differ")
    edges=senior.candidate_call_edges(normalized)
    if ws.documents[doc].symbols[replay.live_handles["clamp_score.function"]].name!="NORMALIZE_SCORE":
        raise RuntimeError("Historical function handle did not resolve to renamed source symbol")

    checkpoints=[]
    checkpoint_specs=[(9,8,"cycle26-rename-host-identity-and-behavior-validation"),
        (11,10,"cycle28-recorded-semantic-snapshot"),(12,11,"cycle29-recorded-semantic-snapshot"),
        (13,12,"cycle29-commit-and-host-behavior-identity-attestation"),(14,13,"cycle30-recorded-semantic-snapshot")]
    evidence_paths={
        9:RESULTS/"cycle26-semantic-rename/real-agent-01/mission-validation-host.json",
        11:RESULTS/"cycle28-conditional-refactor/real-agent-01/history.jsonl",
        12:RESULTS/"cycle29-function-extraction/real-agent-01/history.jsonl",
        13:RESULTS/"cycle29-function-extraction/real-agent-01/mission-b-host-validation.json",
        14:SOURCE/"history.jsonl"}
    for revision,count,kind in checkpoint_specs:
        point,norm=replay_prefix(stream["operations"],count)
        if point.revision!=revision: raise RuntimeError(f"Operation prefix at revision {revision} produced {point.revision}")
        path=evidence_paths[revision]
        if revision in (11,12,14):
            rows=history(path);row=next(row for row in rows if row.get("event")=="transaction_committed" and row.get("resulting_revision")==revision)
            if norm!=row["semantic_snapshot"]: raise RuntimeError(f"Historical revision {revision} semantic snapshot mismatch")
            status="structurally_verified"
        elif revision==9:
            validation=read(path)
            if validation.get("revision")!=9 or validation.get("mission_complete") is not True or validation.get("function_identity_preserved") is not True:
                raise RuntimeError("Revision 9 lacks its rename identity/behavior attestation")
            if not any(fn["name"]=="NORMALIZE_SCORE" for fn in norm["functions"]): raise RuntimeError("Revision 9 renamed spelling absent")
            status="narrow_historical_identity_and_behavior_attestation"
        else:
            validation=read(path)
            commits=history(RESULTS/"cycle29-function-extraction/real-agent-01/history.jsonl")
            commit=next(row for row in commits if row.get("event")=="transaction_committed" and row.get("resulting_revision")==13)
            if validation.get("mission_complete") is not True or commit.get("retired_statement_handles")!=stream["retired_handles"]:
                raise RuntimeError("Revision 13 lacks matching block-retirement and host-validation evidence")
            status="narrow_commit-retirement-and-host-validation-attestation"
        checkpoints.append({"revision":revision,"operation_prefix_length":count,"semantic_fingerprint":fingerprint(norm),
            "historical_evidence":str(path.relative_to(BASIC)),"verification_level":status})
    final_history=history(SOURCE/"history.jsonl")
    final_record=next(row["semantic_snapshot"] for row in final_history if row.get("event")=="transaction_committed" and row.get("resulting_revision")==14)
    if final_record!=normalized: raise RuntimeError("Final revision 14 snapshot mismatch")

    historical_ledger_document=read(SOURCE.parent/"identity-state-ledger.json")
    historical_ledger=historical_ledger_document["revisions"]
    live={};retired={};identity_states={}
    events_by_revision={}
    for event in replay.identity_events: events_by_revision.setdefault(event["revision"],[]).append(event)
    for revision in range(1,replay.revision+1):
        for event in events_by_revision.get(revision,[]):
            handle=event["portable_handle"]
            if event["event"]=="created":
                if handle in live or handle in retired: raise RuntimeError(f"Portable identity reuse at r{revision}: {handle}")
                live[handle]=event["workspace_id"]
            elif event["event"]=="retired":
                if handle not in live: raise RuntimeError(f"Retirement of non-live handle at r{revision}: {handle}")
                retired[handle]=live.pop(handle)
        if revision in {11,12,13,14}:
            expected=historical_ledger[str(revision)]
            expected_retired=[row["portable_handle"] for rev,ledger in historical_ledger.items() if int(rev)<=revision
                              for row in ledger["retired_at_revision"]]
            if sorted(live)!=sorted(expected["live_handles"]) or sorted(retired)!=sorted(expected_retired):
                raise RuntimeError(f"Identity lifecycle differs from saved revision-{revision} ledger")
            identity_states[str(revision)]={"live_handles":sorted(live),"live_count":len(live),
                "retired_handles":sorted(retired),"created_at_revision":[e["portable_handle"] for e in events_by_revision.get(revision,[]) if e["event"]=="created"],
                "retired_at_revision":[e["portable_handle"] for e in events_by_revision.get(revision,[]) if e["event"]=="retired"],
                "matches_historical_handle_state":True}

    write(args.output/"replay-evidence.json",replay.evidence())
    write(args.output/"identity-remapping.json",{"schema":"basic-workspace.portable-identity-remapping","version":1,
        "count":len(identity),"all_remapped":all(row["remapped"] for row in identity),"mappings":identity})
    write(args.output/"revision-checkpoints.json",{"schema":"basic-workspace.replay-checkpoints","version":1,"checkpoints":checkpoints})
    write(args.output/"identity-state-ledger.json",{"schema":"basic-workspace.replayed-identity-lifecycle","version":1,
        "source_historical_ledger":str((SOURCE.parent/"identity-state-ledger.json").relative_to(BASIC)),
        "portable_handle_states":identity_states,"final_live_count":len(live),"final_retired_handles":sorted(retired),
        "replay_local_workspace_ids_are_transient":True})
    write(args.output/"equivalence.json",{"schema":"basic-workspace.cycle31-replay-equivalence","version":1,
        "source_stream":str((SOURCE/"constructive-operations.json").relative_to(BASIC)),"revision":replay.revision,
        "operation_count":len(replay.operation_events),"function_count":len(ws.documents[doc].functions),
        "live_portable_handles":len(replay.live_handles),"retired_portable_handles":sorted(replay.retired_handles),
        "current_renamed_function":{"portable_handle":"clamp_score.function","source_name":"NORMALIZE_SCORE"},
        "normalized_structure_matches_revision14":normalized==final_record,
        "binding_edges":edges,"behavior_matches_cycle30_host_validation":observed==prior_validation["observed_results"],
        "interpreter_jit_agree":observed["interp"]==observed["jit"],"observed_inputs":INPUTS,
        "history_is_sequential_per_operation":True,"whole_stream_atomicity_claimed":False,
        "elapsed_replay_and_verification_ms":round((time.perf_counter()-started)*1000,3),"passed":True})
    write(args.output/"observations.json",{"schema":"basic-workspace.cycle31-mir-observations","version":1,
        "revision":replay.revision,"expectation_source":"Cycle 30 independent host validation, exact output comparison",
        "inputs":INPUTS,"observed_results":observed})
    controls=failure_controls(stream["operations"])
    if not controls["all_rejected"]: raise RuntimeError("A negative replay control was unexpectedly accepted")
    write(args.output/"negative-controls.json",controls)
    tampered=__import__("copy").deepcopy(stream["operations"]);tampered[-1]["edits"][0]["replacement_value"]=26
    tw=Workspace();tdoc=tw.create_empty_document("memory://cycle31/tampered-history.bas")["document_id"]
    tr=replay_constructive_stream(tw,tdoc,tampered,expected_start_revision=1)
    tnorm=senior.normalized_state(projection_semantics(build_projection(tw,tdoc,tr.revision)),tr.live_handles)
    attestation_rejected=tnorm!=final_record
    if not attestation_rejected: raise RuntimeError("Tampered operation unexpectedly matches historical revision-14 snapshot")
    write(args.output/"historical-tamper-control.json",{"control":"Cycle 30 final replacement value changed from 25 to 26",
        "portable_replay_completed":True,"replay_revision":tr.revision,"historical_attestation_passed":False,
        "classification":"REPLAY_SUCCEEDED_BUT_HISTORICAL_ATTESTATION_REJECTED",
        "basis":"Normalized replay state differs from the preserved revision-14 semantic snapshot",
        "authoritative_source_evidence_modified":False})
    print(json.dumps({"passed":True,"revision":replay.revision,"operations":len(replay.operation_events),
        "live_handles":len(replay.live_handles),"retired_handles":len(replay.retired_handles),
        "elapsed_ms":round((time.perf_counter()-started)*1000,3)},sort_keys=True))

if __name__=="__main__":main()
