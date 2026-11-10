#!/usr/bin/env python3
"""Generated Cycle19 -> verified Cycle37 rename -> Cycle20 production campaign.

This experiment adapter builds only contracts/specifications. All mutations are
performed by the existing TypeScript/JSONL production probes and gateways.
"""
from __future__ import annotations
import copy, json, pathlib, random, sys, time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path[:0] = [str(ROOT), str(HERE)]
import cycle36_preflight as c36
import cycle37_preflight as c37
import cycle38_preflight as c38
from basic_workspace.model import WorkspaceError
from cycle20_gateway import Cycle20Gateway
from basic_workspace.model import Workspace
from basic_workspace.portable_replay import replay_constructive_stream
from basic_workspace.projection import build_projection, projection_semantics
from verified_handoff import verify_handoff
from verified_rename_continuation import verify_rename_continuation
import shutil

OUT = HERE / "results/cycle40-generated-production-fuzzing"
PROFILE = c36.PROFILE
INPUTS: dict[str, list[int]] = {}
CURRENT: dict = {}


def write(path, value):
    path = pathlib.Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def generated_case(index: int, seed: int, rename_index: int = 0):
    rng = random.Random(seed)
    topology = ("single_edge", "shared_provider", "chain", "fanout_and_downstream")[(index - 1) % 4]
    count = {"single_edge": 2, "shared_provider": 3, "chain": 3, "fanout_and_downstream": 4}[topology]
    prefix = f"G40_{index:02d}"
    names = [f"{prefix}_PROVIDER"] + [f"{prefix}_PRED_{i}" for i in range(1, count)]
    handles = [f"g40_{index:02d}_provider.function"] + [f"g40_{index:02d}_pred_{i}.function" for i in range(1, count)]
    cap = rng.randint(70, 120); new_cap = cap - rng.randint(5, min(20, cap - 50))
    thresholds = [rng.randint(5, 65) for _ in range(count - 1)]
    new_threshold = thresholds[0] + rng.choice([-3, -2, 2, 3])
    if new_threshold <= 0: new_threshold = thresholds[0] + 4
    inputs = sorted(set([-20, -1, 0, 1, cap-1, cap, cap+1, new_cap-1, new_cap, new_cap+1]
                        + [v+d for v in thresholds + [new_threshold] for d in (-1, 0, 1)]
                        + [rng.randint(-25, 140) for _ in range(3)]))

    def n(v): return {"kind": "number", "value": v}
    def x(): return {"kind": "local_ref", "name": "X"}
    def call(h): return {"kind": "call", "function_handle": h, "arguments": [x()]}
    def assign(e): return {"kind": "assign", "target": {"kind": "result"}, "expression": e}
    def branch(op, left, right, value):
        return {"kind": "if", "condition": {"kind": "binary", "operator": op, "left": left, "right": right},
                "then": [assign(n(value))]}
    functions = [{"name": names[0], "portable_handle": handles[0], "parameters": ["X"],
        "body": [assign(x()), branch("<", x(), n(0), 0), branch(">", x(), n(cap), cap)],
        "rule": {"kind": "clamp", "lower": 0, "upper": cap, "upper_result": cap}, "callee_index": None}]
    # Four graph shapes, all topologically ordered and expressible by the
    # existing one-callee threshold_call oracle.
    callee_indices = [0] if topology == "single_edge" else (
        [0, 0] if topology == "shared_provider" else ([0, 1] if topology == "chain" else [0, 0, 1]))
    for j in range(1, count):
        ci = callee_indices[j-1]
        functions.append({"name": names[j], "portable_handle": handles[j], "parameters": ["X"],
            "body": [assign(n(0)), branch(">=", call(handles[ci]), n(thresholds[j-1]), 1)],
            "rule": {"kind": "threshold", "callee_index": ci, "threshold": thresholds[j-1]}, "callee_index": ci})
    edges = [{"caller_handle": f["portable_handle"], "callee_handle": handles[f["callee_index"]]}
             for f in functions if f["callee_index"] is not None]
    if not 0 <= rename_index < count: raise ValueError("rename target is outside generated function list")
    spec = {"case_id": f"g40-{index:02d}", "seed": seed, "topology": topology, "functions": functions,
            "initial_cap": cap, "final_cap": new_cap, "initial_thresholds": thresholds,
            "final_thresholds": [new_threshold] + thresholds[1:], "rename_target": handles[rename_index],
            "old_provider_name": names[rename_index], "new_provider_name": f"{names[rename_index]}_RENAMED",
            "edges": edges, "inputs": inputs, "new_threshold": new_threshold}
    return spec


def math_values(case, x_value, maintained=False):
    cap = case["final_cap"] if maintained else case["initial_cap"]
    thresholds = case["final_thresholds"] if maintained else case["initial_thresholds"]
    vals = [float(min(cap, max(0, x_value)))]
    for i, fn in enumerate(case["functions"][1:]):
        vals.append(float(int(vals[fn["callee_index"]] >= thresholds[i])))
    return {fn["portable_handle"]: vals[i] for i, fn in enumerate(case["functions"])}


def build_sequence(label, case):
    steps = []
    for i, fn in enumerate(case["functions"]):
        callees = [] if i == 0 else [case["functions"][fn["callee_index"]]["portable_handle"]]
        edges = [] if not callees else [{"caller_handle": fn["portable_handle"], "callee_handle": callees[0]}]
        expected = {str(xv): {row["name"].lower(): math_values(case, xv)[row["portable_handle"]]
                              for row in case["functions"][:i+1]} for xv in case["inputs"]}
        steps.append({"step_id": f"step-{i+1:02d}-{fn['name'].lower()}", "mission_id": f"cycle40.{label}.{i+1:02d}",
            "expected_base_revision": i+1, "function": {"name": fn["name"], "portable_handle": fn["portable_handle"],
                "parameters": ["X"], "return_type": "numeric"}, "required_callees": callees,
            "required_dependency_edges": edges, "required_existing_function_handles_unchanged": [r["portable_handle"] for r in case["functions"][:i]],
            "validation": {"inputs": case["inputs"], "expected_results": expected}})
    return {"schema": "basic-workspace.numeric-function-creation-sequence", "version": 1,
        "sequence_id": f"cycle40.{label}.creation.v1", "objective": f"Construct generated semantic program {label}.",
        "execution_profile_id": PROFILE, "starting_revision": 1, "maximum_steps": 8, "steps": steps}


def constructor_request(label, case, name):
    row = next(f for f in case["functions"] if f["name"] == name)
    return {"name": row["name"], "parameters": ["X"], "body": copy.deepcopy(row["body"])}


def oracle(label, x_value):
    return {row["name"].lower(): value for row, value in zip(CURRENT["functions"], math_values(CURRENT, x_value).values())}


def rename_contract(label, creation, out):
    case = CURRENT; functions = [f["portable_handle"] for f in case["functions"]]
    contract = {"schema": "basic-workspace.semantic-rename-contract", "version": 2,
        "mission_id": f"cycle40.{label}.rename.v2", "objective": f"Rename {case['old_provider_name']} while preserving identity and bindings.",
        "base_document_revision": creation["final_revision"], "execution_profile_id": PROFILE,
        "target_handle": case["rename_target"], "expected_source_name": case["old_provider_name"],
        "new_source_name": case["new_provider_name"], "unchanged_function_handles": [h for h in functions if h != case["rename_target"]],
        "unchanged_dependency_edges": True, "required_revision_increment": 1, "validation_inputs": case["inputs"]}
    path = pathlib.Path(out) / "rename-contract.json"; c37.write(path, contract); return path, contract


def edit_contract(label, creation, mission_dir):
    case = CURRENT
    stream, ws, doc, replay, baseline = c36._replay_source(creation["evidence"])
    provider = case["functions"][0]; pred = case["functions"][1]
    cap_h, pred_h = provider["portable_handle"], pred["portable_handle"]
    cmp_target = {"function_handle": cap_h, "control_path": [{"block": "body", "index": 2}], "expression_path": [1]}
    _f, _s, chosen = Cycle20Gateway._target_expression(baseline, cmp_target)
    if float(chosen["value"]) != case["initial_cap"]: raise RuntimeError("generated cap comparison target mismatch")
    value_targets=[]
    for handle in stream["portable_handles"]:
        if handle.startswith(cap_h.rsplit(".", 1)[0] + ".statement."):
            candidate={"function_handle":cap_h,"statement_handle":handle,"expression_path":[]}
            try:
                _f,_s,node=Cycle20Gateway._target_expression(baseline,candidate)
                if float(node["value"])==case["initial_cap"]: value_targets.append(candidate)
            except WorkspaceError: pass
    if len(value_targets)!=1: raise RuntimeError(f"expected one exact provider result literal, got {len(value_targets)}")
    threshold_target={"function_handle":pred_h,"control_path":[{"block":"body","index":1}],"expression_path":[1]}
    _f,_s,node=Cycle20Gateway._target_expression(baseline,threshold_target)
    if float(node["value"])!=case["initial_thresholds"][0]: raise RuntimeError("generated predicate threshold target mismatch")
    targets=[
        {"target":cmp_target,"expected_original_value":case["initial_cap"],"replacement_constraint":{"kind":"one_of","values":[case["final_cap"]]},"label":"provider upper comparison"},
        {"target":value_targets[0],"expected_original_value":case["initial_cap"],"replacement_constraint":{"kind":"one_of","values":[case["final_cap"]]},"label":"provider upper result"},
        {"target":threshold_target,"expected_original_value":case["initial_thresholds"][0],"replacement_constraint":{"kind":"one_of","values":[case["new_threshold"]]},"label":"dependent threshold"}]
    validations=[]
    for i, fn in enumerate(case["functions"]):
        if i==0: spec={"kind":"clamp","minimum":0,"maximum":case["final_cap"]}
        else:
            threshold=case["final_thresholds"][i-1]
            spec={"kind":"threshold_call","callee_handle":case["functions"][fn["callee_index"]]["portable_handle"],
                "threshold":threshold,"true_value":1,"false_value":0}
        validations.append({"function_handle":fn["portable_handle"],"result_key":fn["name"].lower(),"oracle":spec})
    contract={"schema":"basic-workspace.numeric-literal-maintenance-contract","version":2,"scope_mode":"per_target",
        "mission_id":f"cycle40.{label}.maintenance.v2","objective":"Atomically lower the provider cap and alter one dependent threshold.",
        "base_document_revision":creation["final_revision"]+1,"execution_profile_id":PROFILE,
        "allowed_function_handles":[cap_h,pred_h],"authorized_targets":targets,"minimum_edits":3,"maximum_edits":3,
        "unchanged_function_handles":[f["portable_handle"] for f in case["functions"] if f["portable_handle"] not in {cap_h,pred_h}],
        "required_dependency_edges":case["edges"],"revision_increment":1,
        "validation":{"inputs":case["inputs"],"functions":validations}}
    path=pathlib.Path(mission_dir)/"maintenance-contract.json"; c38.write(path,contract); return path,contract


def expected_by_handle(label, maintained, x_value):
    return math_values(CURRENT, x_value, maintained)


def maintenance_contract(label, creation, renamed, out):
    path, contract = edit_contract(label, creation, out)
    contract["base_document_revision"] = renamed["revision"]
    write(path, contract)
    return path, contract


def make_label(index): return f"workflow-{index:02d}"


def run_one(index, seed, out, rename_index=0):
    global CURRENT
    label=make_label(index); case=generated_case(index,seed,rename_index); CURRENT=case; INPUTS[label]=case["inputs"]
    c36.INPUTS[label]=case["inputs"]; c36.sequence_contract=lambda _label: build_sequence(label,case)
    c36.fn_request=lambda _label,name: constructor_request(label,case,name)
    c37.INPUTS[label]=case["inputs"]; c37.oracle=oracle; c37.rename_contract=rename_contract
    c38.INPUTS[label]=case["inputs"]; c38.expected_by_handle=expected_by_handle; c38.maintenance_contract=maintenance_contract
    case_dir=pathlib.Path(out)/label; case_dir.mkdir(parents=True,exist_ok=False)
    # Frozen independent mathematical spec and host contracts are retained.
    write(case_dir/"mathematical-specification.json",case)
    creation=c36.create_program(label,pathlib.Path(out))
    # Cycle36 returns the per-step evidence while Cycle37 additionally expects
    # the portable inventory on the creation result object.
    creation["portable_handles"] = c36.read(creation["evidence"] / "constructive-operations.json")["portable_handles"]
    renamed=c37.run_rename(label,creation,pathlib.Path(out))
    rename_root=pathlib.Path(out)/label
    renamed.update({"handoff_path":rename_root/"handoff/handoff.json","anchor_path":rename_root/"handoff/host-trust-anchor.json",
        "contract_path":rename_root/"rename-contract.json","revision":creation["final_revision"]+1,
        "evidence":rename_root/"rename/gateway-evidence"})
    maintenance=c38.run_maintenance(label,creation,renamed,case_dir)
    security_dir=case_dir/"provenance-negative-controls"; security_dir.mkdir()
    # Preserve external anchors and mutate only copied bundles. These are
    # actual verifier-boundary tests, not checksum-only assertions.
    source_handoff=rename_root/"handoff/handoff.json"
    bad_handoff=security_dir/"tampered-handoff.json"
    handoff_doc=c36.read(source_handoff); handoff_doc["final_revision"] += 1; write(bad_handoff,handoff_doc)
    try:
        verify_handoff(bad_handoff,rename_root/"handoff/host-trust-anchor.json",creation["evidence"],renamed["contract_path"])
        raise RuntimeError("tampered creation handoff unexpectedly verified")
    except WorkspaceError as exc:
        handoff_rejection=exc.code
    continuation=maintenance["continuation"]
    tampered_root=security_dir/"tampered-continuation-package"
    shutil.copytree(continuation["evidence_root"],tampered_root)
    tampered_bundle=tampered_root/"continuation.json"
    cont_doc=c36.read(tampered_bundle); cont_doc["final_revision"] += 1; write(tampered_bundle,cont_doc)
    try:
        verify_rename_continuation(tampered_bundle,continuation["anchor_path"],tampered_root,tampered_root/"maintenance-contract.json")
        raise RuntimeError("tampered continuation unexpectedly verified")
    except WorkspaceError as exc:
        continuation_rejection=exc.code
    write(security_dir/"results.json",{"tampered_creation_bundle":{"stage":"construction_handoff_verifier","rejected":True,"code":handoff_rejection},
        "tampered_rename_continuation":{"stage":"continuation_verifier","rejected":True,"code":continuation_rejection,
            "external_anchor_unchanged":True},"authoritative_revision_unchanged":True})
    summary={"case_id":case["case_id"],"seed":seed,"topology":case["topology"],"function_count":len(case["functions"]),
        "construction_revision":creation["final_revision"],"rename_revision":renamed["revision"],
        "maintenance_revision":renamed["revision"]+1,"constructors":len(case["functions"]),
        "rename_commits":1,"maintenance_edit_targets":3,"production_handlers":["Cycle19","Cycle37","Cycle20"],
        "independent_oracle":True,"interpreter_jit_replay":True,"portable_handles":creation["portable_handles"],
        "dependency_edges":case["edges"],"bridge":maintenance["bridge"],
        "provenance_negative_controls":[handoff_rejection,continuation_rejection]}
    write(case_dir/"workflow-summary.json",summary)
    return summary


def main():
    import argparse, shutil
    p=argparse.ArgumentParser();p.add_argument("--output",type=pathlib.Path,default=OUT/"attempt-01");p.add_argument("--count",type=int,default=16);p.add_argument("--seed-offset",type=int,default=0);p.add_argument("--start-index",type=int,default=1);p.add_argument("--rename-index",type=int,default=0)
    a=p.parse_args(); out=a.output.resolve()
    if out.exists() and any(out.iterdir()): raise SystemExit(f"refusing overwrite: {out}")
    if not shutil.which("bun"): raise SystemExit("bun required for actual TypeScript bridge")
    out.mkdir(parents=True,exist_ok=True); rows=[]
    for i in range(a.start_index,a.start_index+a.count):
        seed=40000+a.seed_offset+i
        try: rows.append(run_one(i,seed,out,a.rename_index))
        except Exception as exc:
            write(out/f"{make_label(i)}/failure.json",{"case_index":i,"seed":seed,"classification":"production_workflow_failure","error":repr(exc)})
            raise
    write(out/"production-bridge-results.jsonl", "\n".join(json.dumps(row,separators=(",",":")) for row in rows)+"\n")
    write(out/"coverage.json",{"attempted":len(rows),"passed":len(rows),"topologies":sorted({r["topology"] for r in rows}),"seeds":[r["seed"] for r in rows]})
    print(json.dumps({"attempted":len(rows),"passed":len(rows),"topologies":sorted({r["topology"] for r in rows})},indent=2))

if __name__=="__main__": main()
