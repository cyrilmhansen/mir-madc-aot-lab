#!/usr/bin/env python3
"""Finalize Cycle37 host replay, identity and mission evidence from production bridge runs."""
from __future__ import annotations
import argparse, copy, json, pathlib, sys
HERE=pathlib.Path(__file__).resolve().parent; ROOT=HERE.parent
sys.path[:0]=[str(ROOT),str(HERE)]
from basic_workspace.model import Workspace
from basic_workspace.projection import build_projection, projection_semantics
from basic_workspace.portable_replay import replay_constructive_stream
from cycle20_gateway import senior, _call_edges
from cycle26_gateway import Cycle26Gateway
from verified_handoff import _fingerprint, verify_handoff

RESULTS=HERE/"results/cycle37-reusable-rename"
BRIDGE=RESULTS/"production-bridge-attempt-05"
PROFILE="basic-workspace.numeric-composition.v1"


def read(path):return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
def write(path,value):
    path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")


def finalize_mission(label):
    mission=BRIDGE/label
    seq=read(mission/"creation-sequence.json")
    evidence=mission/"creation"/"gateway-evidence"
    contract_path=mission/"rename-contract.json"
    handoff=mission/"handoff/handoff.json";anchor=mission/"handoff/host-trust-anchor.json"
    bridge_result=read(mission/"bridge-validation.json")
    rename_validation=read(mission/"rename/gateway-evidence/mission-validation-host.json")
    if not bridge_result["handoff_verified"] or not bridge_result["host_validation"] or not bridge_result["replay_passed"]:
        raise RuntimeError(f"{label}: the production bridge result is incomplete")
    contract=read(contract_path)
    proof=verify_handoff(handoff,anchor,evidence,contract_path)
    final_stream=read(mission/"rename/gateway-evidence/constructive-operations.json")
    if len(final_stream["operations"])!=len(seq["steps"])+1:
        raise RuntimeError(f"{label}: constructive stream does not contain all constructors and one rename")
    baseline_ops=final_stream["operations"][:-1]
    if baseline_ops!=read(evidence/"constructive-operations.json")["operations"]:
        raise RuntimeError(f"{label}: rename stream changed authentic constructors")
    if final_stream["operations"][-1]!={"operation":"rename_symbol","target_handle":contract["target_handle"],
            "expected_name":contract["expected_source_name"],"new_name":contract["new_source_name"]}:
        raise RuntimeError(f"{label}: final operation is not the host-authorized portable rename")
    prefix_rows={}
    base_handles=[row["function"]["portable_handle"] for row in seq["steps"]]
    for prefix in range(1,len(final_stream["operations"])+1):
        ws=Workspace();doc=ws.create_empty_document(f"memory://cycle37/{label}/prefix-{prefix}.bas")["document_id"]
        replay=replay_constructive_stream(ws,doc,final_stream["operations"][:prefix],expected_start_revision=1)
        norm=senior.normalized_state(projection_semantics(build_projection(ws,doc,replay.revision)),replay.live_handles)
        handles=sorted(replay.live_handles)
        checkpoint_match=None
        receipt_ref=None
        if prefix<=len(seq["steps"]):
            checkpoint=read(evidence/f"checkpoint-step-{prefix:02d}.json")
            checkpoint_match=_fingerprint(replay.revision,norm)==checkpoint["semantic_fingerprint"]
            if not checkpoint_match:
                raise RuntimeError(f"{label}: checkpoint mismatch at revision {replay.revision}")
            receipt=read(evidence/f"mission-{prefix+2}-validation-host.json")
            receipt_ref=f"Cycle35 authenticated host receipt, revision {replay.revision}"
            observations=receipt["observed_results"]
            expected=receipt["expected_results"]
        else:
            checkpoint_match=None
            receipt=rename_validation
            receipt_ref=f"Cycle37 production bridge host validation, revision {replay.revision}"
            observations=receipt["observed_results_by_portable_handle"]
            expected=receipt["expected_results_by_portable_handle"]
        if prefix==len(final_stream["operations"]):
            # The receiving gateway's independent final validation compares the
            # authorized candidate modulo the single source-name change.
            if rename_validation.get("normalized_structure_modulo_target_name") is not True:
                raise RuntimeError(f"{label}: final normalized semantic comparison failed")
        prefix_rows[str(replay.revision)]={
            "operation_prefix":prefix,"normalized_semantics":norm,
            "function_signatures":[{"handle":row["handle"],"name":row["name"],"parameters":row["parameters"],
                "return_type":row["return_type"]} for row in norm["functions"]],
            "dependency_edges":_call_edges(norm),"portable_handles":handles,"retired_handles":replay.retired_handles,
            "checkpoint_match":checkpoint_match,"validation_receipt":receipt_ref,
            "host_observations_available":bool(observations),"host_expected_results_available":bool(expected)}
    final_state=prefix_rows[str(len(final_stream["operations"])+1)]["normalized_semantics"]
    if sorted(final_stream["portable_handles"])!=sorted(prefix_rows[str(len(final_stream["operations"])+1)]["portable_handles"]):
        raise RuntimeError(f"{label}: final portable ledger differs from replay")
    root=RESULTS/label
    root.mkdir(parents=True,exist_ok=True)
    write(root/"MISSION.json",contract)
    write(root/"revision-snapshots.json",{"prefixes":prefix_rows,"final_revision":len(final_stream["operations"])+1,"passed":True})
    # Independently rerun host authorization, token/portable identity preservation,
    # MIR observations and full replay from the same authenticated handoff.
    recheck=root/"host-deterministic-recheck"
    gateway=Cycle26Gateway(recheck/"gateway",contract_path,verified_handoff_path=handoff,
        handoff_anchor_path=anchor,handoff_evidence_root=evidence)
    gateway.discover();preview=gateway._preview_rename({"expected_revision":contract["base_document_revision"],
        "function_handle":contract["target_handle"],"expected_name":contract["expected_source_name"],
        "new_name":contract["new_source_name"]},"cycle37-host-recheck-preview")
    if not preview.get("ok"):raise RuntimeError(f"{label}: host-only authorized preview failed")
    committed=gateway._commit_rename({"transaction_id":preview["transaction_id"]},"cycle37-host-recheck-commit")
    if committed.get("revision")!=contract["base_document_revision"]+1:raise RuntimeError(f"{label}: host-only commit failed")
    host=gateway.validate(committed["revision"],"cycle37-host-recheck-validation","host")
    if not host.get("mission_complete"):raise RuntimeError(f"{label}: host-only final validation failed")
    write(recheck/"host-validation.json",host)
    baseline_mapping=read(mission/"rename/gateway-evidence/baseline-reconstruction.json")["identity_mapping"]
    mapping={row["portable_handle"]:row for row in host["replay"]["identity_mapping"]}
    if set(mapping)!=set(final_stream["portable_handles"]):
        raise RuntimeError(f"{label}: replay identity mapping does not cover all live handles")
    write(root/"identity-ledger.json",{
        "baseline_revision":contract["base_document_revision"],"final_revision":committed["revision"],
        "live_handles_before":sorted(gateway.base_aliases),"live_handles_after":sorted(gateway.aliases),
        "retired_handles":[],"created_handles":[],"source_names_before":{row["handle"]:row["name"] for row in gateway.baseline["functions"]},
        "source_names_after":{row["handle"]:row["name"] for row in gateway._state()["functions"]},
        "baseline_maintenance_workspace_mapping":baseline_mapping,
        "maintenance_to_replay_mapping":[mapping[handle] for handle in sorted(mapping)],
        "all_portable_identities_preserved":host["all_portable_identities_preserved"],
        "function_parameter_statement_and_token_identity_sets_preserved":host["token_identity_set_preserved"],
        "dependency_identity_edges_unchanged":host["dependency_identity_edges_unchanged"]})
    write(root/"independent-oracle-observations.json",{
        "source":"Cycle35 host-owned final step oracle receipt, independently verified by Cycle36 handoff; fresh MIR checks after rename",
        "inputs":contract["validation_inputs"],"before_by_portable_handle":gateway.baseline_observed,
        "after_by_portable_handle":host["observed_results_by_portable_handle"],
        "interpreter_jit_agreement":host["interpreter_jit_agree"],"behavior_unchanged":host["behavior_unchanged"],
        "mission_complete":host["mission_complete"]})
    write(root/"replay-equivalence.json",{
        "construction_operations":len(baseline_ops),"rename_operations":1,"full_operation_count":len(final_stream["operations"]),
        "final_revision":committed["revision"],"portable_handle_count":len(final_stream["portable_handles"]),
        "fresh_replay_matches_authoritative_normalized_semantics":host["replay"]["structural_equivalence_modulo_rename"],
        "fresh_replay_matches_interpreter_and_jit":host["replay"]["behavioral_equivalence"],
        "remapped_identity_count":host["replay"]["identity_remappings"],"retired_handles":[],
        "revision_prefixes":prefix_rows,"passed":host["replay"]["passed"]})
    return {"contract":contract,"proof":proof,"bridge":bridge_result,"host":host,"prefixes":prefix_rows,
        "normalized":final_state,"final_revision":committed["revision"]}


def main():
    global BRIDGE
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bridge-dir",default="production-bridge-attempt-05",
        help="bridge output directory relative to the Cycle37 result directory")
    args=parser.parse_args()
    BRIDGE=(RESULTS/args.bridge_dir).resolve()
    a=finalize_mission("mission-a");b=finalize_mission("mission-b")
    bridge=read(BRIDGE/"bridge-validation.json")
    write(RESULTS/"bridge-validation.json",bridge)
    write(RESULTS/"replay-equivalence.json",{"mission-a":read(RESULTS/"mission-a/replay-equivalence.json"),
        "mission-b":read(RESULTS/"mission-b/replay-equivalence.json"),"passed":True})
    write(RESULTS/"identity-ledger.json",{"mission-a":read(RESULTS/"mission-a/identity-ledger.json"),
        "mission-b":read(RESULTS/"mission-b/identity-ledger.json")})
    write(RESULTS/"mission-a-results.json",{"contract":a["contract"],"handoff":a["proof"],"bridge":a["bridge"],
        "host_validation":a["host"],"prefixes":a["prefixes"]})
    write(RESULTS/"mission-b-results.json",{"contract":b["contract"],"handoff":b["proof"],"bridge":b["bridge"],
        "host_validation":b["host"],"prefixes":b["prefixes"]})
    print(json.dumps({"mission-a_revision":a["final_revision"],"mission-b_revision":b["final_revision"],"passed":True},indent=2))


if __name__=="__main__":main()
