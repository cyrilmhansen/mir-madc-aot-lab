#!/usr/bin/env python3
"""No-inference TypeScript-extension/JSONL preflight for the shared kernel."""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
EXPECTED_ATOMIC = ["workspace_discover_functions", "workspace_inspect_program",
    "workspace_preview_function", "workspace_commit_preview", "workspace_validate_mission"]


def write(path: pathlib.Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read(path: pathlib.Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=pathlib.Path, required=True)
    ap.add_argument("--maintenance-schema-dir", type=pathlib.Path, required=True)
    args = ap.parse_args()
    out = args.output.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"refusing to overwrite preflight evidence: {out}")
    out.mkdir(parents=True, exist_ok=True)

    # Exercise the exact installed TypeScript extension tool handler and its
    # JSONL bridge against the production Cycle19 gateway in a fresh document.
    create = out / "function-creation"
    create.mkdir()
    gateway_err = (create / "gateway.stderr.log").open("w", encoding="utf-8")
    proc = subprocess.Popen([sys.executable, str(HERE / "cycle19_gateway.py"),
        "--output", str(create / "gateway-evidence"), "--port", "0"],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=gateway_err, text=True)
    try:
        line = proc.stdout.readline()
        if not line:
            raise RuntimeError("Cycle19 gateway exited before readiness")
        ready = json.loads(line)
        if ready.get("revision") != 1 or not ready.get("ready"):
            raise RuntimeError(f"creation gateway was not empty/revision 1: {ready}")
        args_path, result_path = create / "dispatch-input.json", create / "dispatch-output.json"
        constructor = {"expected_revision": 1, "name": "CLAMP_SCORE", "parameters": ["X"], "body": [
            {"kind": "assign", "target": {"kind": "result"}, "expression": {"kind": "local_ref", "name": "X"}},
            {"kind": "if", "condition": {"kind": "binary", "operator": "<", "left": {"kind": "local_ref", "name": "X"}, "right": {"kind": "number", "value": 0}},
             "then": [{"kind": "assign", "target": {"kind": "result"}, "expression": {"kind": "number", "value": 0}}]},
            {"kind": "if", "condition": {"kind": "binary", "operator": ">", "left": {"kind": "local_ref", "name": "X"}, "right": {"kind": "number", "value": 100}},
             "then": [{"kind": "assign", "target": {"kind": "result"}, "expression": {"kind": "number", "value": 100}}]},
        ]}
        correlation = f"cycle23-create-{time.time_ns()}"
        write(args_path, {"authoring_mode": "atomic_create", "correlation_id": correlation,
            "preview_args": constructor, "commit": True, "duplicate_commit": True,
            "controls": [dict(constructor, name="UNRELATED"), dict(constructor, expected_revision=0)]})
        env = os.environ.copy()
        env.update({"BASIC_WS_AUTHORING_MODE": "atomic", "BASIC_WS_PI_GATEWAY": f"127.0.0.1:{ready['port']}",
            "BASIC_WS_DISPATCH_PROBE_INPUT": str(args_path), "BASIC_WS_DISPATCH_PROBE_OUTPUT": str(result_path),
            "NODE_PATH": "/usr/lib/node_modules/@earendil-works/pi-coding-agent/node_modules"})
        ts = subprocess.run(["bun", str(HERE / "cycle20b_dispatch_probe.ts")], env=env,
            capture_output=True, text=True, timeout=45)
        (create / "dispatch.stdout.log").write_text(ts.stdout, encoding="utf-8")
        (create / "dispatch.stderr.log").write_text(ts.stderr, encoding="utf-8")
        if ts.returncode or not result_path.is_file():
            raise RuntimeError(f"production creation extension dispatch failed: {ts.stderr[-1200:]}")
        result = read(result_path)
        if set(result.get("active_tools", [])) != set(EXPECTED_ATOMIC) or not result.get("schema_ok"):
            raise RuntimeError("creation tool inventory/schema check failed")
        schema_path = HERE / "results/cycle19-empty-workspace/preflight-corrected/tool-schemas.json"
        captured = read(schema_path)
        schema_by_name = {row["name"]: row["parameters"] for row in result.get("schemas", [])}
        captured_by_name = {row["name"]: row["parameters"] for row in captured}
        if schema_by_name != captured_by_name:
            raise RuntimeError("registered creation schema differs from the preserved active Pi schema capture")
        write(create / "tool-inventory.json", {"source": "Production Pi extension registry", "tools": result["active_tools"]})
        write(create / "tool-schemas.json", result["schemas"])
        if not result.get("preview", {}).get("candidate_is_preview_only"):
            raise RuntimeError("creation preview did not report preview-only status")
        control_codes = [row.get("code") for row in result.get("controls", [])]
        if control_codes != ["MISSION_SIGNATURE", "STALE_REVISION"]:
            raise RuntimeError(f"creation negative controls returned unexpected codes: {control_codes}")
        if not result.get("committed", {}).get("committed") or result["committed"].get("revision") != 2:
            raise RuntimeError("creation commit did not advance exactly to revision 2")
        if result.get("duplicate_commit", {}).get("code") != "STALE_REVISION":
            raise RuntimeError("duplicate constructor commit was not rejected as stale")
        if not result.get("validation", {}).get("mission_complete") or not result["validation"].get("replay", {}).get("passed"):
            raise RuntimeError("creation MIR/replay validation failed")
        write(create / "summary.json", {"authoring_mode": "atomic_create", "schema_bytes": len(json.dumps(result["schemas"], separators=(",", ":")).encode()),
            "active_tools": result["active_tools"], "registered_schema_bytes": len(json.dumps(result["schemas"], separators=(",", ":")).encode()),
            "preview_only_revision": 1, "committed_revision": 2,
            "rejection_controls": control_codes, "duplicate_commit_code": result["duplicate_commit"]["code"],
            "interpreter_jit_agreement": result["validation"].get("engines_agree"),
            "fresh_replay": result["validation"].get("replay", {}).get("passed"),
            "tool_call_id": correlation, "extension_to_jsonl": "passed"})
    finally:
        if proc.poll() is None:
            proc.terminate()
            try: proc.wait(timeout=5)
            except subprocess.TimeoutExpired: proc.kill(); proc.wait(timeout=5)
        gateway_err.close()

    # Reuse the already production-backed Cycle21 dispatch suite for numeric
    # maintenance; it exercises two contract families, negatives and commit.
    maintenance = out / "numeric-maintenance"
    maintenance.mkdir()
    with tempfile.TemporaryDirectory(prefix="atlas-cycle23-maintenance-", dir="/var/tmp") as temp:
        full_evidence = pathlib.Path(temp) / "maintenance"
        cmd = [sys.executable, str(HERE / "cycle21_preflight.py"), "--output", str(full_evidence),
            "--pi-schema-dir", str(args.maintenance_schema_dir.resolve())]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=150)
        if result.returncode:
            raise RuntimeError(f"maintenance TypeScript/JSONL preflight failed: {result.stderr[-2000:]}")
        maintenance_summary = read(full_evidence / "preflight-summary.json")
        # Keep the aggregate and source requests, plus the exact production
        # handler responses for each historical proposal and both commits.
        shutil.copy2(full_evidence / "preflight-summary.json", maintenance / "preflight-summary.json")
        shutil.copy2(full_evidence / "historical-cycle20-proposals.json", maintenance / "historical-cycle20-proposals.json")
        selected = {"mission-a-preview-commit-replay", "mission-b-preview-commit-replay"} | {
            f"mission-a-historical-{index:02d}" for index in range(1, 5)}
        dispatch = maintenance / "production-dispatch"
        dispatch.mkdir()
        for name in sorted(selected):
            source = full_evidence / name
            target = dispatch / name
            target.mkdir()
            for filename in ("dispatch-input.json", "dispatch-output.json"):
                shutil.copy2(source / filename, target / filename)
    summary = {"schema": "basic-workspace.cycle23-transaction-preflight", "version": 1,
        "inference_performed": False, "function_creation": read(create / "summary.json"),
        "numeric_maintenance": {"cycle21_production_dispatch_checks": maintenance_summary.get("all_preflight_checks_passed"),
            "mission_a_historical_proposals": len(maintenance_summary.get("mission_a_historical_proposals", [])),
            "mission_b_disposable_commit_validation_replay": maintenance_summary.get("mission_b_disposable_commit_validation_replay"),
            "active_tool_schema_bytes": maintenance_summary.get("active_pi_schema_bytes")}}
    write(out / "summary.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
