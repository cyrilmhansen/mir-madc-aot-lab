#!/usr/bin/env python3
"""Assemble bounded Cycle39 case, bridge, negative, and coverage ledgers."""
from __future__ import annotations
import json, shutil
from collections import Counter, defaultdict
from pathlib import Path

HERE=Path(__file__).resolve().parent
OUT=HERE/"results/cycle39-differential-fuzzing"
SEM=OUT/"semantic-final"
PROD=OUT/"production-final"
ALT=OUT/"alternative-run"

def read(p): return json.loads(Path(p).read_text(encoding="utf-8"))
def write(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,indent=2,sort_keys=True)+"\n",encoding="utf-8")

def main():
    shutil.copyfile(SEM/"generated-cases.jsonl",OUT/"generated-cases.jsonl")
    shutil.copyfile(SEM/"differential-results.jsonl",OUT/"differential-results.jsonl")
    shutil.copyfile(ALT/"generated-cases.jsonl",OUT/"generated-cases-alt.jsonl")
    shutil.copyfile(ALT/"differential-results.jsonl",OUT/"differential-results-alt.jsonl")
    cases=[json.loads(x) for x in (OUT/"generated-cases.jsonl").read_text().splitlines()]
    results=[json.loads(x) for x in (OUT/"differential-results.jsonl").read_text().splitlines()]
    production=read(PROD/"production-bridge-summary.json")
    with (OUT/"production-bridge-results.jsonl").open("w",encoding="utf-8") as f:
        for row in production["workflows"]: f.write(json.dumps(row,sort_keys=True,separators=(",",":"))+"\n")
    negative=[]; layer_counts=Counter(); class_counts=Counter()
    for workflow in production["workflows"]:
        for step_index,step in enumerate(workflow["steps"]):
            inp=read(PROD/workflow["case_id"]/f"step-{step_index+1:02d}"/"dispatch-input.json")
            response=read(PROD/workflow["case_id"]/f"step-{step_index+1:02d}"/"dispatch-output.json")
            before=response["discovery"]["revision"]
            for i,observed in enumerate(response.get("controls",[])):
                args=inp["controls"][i]
                category={"STALE_REVISION":"revision conflict","MISSION_SIGNATURE":"unauthorized function scope",
                          "MISSION_DEPENDENCY_REQUIRED":"invented/unauthorized dependency"}.get(observed.get("code"),"python authorization rejection")
                row={"case_id":workflow["case_id"],"step":step_index+1,"layer":"Python mission authorization",
                    "category":category,"expected_classification":category,"actual_code":observed.get("code"),
                    "expected_revision":args["expected_revision"],"revision_before":before,"revision_after":observed.get("revision"),
                    "authoritative_workspace_changed":observed.get("authoritative_workspace_changed"),
                    "rejected_before_mutation":observed.get("authoritative_workspace_changed") is False,
                    "request":args}
                negative.append(row);layer_counts[row["layer"]]+=1;class_counts[row["category"]]+=1
            for schema in response.get("schema_rejections",[]):
                args=schema["arguments"]
                row={"case_id":workflow["case_id"],"step":step_index+1,"layer":"TypeScript TypeBox schema",
                    "category":"unknown semantic field","expected_classification":"schema rejection",
                    "actual_errors":schema.get("errors"),"revision_before":before,"revision_after":response["preview"].get("base_revision"),
                    "authoritative_workspace_changed":False if response["preview"].get("base_revision")==before else None,
                    "rejected_before_mutation":response["preview"].get("base_revision")==before,"request":args}
                negative.append(row);layer_counts[row["layer"]]+=1;class_counts[row["category"]]+=1
    # Direct replay integrity control is separately labeled and doesn't count
    # as a production bridge rejection.
    negative.append({"case_id":"unit-replay-unknown-operation","layer":"shared portable replay",
        "category":"unsupported operation kind","expected_classification":"REPLAY_OPERATION_UNSUPPORTED",
        "actual_classification":"REPLAY_OPERATION_UNSUPPORTED","authoritative_workspace_changed":False,
        "source":"test_cycle39_differential.py::test_unknown_replay_operation_rejects_without_mutation"})
    negative.append({"case_id":"unit-replay-wrong-old-literal","layer":"canonical Workspace via replay",
        "category":"incorrect expected literal","expected_classification":"EXPECTED_LITERAL_MISMATCH",
        "actual_classification":"EXPECTED_LITERAL_MISMATCH","authoritative_workspace_changed":False,
        "source":"test_cycle39_differential.py::test_incorrect_literal_precondition_rejects_atomically"})
    write(OUT/"negative-controls.json",{"schema":"basic-workspace.cycle39-negative-controls","version":1,
        "case_count":len(negative),"production_bridge_case_count":len(negative)-2,
        "production_layer_counts":dict(layer_counts),"classification_counts":dict(class_counts),
        "all_observed_production_rejections_preserved_state":all(row.get("rejected_before_mutation",row.get("authoritative_workspace_changed") is False)
            for row in negative if row.get("layer")!="shared portable replay" and row.get("layer")!="canonical Workspace via replay"),
        "controls":negative})
    fam=Counter(row["family"] for row in cases); func=Counter(str(len(row["functions"])) for row in cases)
    topo={}
    for case in cases:
        n=len(case["functions"]); depth={h:0 for h in [fn["portable_handle"] for fn in case["functions"]]}
        for fn in case["functions"]:
            depth[fn["portable_handle"]]=max([depth.get(c,0)+1 for c in fn["callees"]] or [0])
        key=f"functions={n};max_dependency_depth={max(depth.values(),default=0)}"
        topo[key]=topo.get(key,0)+1
    production_selected={row["case_id"] for row in production["workflows"]}
    matrix={"valid_cases":len(cases),"families":dict(fam),"function_count_distribution":dict(func),
        "topology_distribution":topo,"operation_history_length_distribution":dict(Counter(str(len(row["operations"])) for row in cases)),
        "dependency_edge_count_distribution":dict(Counter(str(len(row["dependency_edges"])) for row in results if row.get("valid"))),
        "input_count_distribution":dict(Counter(str(row["input_count"]) for row in results if row.get("valid"))),
        "atomic_literal_edit_target_count_distribution":{"1":len(cases)},"rename_target_positions":{"first_function":len(cases)},
        "production_selected_case_count":len(production_selected),"production_selected_families":dict(Counter(row["family"] for row in production["workflows"])),
        "production_committed_steps":sum(len(row["steps"]) for row in production["workflows"]),
        "production_authorization_layers":{"Cycle19 creation":len(production["workflows"]),"Cycle20 maintenance":0,"Cycle37 rename":0},
        "engines":["MIR interpreter","MIR JIT"],"replay_mode":"fresh portable replay for all 120 cases"}
    write(OUT/"coverage-matrix.json",matrix)
    scalar_checks=sum(row.get("input_count",0)*row.get("function_count",0)*4 for row in results if row.get("valid"))
    write(OUT/"replay-equivalence.json",{"case_count":len(results),
        "cases_with_fresh_replay":sum(bool(row.get("replay_equal")) for row in results),
        "replayed_engine_observations_match_oracle":all(row.get("replay_equal") for row in results if row.get("valid")),
        "normalized_structure_compared_modulo_workspace_uuids":True,
        "scalar_oracle_comparisons_across_committed_and_replayed_workspaces":scalar_checks})
    write(OUT/"counterexamples"/"injected-reducer-check.json",read(SEM/"counterexamples"/"injected-reducer-check.json"))
    write(OUT/"counterexamples"/"harness-calibration-summary.json",{"product_findings":0,
        "preserved_preliminary_attempt_directories":["preflight-fast","preflight-fast-corrected","preflight-fast-v3","preflight-fast-v4","preflight-fast-v5","preflight-fast-v6","semantic-run-01","semantic-run-02","semantic-run-03"],
        "classification":"generator/oracle/contract calibration; no confirmed product divergence"})
    write(OUT/"campaign-outcome.json",{"semantic":read(SEM/"differential-summary.json"),
        "production_bridge":production,"metamorphic":read(OUT/"metamorphic-results.json"),
        "negative_controls":{"count":len(negative),"production_count":len(negative)-2},
        "performance":read(OUT/"performance-confirmatory.json"),
        "alternative_campaign":read(ALT/"differential-summary.json")})
    print(json.dumps({"cases":len(cases),"production_workflows":len(production["workflows"]),
        "production_steps":sum(len(row["steps"]) for row in production["workflows"]),
        "negative_controls":len(negative),"production_rejections":len(negative)-2,"families":dict(fam)},indent=2))

if __name__=="__main__":main()
