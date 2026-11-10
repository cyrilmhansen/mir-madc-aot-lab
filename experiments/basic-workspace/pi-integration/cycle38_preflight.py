#!/usr/bin/env python3
"""Model-free Cycle38 construction -> rename -> maintenance production bridge."""
from __future__ import annotations

import argparse
import copy
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
RESULTS = HERE / "results/cycle38-longitudinal-stress"
sys.path[:0] = [str(ROOT), str(HERE)]

import cycle36_preflight as c36
import cycle37_preflight as c37
from basic_workspace.model import Workspace, WorkspaceError
from basic_workspace.mir_execution import MirExecutionService
from basic_workspace.portable_replay import replay_constructive_stream
from basic_workspace.projection import build_projection, projection_semantics
from cycle20_gateway import senior, _call_edges
from cycle26_gateway import Cycle26Gateway
from run_cycle16 import gateway_call
from verified_handoff import build_handoff, _fingerprint
from verified_rename_continuation import build_rename_continuation

PROFILE = "basic-workspace.numeric-composition.v1"
EXECUTOR = MirExecutionService(timeout=20)
TOOLS = {"workspace_discover_functions", "workspace_inspect_program", "workspace_preview_semantic_edit",
    "workspace_commit_preview", "workspace_validate_mission"}
INPUTS = {"mission-a": c36.INPUTS["mission-a"], "mission-b": c36.INPUTS["mission-b"]}


def read(path): return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
def keys_recursive(value):
    if isinstance(value, dict):
        nested = set().union(*(keys_recursive(child) for child in value.values())) if value else set()
        return set(value) | nested
    if isinstance(value, list):
        return set().union(*(keys_recursive(child) for child in value)) if value else set()
    return set()

def write(path, value):
    path = pathlib.Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
def stop(proc):
    if proc and proc.poll() is None:
        proc.terminate()
        try: proc.wait(timeout=5)
        except subprocess.TimeoutExpired: proc.kill(); proc.wait(timeout=5)


def contract_rename_b(creation, out):
    functions = [step["function"]["portable_handle"] for step in creation["sequence"]["steps"]]
    contract = {"schema": "basic-workspace.semantic-rename-contract", "version": 2,
        "mission_id": "cycle38.mission-b.age-provider-rename.v2",
        "objective": "Rename NORMALIZED_AGE to CAPPED_AGE, preserving identity, bindings and behavior.",
        "base_document_revision": creation["final_revision"], "execution_profile_id": PROFILE,
        "target_handle": "normalized_age.function", "expected_source_name": "NORMALIZED_AGE",
        "new_source_name": "CAPPED_AGE",
        "unchanged_function_handles": [handle for handle in functions if handle != "normalized_age.function"],
        "unchanged_dependency_edges": True, "required_revision_increment": 1,
        "validation_inputs": list(INPUTS["mission-b"])}
    path = out / "rename-contract.json"; write(path, contract); return path, contract


def rename_b(creation, out):
    out.mkdir(parents=True, exist_ok=True)
    contract_path, contract = contract_rename_b(creation, out)
    handoff_dir = out / "handoff"; handoff_dir.mkdir(parents=True, exist_ok=True)
    handoff, anchor = build_handoff(creation["evidence"], creation["sequence_path"], contract_path,
        handoff_dir / "handoff.json", handoff_dir / "host-trust-anchor.json")
    (out / "rename").mkdir(parents=True, exist_ok=True)
    evidence = out / "rename/gateway-evidence"; err = (out / "rename/gateway.stderr.log").open("w", encoding="utf-8")
    env = os.environ.copy(); env["PYTHONPATH"] = os.pathsep.join((str(ROOT), str(HERE), env.get("PYTHONPATH", "")))
    proc = subprocess.Popen([sys.executable, str(HERE / "cycle26_gateway.py"), "--output", str(evidence),
        "--contract", str(contract_path), "--verified-handoff", str(handoff_dir / "handoff.json"),
        "--handoff-anchor", str(handoff_dir / "host-trust-anchor.json"),
        "--handoff-evidence-root", str(creation["evidence"]), "--port", "0"],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=err, text=True, env=env)
    try:
        line = proc.stdout.readline()
        if not line: raise RuntimeError(f"Cycle37 rename gateway did not start: {err.name}")
        ready = json.loads(line); base_revision = creation["final_revision"]
        if ready.get("revision") != base_revision or not ready.get("baseline_verified"):
            raise RuntimeError(f"Rename gateway baseline was not verified: {ready}")
        request = {"expected_revision": base_revision, "function_handle": contract["target_handle"],
            "expected_name": contract["expected_source_name"], "new_name": contract["new_source_name"]}
        controls = [{**request, "function_handle": "invented.function"}, {**request, "expected_name": "OLD_AGE"},
            {**request, "new_name": "UNAUTHORIZED"}, {**request, "expected_revision": base_revision - 1}]
        result = c37.dispatch(out / "rename", ready["port"], "rename", {"authoring_mode": "rename",
            "correlation_id": f"cycle38-mission-b-rename-{time.time_ns()}", "preview_args": request,
            "controls": controls, "commit": True, "duplicate_commit": True})
        codes = [row.get("code") for row in result.get("controls", [])]
        if codes != ["MISSION_RENAME_SCOPE", "RENAME_PRECONDITION_FAILED", "MISSION_RENAME_NAME", "STALE_REVISION"]:
            raise RuntimeError(f"Mission B rename controls differ: {codes}")
        schema_bad = {**request, "unknown_semantic_field": True}
        schema_result = c37.dispatch(out / "rename-schema-negative", ready["port"], "rename", {
            "authoring_mode": "rename", "correlation_id": f"cycle38-mission-b-schema-{time.time_ns()}",
            "preview_args": schema_bad})
        if schema_result.get("schema_ok") is not False: raise RuntimeError("Rename schema accepted an unknown field")
        if (result.get("active_tools") is None or set(result["active_tools"]) != c37.RENAME_TOOLS
                or not result["preview"].get("candidate_is_preview_only")
                or result.get("committed", {}).get("revision") != base_revision + 1
                or result.get("duplicate_commit", {}).get("committed") is not False
                or not result.get("validation", {}).get("mission_complete")):
            raise RuntimeError("Mission B production rename path did not complete its preview/commit/validation")
        host = gateway_call("127.0.0.1", ready["port"], "host_validate", {"expected_revision": base_revision + 1})
        if not host.get("mission_complete"): raise RuntimeError("Mission B independent rename host validation failed")
        write(out / "rename-bridge-validation.json", {"tools": sorted(result["active_tools"]), "controls": codes,
            "unknown_schema_field_rejected": True, "preview_non_mutating": True,
            "base_revision": base_revision, "committed_revision": base_revision + 1,
            "duplicate_commit_rejected": True, "host_validation": host["mission_complete"]})
        return {"contract": contract, "contract_path": contract_path, "handoff": handoff, "anchor": anchor,
            "evidence": evidence, "revision": base_revision + 1, "host_validation": host, "bridge": result}
    finally:
        stop(proc); err.close()


def maintenance_contract(label, creation, renamed, out):
    contract_path, contract = c36.edit_contract(label, creation, out)
    contract["base_document_revision"] = renamed["revision"]
    contract["mission_id"] = f"cycle38.{label}.maintenance.v1"
    if label == "mission-a":
        contract["objective"] = "At revision 6, cap NORMALIZED_SCORE at 80 and set IS_PASSING threshold to 70 atomically."
        contract["validation"]["functions"][0]["result_key"] = "normalized_score"
    else:
        contract["objective"] = "At revision 5, cap CAPPED_AGE at 60 and set IS_SENIOR threshold to 55 atomically."
        contract["validation"]["functions"][0]["result_key"] = "capped_age"
    write(contract_path, contract)
    return contract_path, contract


def start_maintenance(label, continuation, contract_path, out):
    (out / "maintenance").mkdir(parents=True, exist_ok=True)
    evidence = out / "maintenance/gateway-evidence"; err = (out / "maintenance/gateway.stderr.log").open("w", encoding="utf-8")
    package = continuation["evidence_root"]
    env = os.environ.copy(); env["PYTHONPATH"] = os.pathsep.join((str(ROOT), str(HERE), env.get("PYTHONPATH", "")))
    proc = subprocess.Popen([sys.executable, str(HERE / "cycle20_gateway.py"), "--output", str(evidence),
        "--contract", str(contract_path), "--verified-rename-continuation", str(continuation["bundle_path"]),
        "--continuation-anchor", str(continuation["anchor_path"]), "--continuation-evidence-root", str(package),
        "--port", "0"], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=err, text=True, env=env)
    try:
        line = proc.stdout.readline()
        if not line: raise RuntimeError(f"Cycle20 continuation gateway failed to start: {err.name}")
        ready = json.loads(line)
        expected_revision = continuation["verified"]["revision"]
        if (ready.get("revision") != expected_revision or not ready.get("baseline_verified")
                or not ready.get("continuation_verified")):
            raise RuntimeError(f"Cycle20 did not authenticate the post-rename baseline: {ready}")
        reconstruction = read(evidence / "baseline-reconstruction.json")
        if (reconstruction.get("normalized_semantics_match") is not True
                or reconstruction.get("portable_identity_count") != len(continuation["verified"]["aliases"])
                or not all(row.get("remapped") for row in reconstruction.get("identity_mapping", []))):
            raise RuntimeError("Cycle20 reconstructed baseline identity or structure verification is incomplete")
        return proc, err, ready, evidence
    except BaseException:
        stop(proc); err.close(); raise


def expected_by_handle(label, maintained, x):
    if label == "mission-a":
        cap = 80 if maintained else 100; threshold = 70 if maintained else 60
        normalized = min(cap, max(0, x)); excellent = int(normalized >= 90)
        return {"bounded_score.function": float(normalized), "is_passing.function": float(normalized >= threshold),
            "is_excellent.function": float(excellent), "high_priority.function": float(excellent)}
    cap = 60 if maintained else 100; threshold = 55 if maintained else 65
    age = min(cap, max(0, x)); senior_result = int(age >= threshold)
    return {"normalized_age.function": float(age), "is_senior.function": float(senior_result),
        "senior_flag.function": float(senior_result)}


def observe_prefix(ws, doc, revision, aliases, handles, values):
    return {engine: {str(value): {handle: EXECUTOR.execute_function(ws, doc, revision, aliases[handle], [value], engine)["result"]
            for handle in handles} for value in values} for engine in ("interp", "jit")}


def run_maintenance(label, creation, renamed, maintenance_root):
    contract_path, contract = maintenance_contract(label, creation, renamed, maintenance_root)
    continuation = build_rename_continuation(creation_handoff=renamed["handoff_path"],
        creation_anchor=renamed["anchor_path"], creation_evidence_root=creation["evidence"],
        rename_contract=renamed["contract_path"], rename_evidence_root=renamed["evidence"],
        destination_contract=contract_path, package_root=maintenance_root / "continuation-package")
    proc, err, ready, evidence = start_maintenance(label, continuation, contract_path, maintenance_root)
    try:
        gateway = {"host": "127.0.0.1", "port": ready["port"]}
        initial = gateway_call(gateway["host"], gateway["port"], "get_status", {})
        base_revision = renamed["revision"]
        # Use the live, revision-bound target projection discovered after the
        # continuation verifier reconstructed the program.
        inspection = gateway_call(gateway["host"], gateway["port"], "inspect_program", {})
        edit_rows = []
        for target_spec in contract["authorized_targets"]:
            edit_rows.append({"target": target_spec["target"],
                "expected_value": target_spec["expected_original_value"],
                "replacement_value": target_spec["replacement_constraint"]["values"][0]})
        request = {"expected_revision": base_revision, "scope_mode": "per_target", "edits": edit_rows}
        invalid_mixed = copy.deepcopy(request)
        invalid_mixed["edits"][-1]["target"]["function_handle"] = "unauthorized.function"
        stale = copy.deepcopy(request); stale["expected_revision"] -= 1
        missing = copy.deepcopy(request); missing["edits"].pop()
        duplicate = copy.deepcopy(request); duplicate["edits"][1] = copy.deepcopy(duplicate["edits"][0])
        unknown = copy.deepcopy(request); unknown["edits"][0]["untrusted"] = True
        transport = copy.deepcopy(request); transport["toolCallId"] = "not-semantic"
        result = c36.dispatch(ready, {"authoring_mode": "semantic_edit_multi",
            "correlation_id": f"cycle38-{label}-maintenance-{time.time_ns()}", "preview_args": request,
            "controls": [invalid_mixed, stale, missing, duplicate, unknown, transport],
            "commit": True, "duplicate_commit": True}, maintenance_root / "maintenance-dispatch", "semantic_edit_multi")
        if not result.get("ok") or not result.get("schema_ok") or set(result.get("active_tools", [])) != TOOLS:
            raise RuntimeError("Cycle20 actual TypeScript/JSONL multi-edit dispatch did not use the five-tool maintenance interface")
        control_rows = result.get("controls", [])
        control_codes = [row.get("code") for row in control_rows]
        if control_codes[:3] != ["MISSION_EDIT_TARGETS", "STALE_REVISION", "MISSION_EDIT_COUNT"]:
            raise RuntimeError(f"Maintenance authorization rejected the wrong failure classes: {control_codes}")
        schema_fields = set().union(*(keys_recursive(row.get("arguments", {}))
            for row in result.get("schema_rejections", [])))
        if not {"untrusted", "toolCallId"}.issubset(schema_fields):
            raise RuntimeError(f"Transport/unknown semantic fields were not rejected by TypeScript schema: {schema_fields}")
        if (not result["preview"].get("candidate_is_preview_only") or result["preview"].get("base_revision") != base_revision
                or result["committed"].get("revision") != base_revision + 1
                or result["duplicate_commit"].get("committed") is not False):
            raise RuntimeError("Maintenance did not preview without mutation and commit exactly one revision")
        host = gateway_call(gateway["host"], gateway["port"], "host_validate", {"expected_revision": base_revision + 1})
        if not host.get("mission_complete"):
            raise RuntimeError(f"Cycle20 independent maintenance oracle failed: {host.get('diagnostics')}")
        stream = read(evidence / "constructive-operations.json")
        prefix_rows = {}
        expected_revisions = len(stream["operations"]) + 1
        for prefix in range(1, len(stream["operations"]) + 1):
            ws = Workspace(); doc = ws.create_empty_document(f"memory://cycle38/{label}/prefix-{prefix}.bas")["document_id"]
            replay = replay_constructive_stream(ws, doc, stream["operations"][:prefix], expected_start_revision=1)
            normalized = senior.normalized_state(projection_semantics(build_projection(ws, doc, replay.revision)), replay.live_handles)
            maintenance_applied = prefix == len(stream["operations"])
            handles = sorted(handle for handle in replay.live_handles if handle.endswith(".function"))
            observed = observe_prefix(ws, doc, replay.revision, replay.live_handles, handles, INPUTS[label])
            expected = {engine: {str(x): {h: expected_by_handle(label, maintenance_applied, x)[h]
                for h in handles if h in expected_by_handle(label, maintenance_applied, x)} for x in INPUTS[label]}
                for engine in ("interp", "jit")}
            if observed != expected:
                raise RuntimeError(f"Mission {label} replay revision {replay.revision} disagrees with independent oracle")
            prefix_rows[str(replay.revision)] = {"operation_prefix": prefix, "normalized_semantics": normalized,
                "signatures": [{"handle": f["handle"], "name": f["name"], "parameters": f["parameters"],
                    "return_type": f["return_type"]} for f in normalized["functions"]],
                "dependencies": _call_edges(normalized), "portable_handles": sorted(replay.live_handles),
                "retired_handles": replay.retired_handles, "interpreter": observed["interp"], "jit": observed["jit"],
                "independent_oracle_match": True}
        if expected_revisions != base_revision + 1:
            raise RuntimeError("Complete longitudinal stream has an unexpected operation/revision count")
        final_state = prefix_rows[str(base_revision + 1)]["normalized_semantics"]
        if final_state != host.get("normalized_semantics") and host.get("normalized_semantics") is not None:
            raise RuntimeError("Fresh complete replay differs from the maintenance host validation structure")
        write(maintenance_root / "revision-checkpoints.json", {"prefixes": prefix_rows,
            "final_revision": base_revision + 1, "passed": True})
        write(maintenance_root / "independent-oracle-observations.json", {
            "inputs": INPUTS[label], "pre_maintenance_expected_by_handle": {str(x): expected_by_handle(label, False, x) for x in INPUTS[label]},
            "post_maintenance_expected_by_handle": {str(x): expected_by_handle(label, True, x) for x in INPUTS[label]},
            "pre_maintenance_interpreter": continuation["verified"]["base_observations_by_handle"]["interp"],
            "pre_maintenance_jit": continuation["verified"]["base_observations_by_handle"]["jit"],
            "post_maintenance_interpreter": host["observed_results"]["interp"],
            "post_maintenance_jit": host["observed_results"]["jit"], "engines_agree": host.get("engines_agree"),
            "expectation_source": "Cycle38 explicit arithmetic oracle; not derived from MIR"})
        write(maintenance_root / "bridge-validation.json", {"bridge": "actual TypeScript extension -> JSONL -> Cycle20Gateway",
            "continuation_verified": True, "destination_contract_bound": True, "base_revision": base_revision,
            "committed_revision": base_revision + 1, "atomic_edit_count": len(edit_rows),
            "preview_non_mutating": True, "duplicate_commit_rejected": True, "control_codes": control_codes,
            "schema_rejections": sorted(schema_fields), "active_tools": sorted(result["active_tools"]),
            "compact_schema_bytes": len(json.dumps(result["schemas"], separators=(",", ":")).encode()),
            "host_validation": host.get("mission_complete"), "full_replay": host.get("replay", {}).get("passed")})
        return {"contract": contract, "continuation": continuation, "bridge": read(maintenance_root / "bridge-validation.json"),
            "host_validation": host, "prefixes": prefix_rows, "gateway_evidence": evidence,
            "target_inspection": inspection, "initial_status": initial}
    finally:
        stop(proc); err.close()


def run_mission_a(out):
    creation = c37.create_program("mission-a", out)
    renamed = c37.run_rename("mission-a", creation, out)
    renamed.update({"handoff_path": out / "mission-a/handoff/handoff.json",
        "anchor_path": out / "mission-a/handoff/host-trust-anchor.json", "contract_path": out / "mission-a/rename-contract.json",
        "revision": creation["final_revision"] + 1, "evidence": out / "mission-a/rename/gateway-evidence"})
    return creation, renamed


def run_mission_b(out):
    creation = c36.create_program("mission-b", out)
    rename_out = out / "mission-b"; rename_out.mkdir(parents=True, exist_ok=True)
    renamed = rename_b(creation, rename_out)
    renamed.update({"handoff_path": rename_out / "handoff/handoff.json", "anchor_path": rename_out / "handoff/host-trust-anchor.json",
        "contract_path": renamed["contract_path"], "revision": renamed["revision"]})
    return creation, renamed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args(); out = args.output.resolve()
    if out.exists() and any(out.iterdir()): raise SystemExit(f"Refusing to overwrite evidence: {out}")
    if not shutil.which("bun"): raise SystemExit("Bun is required for the actual TypeScript bridge")
    out.mkdir(parents=True, exist_ok=True)
    results = {}
    for label, create in (("mission-a", run_mission_a), ("mission-b", run_mission_b)):
        creation, renamed = create(out)
        maintenance = run_maintenance(label, creation, renamed, out / label)
        portable_handles = creation.get("portable_handles") or sorted(
            step["function"]["portable_handle"] for step in creation["sequence"]["steps"])
        results[label] = {"creation_revision": creation["final_revision"], "rename_revision": renamed["revision"],
            "maintenance_revision": renamed["revision"] + 1, "portable_handles": portable_handles,
            "rename_contract": renamed["contract"], "maintenance_contract": maintenance["contract"],
            "rename_host_validation": renamed.get("host_validation"), "bridge": maintenance["bridge"]}
    write(out / "bridge-validation.json", {"schema": "basic-workspace.cycle38-production-bridge", "version": 1,
        "inference_performed": False, "missions": results, "passed": True})
    print(json.dumps({label: {key: row[key] for key in ("creation_revision", "rename_revision", "maintenance_revision")}
        for label, row in results.items()}, indent=2))


if __name__ == "__main__": main()
