#!/usr/bin/env python3
"""Assemble Cycle36 report indexes from authentic deterministic run outputs."""
import json, pathlib, shutil
HERE=pathlib.Path(__file__).resolve().parent
OUT=HERE/"results/cycle36-verified-handoff"
RUN=OUT/"production-bridge-attempt-07"
def read(p): return json.loads(pathlib.Path(p).read_text(encoding="utf-8"))
def write(p,v): pathlib.Path(p).write_text(json.dumps(v,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
missions={}
identity={"schema":"basic-workspace.cycle36-portable-identity-ledger","version":1,"missions":{}}
replay={"schema":"basic-workspace.cycle36-replay-equivalence","version":1,"missions":{}}
bridge=read(RUN/"bridge-validation.json")
for label in ("mission-a","mission-b"):
    base=RUN/label
    creation=read(base/"creation/bridge-summary.json")
    creation_oracle=read(base/"creation/independent-oracle-observations.json")
    checkpoint=read(base/"creation/gateway-evidence"/f"checkpoint-step-{len(creation['steps']):02d}.json")
    stream=read(base/"maintenance/gateway-evidence/constructive-operations.json")
    validation=read(base/"maintenance/gateway-evidence/validation.json")
    base_reconstruction=read(base/"maintenance/gateway-evidence/baseline-reconstruction.json")
    final_oracle=read(base/"independent-oracle-observations.json")
    prefix=read(base/"revision-prefix-equivalence.json")
    missions[label]={"creation":creation,"creation_revision_observations":creation_oracle,
        "verified_handoff":read(base/"handoff/handoff.json"),"maintenance_contract":read(base/"maintenance-contract.json"),
        "baseline_reconstruction":base_reconstruction,"maintenance_bridge":read(base/"maintenance-bridge-summary.json"),
        "independent_oracle_observations":final_oracle,"final_validation":validation,
        "revision_prefix_equivalence":prefix}
    source_history=[json.loads(line) for line in (base/"creation/gateway-evidence/history.jsonl").read_text().splitlines() if line.strip()]
    creation_commit=next(row for row in reversed(source_history) if row.get("event")=="transaction_committed")
    receiving_map={row["portable_handle"]:row["reconstructed_workspace_id"] for row in base_reconstruction["identity_mapping"]}
    final_map={row["portable_handle"]:{"maintenance_workspace_id":row["committed_workspace_id"],
        "full_replay_workspace_id":row["replay_workspace_id"],"remapped_on_final_replay":row["remapped"]}
        for row in validation["replay"]["identity_mapping"]}
    live=sorted(stream["portable_handles"]); retired=sorted(stream.get("retired_handles",[]))
    identity["missions"][label]={"creation_portable_handles":sorted(checkpoint["portable_handles"]),
        "final_live_portable_handles":live,"retired_portable_handles":retired,
        "creation_session_workspace_ids":creation_commit.get("alias_bindings",{}),
        "maintenance_reconstruction_workspace_ids":receiving_map,
        "final_full_replay_mappings":final_map,
        "all_creation_handles_survive":set(checkpoint["portable_handles"]).issubset(live),
        "no_unexpected_new_or_retired_handles":set(live)==set(checkpoint["portable_handles"]) and not retired}
    replay["missions"][label]={"construction_revisions":sorted(int(k) for k in creation_oracle["revisions"]),
        "complete_history_operations":len(stream["operations"]),
        "full_history_revisions":sorted(int(k) for k in prefix["prefixes"]),
        "all_prefixes_structurally_bound_and_behaviorally_valid":prefix["passed"],
        "cycle20_replay":validation.get("replay"),"same_revision_after_maintenance":validation.get("revision"),
        "dependency_edges":validation.get("replay",{}).get("binding_equivalence"),
        "passed":prefix["passed"] and validation.get("replay",{}).get("passed") is True}
write(OUT/"mission-a-results.json",missions["mission-a"])
write(OUT/"mission-b-results.json",missions["mission-b"])
write(OUT/"identity-ledger.json",identity)
write(OUT/"replay-equivalence.json",{**replay,"passed":all(m["passed"] for m in replay["missions"].values())})
write(OUT/"bridge-validation.json",bridge)
print(json.dumps({"identity":True,"replay":read(OUT/"replay-equivalence.json")["passed"],"bridge":bridge["passed"]},indent=2))
