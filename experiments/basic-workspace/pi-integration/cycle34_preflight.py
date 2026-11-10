#!/usr/bin/env python3
"""Exercise Cycle34 v2 cross-function edit through the real Pi extension and JSONL gateway; no inference."""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
RESULTS = HERE / "results/cycle34-cross-function-authorization"
EXPECTED_TOOLS = {"workspace_discover_functions", "workspace_inspect_program",
    "workspace_preview_semantic_edit", "workspace_commit_preview", "workspace_validate_mission"}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def independent_reference(contract, value):
    clamp_spec = next(row for row in contract["validation"]["functions"]
        if row["oracle"]["kind"] == "clamp")
    clamp = min(clamp_spec["oracle"]["maximum"], max(clamp_spec["oracle"]["minimum"], value))
    threshold_spec = next(row for row in contract["validation"]["functions"]
        if row["oracle"]["kind"] == "threshold_call")
    return {clamp_spec["result_key"]: float(clamp),
        threshold_spec["result_key"]: float(1 if clamp >= threshold_spec["oracle"]["threshold"] else 0)}


def independent_baseline_reference(value):
    clamp = min(100, max(0, value))
    return {"clamp_score": float(clamp), "is_passing": float(1 if clamp >= 60 else 0)}


def run_arm(name, contract_path, output):
    arm = output / name
    arm.mkdir(parents=True)
    gateway_evidence = arm / "gateway-evidence"
    gateway_error = (arm / "gateway.stderr.log").open("w", encoding="utf-8")
    gateway = subprocess.Popen([sys.executable, str(HERE / "cycle20_gateway.py"),
        "--output", str(gateway_evidence), "--contract", str(contract_path), "--port", "0"],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=gateway_error, text=True)
    try:
        line = gateway.stdout.readline()
        if not line:
            raise RuntimeError(f"{name}: gateway did not emit readiness")
        ready = json.loads(line)
        if not ready.get("ready") or ready.get("revision") != 3 or not ready.get("baseline_verified"):
            raise RuntimeError(f"{name}: unexpected baseline readiness: {ready}")
        contract = read(contract_path)
        edits = [{"target": item["target"], "expected_value": item["expected_original_value"],
                  "replacement_value": item["replacement_constraint"]["values"][0]}
                 for item in contract["authorized_targets"]]
        preview_args = {"expected_revision": 3, "scope_mode": "per_target", "edits": edits}
        unauthorized = json.loads(json.dumps(preview_args))
        unauthorized["edits"][2]["target"]["control_path"] = [{"block": "body", "index": 1}]
        legacy_shape = json.loads(json.dumps(preview_args)); legacy_shape["function_handle"] = "clamp_score.function"
        transport_leak = json.loads(json.dumps(preview_args)); transport_leak["toolCallId"] = "cycle34-transport-only"
        args_path, result_path = arm / "dispatch-input.json", arm / "dispatch-output.json"
        correlation = f"cycle34-{name}-{time.time_ns()}"
        write(args_path, {"authoring_mode": "semantic_edit_multi", "correlation_id": correlation,
            "preview_args": preview_args, "controls": [unauthorized, legacy_shape, transport_leak],
            "commit": True, "duplicate_commit": True})
        env = os.environ.copy()
        env.update({"BASIC_WS_AUTHORING_MODE": "semantic_edit_multi",
            "BASIC_WS_PI_GATEWAY": f"127.0.0.1:{ready['port']}",
            "BASIC_WS_DISPATCH_PROBE_INPUT": str(args_path),
            "BASIC_WS_DISPATCH_PROBE_OUTPUT": str(result_path),
            "NODE_PATH": "/usr/lib/node_modules/@earendil-works/pi-coding-agent/node_modules"})
        ts = subprocess.run(["bun", str(HERE / "cycle20b_dispatch_probe.ts")], env=env,
            capture_output=True, text=True, timeout=60)
        (arm / "dispatch.stdout.log").write_text(ts.stdout, encoding="utf-8")
        (arm / "dispatch.stderr.log").write_text(ts.stderr, encoding="utf-8")
        if ts.returncode != 0 or not result_path.is_file():
            raise RuntimeError(f"{name}: TypeScript dispatch failed: {ts.stderr[-1500:]}")
        result = read(result_path)
        if not result.get("schema_ok") or set(result.get("active_tools", [])) != EXPECTED_TOOLS:
            raise RuntimeError(f"{name}: tool inventory or TypeBox schema failed")
        if not result.get("preview", {}).get("candidate_is_preview_only"):
            raise RuntimeError(f"{name}: preview did not remain non-mutating")
        if result.get("controls", [{}])[0].get("code") != "MISSION_EDIT_TARGETS":
            raise RuntimeError(f"{name}: mixed unauthorized batch was not rejected at authorization")
        rejected_schema_fields = {key for row in result.get("schema_rejections", [])
            for key in row["arguments"] if key in {"function_handle", "toolCallId"}}
        if rejected_schema_fields != {"function_handle", "toolCallId"}:
            raise RuntimeError(f"{name}: legacy global scope or transport metadata escaped v2 schema: {rejected_schema_fields}")
        if not result.get("committed", {}).get("committed") or result["committed"].get("revision") != 4:
            raise RuntimeError(f"{name}: atomic cross-function commit failed")
        if result.get("duplicate_commit", {}).get("code") != "STALE_REVISION":
            raise RuntimeError(f"{name}: consumed transaction replay was not rejected")
        if not result.get("validation", {}).get("mission_complete") or not result["validation"].get("replay", {}).get("passed"):
            raise RuntimeError(f"{name}: independent MIR/replay validation failed")
        independent = {str(value): independent_reference(contract, value) for value in contract["validation"]["inputs"]}
        baseline_evidence = read(gateway_evidence / "baseline-observations.json")["observed_results"]
        baseline_expected = {str(value): independent_baseline_reference(value) for value in contract["validation"]["inputs"]}
        for engine in ("interp", "jit"):
            if result["validation"]["observed_results"][engine] != independent:
                raise RuntimeError(f"{name}: {engine} differs from separate arithmetic reference")
            if baseline_evidence[engine] != baseline_expected:
                raise RuntimeError(f"{name}: reconstructed baseline {engine} differs from separate initial oracle")
        write(arm / "independent-oracle-observations.json", {"source": "separate arithmetic reference in cycle34_preflight.py",
            "input_corpus": contract["validation"]["inputs"], "before_expected": baseline_expected,
            "before_mir_interpreter": baseline_evidence["interp"], "before_mir_jit": baseline_evidence["jit"],
            "before_agree": True, "expected": independent,
            "mir_interpreter": result["validation"]["observed_results"]["interp"],
            "mir_jit": result["validation"]["observed_results"]["jit"], "all_agree": True})
        schemas = result["schemas"]
        schema_bytes = len(json.dumps(schemas, separators=(",", ":"), ensure_ascii=False).encode())
        write(arm / "tool-schemas.json", schemas)
        summary = {"bridge": "actual TypeScript extension handler -> JSONL -> Cycle20Gateway",
            "inference_performed": False, "baseline_revision": 3, "preview_revision_unchanged": 3,
            "atomic_edit_count": result["preview"]["atomic_edit_count"], "committed_revision": 4,
            "active_tools": result["active_tools"], "schema_bytes_compact": schema_bytes,
            "mixed_batch_rejection": result["controls"][0]["code"],
            "schema_rejections": [{"index": row["index"], "field": next(key for key in row["arguments"] if key in {"function_handle", "toolCallId"})}
                for row in result["schema_rejections"]],
            "duplicate_commit_rejection": result["duplicate_commit"]["code"],
            "mir_interpreter_jit": result["validation"]["engines_agree"],
            "fresh_replay": result["validation"]["replay"]["passed"],
            "mission_complete": result["validation"]["mission_complete"], "tool_call_correlation": correlation}
        write(arm / "summary.json", summary)
        return summary
    finally:
        if gateway.poll() is None:
            gateway.terminate()
            try:
                gateway.wait(timeout=5)
            except subprocess.TimeoutExpired:
                gateway.kill(); gateway.wait(timeout=5)
        gateway_error.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=pathlib.Path, default=RESULTS / "production-bridge")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise SystemExit(f"refusing to overwrite evidence: {output}")
    output.mkdir(parents=True, exist_ok=True)
    if not shutil_which("bun"):
        raise SystemExit("Bun is required for actual TypeScript extension integration")
    summaries = {name: run_arm(name, RESULTS / filename, output)
        for name, filename in (("primary", "primary-contract.json"), ("secondary", "secondary-contract.json"))}
    bridge = {"schema": "basic-workspace.cycle34-bridge-validation", "version": 1,
        "inference_performed": False, "missions": summaries, "passed": all(row["mission_complete"] for row in summaries.values())}
    write(output / "bridge-validation.json", bridge)
    write(RESULTS / "bridge-validation.json", bridge)
    replay_rows, oracle_rows = {}, {}
    for name in summaries:
        dispatch = read(output / name / "dispatch-output.json")
        validation = dispatch["validation"]
        replay_rows[name] = {"final_revision": validation["revision"],
            "structural_equivalence": validation["structural_change_scope_valid"],
            "binding_equivalence": validation["dependency_edges_unchanged"],
            "behavioral_equivalence": validation["replay"]["behavioral_equivalence"],
            "interpreter_jit_agreement": validation["replay"]["engine_agreement"],
            "portable_identity_count": validation["preserved_semantic_identity_count"],
            "replay_identity_remappings": validation["replay"]["identity_remappings"],
            "retired_handles": validation["replay"]["retired_handles"], "passed": validation["replay"]["passed"]}
        oracle_rows[name] = read(output / name / "independent-oracle-observations.json")
    write(RESULTS / "replay-equivalence.json", {"schema": "basic-workspace.cycle34-replay-equivalence", "version": 1,
        "missions": replay_rows, "all_passed": all(row["passed"] for row in replay_rows.values())})
    write(RESULTS / "oracle-observations.json", {"schema": "basic-workspace.cycle34-independent-oracle", "version": 1,
        "missions": oracle_rows, "all_agree": all(row["all_agree"] for row in oracle_rows.values())})
    print(json.dumps(summaries, indent=2))


def shutil_which(name):
    import shutil
    return shutil.which(name)


if __name__ == "__main__":
    main()
