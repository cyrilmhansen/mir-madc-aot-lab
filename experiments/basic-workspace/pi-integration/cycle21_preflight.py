#!/usr/bin/env python3
"""No-inference production Extension -> JSONL gateway checks for Cycle 21."""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import socket
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
CONTRACTS = HERE / "contracts/numeric-edit"
REV4 = HERE / "results/cycle20b-semantic-edit-recovery/real-agent-02"
TOOLS = ["workspace_discover_functions", "workspace_inspect_program", "workspace_preview_semantic_edit",
         "workspace_commit_preview", "workspace_validate_mission"]


def write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def call(host, port, method, params, correlation):
    request = {"request_id": f"cycle21-{time.time_ns()}", "method": method, "params": params,
               "transport": {"tool_call_id": correlation}}
    with socket.create_connection((host, port), timeout=10) as conn:
        conn.settimeout(15)
        conn.sendall(json.dumps(request, separators=(",", ":")).encode() + b"\n")
        data = bytearray()
        while b"\n" not in data:
            chunk = conn.recv(65536)
            if not chunk:
                raise RuntimeError("gateway closed before its JSONL response")
            data.extend(chunk)
            if len(data) > 1024 * 1024:
                raise RuntimeError("gateway response exceeded 1 MiB")
    return json.loads(bytes(data).split(b"\n", 1)[0])


class Gateway:
    def __init__(self, case, contract, *, mission_b=False):
        self.case = case
        self.case.mkdir(parents=True, exist_ok=True)
        self.err = (case / "gateway.stderr.log").open("w", encoding="utf-8")
        cmd = [sys.executable, str(HERE / "cycle20_gateway.py"), "--output", str(case / "gateway-evidence"),
               "--contract", str(contract), "--port", "0"]
        if mission_b:
            cmd += ["--baseline-stream", str(REV4 / "constructive-operations.json"),
                    "--baseline-history", str(REV4 / "history.jsonl"),
                    "--baseline-validation", str(REV4 / "validation.json")]
        self.proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                     stderr=self.err, text=True)
        line = self.proc.stdout.readline()
        if not line:
            raise RuntimeError(f"gateway failed to start: {(case / 'gateway.stderr.log').read_text()}")
        self.ready = json.loads(line)
        wanted = 4 if mission_b else 3
        if not self.ready.get("ready") or self.ready.get("revision") != wanted or not self.ready.get("contract_verified"):
            self.close()
            raise RuntimeError(f"gateway readiness mismatch: {self.ready}")

    def close(self):
        if getattr(self, "proc", None) and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill(); self.proc.wait(timeout=5)
        if getattr(self, "err", None) and not self.err.closed:
            self.err.close()


def extension_probe(case, ready, args, *, commit=False, schema_expected=None):
    input_path, output_path = case / "dispatch-input.json", case / "dispatch-output.json"
    write(input_path, {"correlation_id": f"cycle21-dispatch-{case.name}", "preview_args": args, "commit": commit})
    env = os.environ.copy()
    env.update({"BASIC_WS_AUTHORING_MODE": "semantic_edit",
        "BASIC_WS_PI_GATEWAY": f"127.0.0.1:{ready['port']}",
        "BASIC_WS_DISPATCH_PROBE_INPUT": str(input_path),
        "BASIC_WS_DISPATCH_PROBE_OUTPUT": str(output_path),
        "NODE_PATH": "/usr/lib/node_modules/@earendil-works/pi-coding-agent/node_modules"})
    result = subprocess.run(["bun", str(HERE / "cycle20b_dispatch_probe.ts")], env=env,
        capture_output=True, text=True, timeout=40)
    (case / "dispatch.stdout.log").write_text(result.stdout, encoding="utf-8")
    (case / "dispatch.stderr.log").write_text(result.stderr, encoding="utf-8")
    if result.returncode or not output_path.is_file():
        raise RuntimeError(f"production TypeScript dispatch failed at {case}: {result.stderr[-1200:]}")
    output = read(output_path)
    if schema_expected is not None:
        actual = {row["name"]: row["parameters"] for row in output.get("schemas", [])}
        if actual != schema_expected:
            raise RuntimeError("production extension schema differs from the captured Pi schema")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--pi-schema-dir", type=pathlib.Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"refusing to overwrite preflight evidence: {out}")
    out.mkdir(parents=True, exist_ok=True)
    schema_dir = args.pi_schema_dir.resolve()
    schemas = read(schema_dir / "tool-schemas.json")
    inventory = read(schema_dir / "tool-inventory.json")
    if inventory.get("tools") != TOOLS or {row["name"] for row in schemas} != set(TOOLS):
        raise RuntimeError("the captured active Pi tool allowlist is not the expected five tools")
    schema_map = {row["name"]: row["parameters"] for row in schemas}
    preview_schema = schema_map["workspace_preview_semantic_edit"]
    if preview_schema["properties"]["edits"].get("minItems") != 1 or preview_schema["properties"]["edits"].get("maxItems") != 8:
        raise RuntimeError("Pi schema does not advertise the bounded reusable edit list")
    if json.dumps(schemas, separators=(",", ":")).find('"items":{}') >= 0:
        raise RuntimeError("active schema contains an unconstrained items shape")

    # Use the four actual model arguments preserved in Cycle 20's original Pi
    # transcript; each one is previewed in an independent Mission A workspace.
    from cycle20b_preflight import historical_fixtures
    historical, malformed, all_calls = historical_fixtures()
    write(out / "historical-cycle20-proposals.json", {"source": str(HERE / "results/cycle20-semantic-evolution/real-agent-01"),
        "four_model_proposals": historical, "malformed_fifth_schema_fixture": malformed, "all_tool_calls": all_calls})
    a_contract = CONTRACTS / "cycle20-cap50.json"
    a_previews = []
    for i, fixture in enumerate(historical, 1):
        case = out / f"mission-a-historical-{i:02d}"; case.mkdir()
        gateway = Gateway(case, a_contract)
        try:
            result = extension_probe(case, gateway.ready, fixture["args"], schema_expected=schema_map)
            if not result.get("schema_ok") or not result.get("preview", {}).get("accepted"):
                raise RuntimeError(f"historical Cycle 20 proposal {i} did not pass the new shared contract: {result}")
            state = call("127.0.0.1", gateway.ready["port"], "get_status", {}, f"status-a-{i}")
            if state["result"]["revision"] != 3 or state["result"]["committed"]:
                raise RuntimeError("Mission A preview changed committed Workspace state")
            a_previews.append({"source_tool_call_id": fixture["tool_call_id"], "schema_valid": True,
                "preview_accepted": True, "revision_unchanged": True,
                "candidate_observations": result["preview"]["impact"]["candidate_observations"]})
        finally:
            gateway.close()

    # Disposable Mission A commit validates the same TypeScript-to-JSONL path.
    a_case = out / "mission-a-preview-commit-replay"; a_case.mkdir()
    gateway = Gateway(a_case, a_contract)
    try:
        committed_a = extension_probe(a_case, gateway.ready, historical[0]["args"], commit=True, schema_expected=schema_map)
        if not committed_a["preview"]["accepted"] or not committed_a["committed"]["committed"] or not committed_a["validation"]["mission_complete"]:
            raise RuntimeError("Mission A disposable preview, commit, MIR or replay failed")
        if not committed_a["validation"].get("replay", {}).get("passed"):
            raise RuntimeError("Mission A disposable fresh replay failed")
    finally:
        gateway.close()

    b_contract = CONTRACTS / "cycle21-is-passing-threshold40.json"
    b_args = {"expected_revision": 4, "function_handle": "is_passing.function", "edits": [{
        "target": {"function_handle": "is_passing.function", "control_path": [{"block": "body", "index": 0}], "expression_path": [1]},
        "expected_value": 60, "replacement_value": 40}]}
    b_case = out / "mission-b-preview-commit-replay"; b_case.mkdir()
    gateway = Gateway(b_case, b_contract, mission_b=True)
    try:
        committed_b = extension_probe(b_case, gateway.ready, b_args, commit=True, schema_expected=schema_map)
        if not committed_b["preview"]["accepted"] or not committed_b["committed"]["committed"] or not committed_b["validation"]["mission_complete"]:
            raise RuntimeError("Mission B disposable preview, commit, MIR or replay failed")
        if not committed_b["validation"].get("replay", {}).get("passed"):
            raise RuntimeError("Mission B disposable fresh replay failed")
        if committed_b["committed"]["revision"] != 5:
            raise RuntimeError("Mission B did not make exactly one revision increment")
        timing_rows = [json.loads(line) for line in
            (b_case / "gateway-evidence/gateway-tool-timings.jsonl").read_text(encoding="utf-8").splitlines() if line]
        correlated = [row for row in timing_rows if row.get("tool_call_id") == f"cycle21-dispatch-{b_case.name}"]
        if not any(row.get("method") == "preview_semantic_edit" for row in correlated):
            raise RuntimeError("Pi tool-call correlation was not retained at the extension/JSONL boundary")
    finally:
        gateway.close()

    # Denials go through the same production Python JSONL dispatcher with the
    # same transport envelope. Each control gets a fresh authoritative state.
    controls = []
    invalids = [
        ("incorrect_edit_count", {**b_args, "edits": []}, "MISSION_EDIT_COUNT"),
        ("undiscovered_handle", {**b_args, "function_handle": "unknown.function"}, "FUNCTION_NOT_DISCOVERED"),
        ("wrong_function", {**b_args, "function_handle": "clamp_score.function"}, "MISSION_EDIT_SCOPE"),
        ("wrong_original_value", {**b_args, "edits": [{**b_args["edits"][0], "expected_value": 59}]}, "MISSION_LITERAL_VALUES"),
        ("stale_revision", {**b_args, "expected_revision": 3}, "STALE_REVISION"),
        ("ambiguous_path", {**b_args, "edits": [{**b_args["edits"][0], "target": {**b_args["edits"][0]["target"], "expression_path": [99]}}]}, "MISSION_EDIT_TARGETS"),
        ("unauthorized_dependent_function", {**b_args, "edits": [{**b_args["edits"][0], "target": {**b_args["edits"][0]["target"], "function_handle": "clamp_score.function"}}]}, "MISSION_EDIT_TARGETS"),
        ("unknown_semantic_field", {**b_args, "extra": True}, "INVALID_EDIT_REQUEST"),
        ("invalid_partial_batch", {**b_args, "edits": [b_args["edits"][0], {**b_args["edits"][0], "expected_value": 60}]}, "MISSION_EDIT_COUNT"),
    ]
    for name, request, expected_code in invalids:
        case = out / f"negative-{name}"; gateway = Gateway(case, b_contract, mission_b=True)
        try:
            if name != "undiscovered_handle":
                discovered = call("127.0.0.1", gateway.ready["port"], "discover_functions", {}, f"{name}-discover")
                if not discovered.get("ok"):
                    raise RuntimeError(f"control setup failed: {name}")
            response = call("127.0.0.1", gateway.ready["port"], "preview_semantic_edit", request, name)
            payload = response.get("result", {})
            code = payload.get("code") or response.get("error", {}).get("code")
            if code != expected_code:
                raise RuntimeError(f"{name}: expected {expected_code}, got {response}")
            status = call("127.0.0.1", gateway.ready["port"], "get_status", {}, f"{name}-status")
            if status["result"]["revision"] != 4 or status["result"]["committed"]:
                raise RuntimeError(f"rejected control {name} mutated Workspace")
            controls.append({"name": name, "expected_code": expected_code, "observed_code": code,
                "revision_unchanged": True, "transport_correlation": name})
        finally:
            gateway.close()

    # The schema rejects missing expression_path and additional semantic fields
    # before any gateway call; test exact active ExtensionAPI schema.
    import jsonschema
    jsonschema.validate(b_args, preview_schema)
    missing_path = json.loads(json.dumps(b_args)); missing_path["edits"][0]["target"].pop("expression_path")
    missing_errors = list(jsonschema.Draft202012Validator(preview_schema).iter_errors(missing_path))
    unknown_field = json.loads(json.dumps(b_args)); unknown_field["edits"][0]["unexpected"] = 1
    unknown_errors = list(jsonschema.Draft202012Validator(preview_schema).iter_errors(unknown_field))
    if not missing_errors or not unknown_errors:
        raise RuntimeError("Pi schema did not reject missing path or unsupported edit fields")
    schema_case = out / "schema-negative-missing-path"; schema_case.mkdir()
    schema_gateway = Gateway(schema_case, b_contract, mission_b=True)
    try:
        typebox_result = extension_probe(schema_case, schema_gateway.ready, missing_path, schema_expected=schema_map)
        if typebox_result.get("schema_ok") is not False or typebox_result.get("stage") != "pi_typescript_schema":
            raise RuntimeError("actual TypeBox handler probe did not reject missing expression_path")
    finally:
        schema_gateway.close()
    unknown_schema_case = out / "schema-negative-unknown-edit-field"; unknown_schema_case.mkdir()
    unknown_schema_gateway = Gateway(unknown_schema_case, b_contract, mission_b=True)
    try:
        typebox_unknown = extension_probe(unknown_schema_case, unknown_schema_gateway.ready, unknown_field,
            schema_expected=schema_map)
        if typebox_unknown.get("schema_ok") is not False or typebox_unknown.get("stage") != "pi_typescript_schema":
            raise RuntimeError("actual TypeBox handler probe did not reject an unsupported edit field")
        state = call("127.0.0.1", unknown_schema_gateway.ready["port"], "get_status", {}, "schema-unknown-status")
        if state["result"]["revision"] != 4 or state["result"]["committed"]:
            raise RuntimeError("schema rejection changed authoritative Workspace state")
    finally:
        unknown_schema_gateway.close()
    write(out / "preflight-summary.json", {"schema": "basic-workspace.cycle21-maintenance-preflight", "version": 1,
        "inference_performed": False, "active_tools": inventory["tools"],
        "active_pi_schema_bytes": (schema_dir / "tool-schemas.json").stat().st_size,
        "schema_source": str(schema_dir), "mission_a_historical_proposals": a_previews,
        "mission_a_disposable_commit_validation_replay": "passed",
        "mission_b_disposable_commit_validation_replay": "passed",
        "mission_b_candidate_results": committed_b["validation"]["observed_results"],
        "negative_controls": controls, "missing_expression_path_rejected_by_active_schema": True,
        "unknown_edit_field_rejected_by_active_schema": True,
        "transport_correlation_recorded": True, "all_preflight_checks_passed": True})
    print(json.dumps(read(out / "preflight-summary.json"), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
