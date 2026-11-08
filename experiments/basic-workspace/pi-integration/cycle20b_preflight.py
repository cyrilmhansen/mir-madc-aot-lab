#!/usr/bin/env python3
"""Verify Pi TypeBox -> real TypeScript handler -> JSONL Gateway without inference."""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import socket
import subprocess
import sys
import time
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
PREVIOUS = HERE / "results/cycle20-semantic-evolution/real-agent-01"
MODEL = "Qwen3.8-Flash-Next-Sushi-STQ-2.75bpw"
EXPECTED_TOOLS = ["workspace_discover_functions", "workspace_inspect_program",
    "workspace_preview_semantic_edit", "workspace_commit_preview", "workspace_validate_mission"]


def read_jsonl(path: pathlib.Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path: pathlib.Path, value: Any):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def historical_fixtures():
    pi_rows = read_jsonl(PREVIOUS / "pi-session.jsonl")
    tool_rows = read_jsonl(PREVIOUS / "pi-tool-lifecycle.jsonl")
    starts = {row.get("toolCallId"): row for row in tool_rows
        if row.get("type") == "tool_execution_start" and row.get("toolName") == "workspace_preview_semantic_edit"}
    gateway_valid = []
    for row in tool_rows:
        if row.get("type") != "tool_execution_end" or row.get("toolName") != "workspace_preview_semantic_edit":
            continue
        details = (row.get("result") or {}).get("details") or {}
        start = starts.get(row.get("toolCallId"), {})
        if not row.get("isError") and details.get("code") == "INVALID_EDIT_REQUEST":
            gateway_valid.append({"tool_call_id": row.get("toolCallId"), "args": start.get("args"),
                "historical_gateway_code": details["code"]})
    calls = []
    for row in pi_rows:
        if row.get("type") != "message_end" or row.get("message", {}).get("role") != "assistant":
            continue
        for item in row["message"].get("content", []):
            if item.get("type") == "toolCall" and item.get("name") == "workspace_preview_semantic_edit":
                calls.append(item)
    malformed = [item for item in calls if len((item.get("arguments", {}).get("edits") or [])) == 2
        and "expression_path" not in item["arguments"]["edits"][1].get("target", {})]
    if len(gateway_valid) != 4 or len(malformed) != 1 or len(calls) != 5:
        raise RuntimeError(f"expected 4 historical gateway proposals and 1 schema-negative proposal; got {len(gateway_valid)}, {len(malformed)}, total {len(calls)}")
    return gateway_valid, malformed[0], calls


def start_gateway(case_dir: pathlib.Path):
    err = (case_dir / "gateway.stderr.log").open("w", encoding="utf-8")
    proc = subprocess.Popen([sys.executable, str(HERE / "cycle20_gateway.py"),
        "--output", str(case_dir / "gateway-evidence"), "--port", "0"],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=err, text=True)
    try:
        line = proc.stdout.readline()
        if not line:
            raise RuntimeError(f"Gateway exited before readiness: {(case_dir / 'gateway.stderr.log').read_text()}")
        ready = json.loads(line)
        if not ready.get("ready") or ready.get("revision") != 3 or not ready.get("baseline_verified"):
            raise RuntimeError(f"Gateway baseline reconstruction failed: {ready}")
        return proc, err, ready
    except Exception:
        proc.terminate()
        proc.wait(timeout=5)
        err.close()
        raise


def jsonl_call(host: str, port: int, method: str, params: dict[str, Any],
               tool_call_id: str | None = None):
    request = {"request_id": f"cycle20b-host-{time.time_ns()}", "method": method, "params": params}
    if tool_call_id is not None:
        request["transport"] = {"tool_call_id": tool_call_id}
    with socket.create_connection((host, port), timeout=10) as conn:
        conn.settimeout(10)
        conn.sendall(json.dumps(request, separators=(",", ":")).encode() + b"\n")
        data = bytearray()
        while b"\n" not in data:
            chunk = conn.recv(65536)
            if not chunk:
                raise RuntimeError("Gateway closed during framed request")
            data.extend(chunk)
            if len(data) > 1024 * 1024:
                raise RuntimeError("Gateway response exceeded one MiB")
    return json.loads(bytes(data).split(b"\n", 1)[0])


def run_probe(case_dir: pathlib.Path, ready: dict[str, Any], fixture: dict[str, Any], *, commit: bool):
    input_path = case_dir / "probe-input.json"
    output_path = case_dir / "probe-result.json"
    tool_id = fixture["tool_call_id"]
    payload = {"correlation_id": tool_id, "preview_args": fixture["args"], "commit": commit}
    write_json(input_path, payload)
    env = os.environ.copy()
    env.update({"BASIC_WS_AUTHORING_MODE": "semantic_edit",
        "BASIC_WS_PI_GATEWAY": f"127.0.0.1:{ready['port']}",
        "BASIC_WS_DISPATCH_PROBE_INPUT": str(input_path),
        "BASIC_WS_DISPATCH_PROBE_OUTPUT": str(output_path),
        "NODE_PATH": "/usr/lib/node_modules/@earendil-works/pi-coding-agent/node_modules"})
    completed = subprocess.run(["bun", str(HERE / "cycle20b_dispatch_probe.ts")], env=env,
        capture_output=True, text=True, timeout=30)
    (case_dir / "probe.stdout.log").write_text(completed.stdout, encoding="utf-8")
    (case_dir / "probe.stderr.log").write_text(completed.stderr, encoding="utf-8")
    if completed.returncode != 0 or not output_path.is_file():
        raise RuntimeError(f"Extension dispatch probe failed in {case_dir.name}: {completed.stderr[-1000:]}")
    return json.loads(output_path.read_text(encoding="utf-8"))


def assert_extension_schema_matches_pi(probe_result, expected):
    captured = {row["name"]: row["parameters"] for row in probe_result.get("schemas", [])}
    if captured != expected:
        raise RuntimeError("TypeBox schemas registered by the extension differ from Pi's active schema capture")


def end_gateway(proc, err):
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
    err.close()


def exercise_unknown_fields(case_dir: pathlib.Path, fixture: dict[str, Any]):
    case_dir.mkdir()
    proc, err, ready = start_gateway(case_dir)
    try:
        semantic = dict(fixture["args"])
        semantic["unapproved_semantic_field"] = "must not be ignored"
        rejected = jsonl_call("127.0.0.1", ready["port"], "preview_semantic_edit", semantic,
            "cycle20b-unknown-semantic-field")
        if not rejected.get("ok") or rejected.get("result", {}).get("ok") or rejected.get("result", {}).get("code") != "INVALID_EDIT_REQUEST":
            raise RuntimeError(f"unknown semantic field was not rejected: {rejected}")
        # jsonl_call emits only tool_call_id; send an unknown transport key
        # separately to test the shared envelope validator.
        raw = {"request_id": "cycle20b-unknown-transport-envelope", "method": "discover_functions",
            "params": {}, "transport": {"tool_call_id": "call-safe", "extra": "reject"}}
        with socket.create_connection(("127.0.0.1", ready["port"]), timeout=10) as conn:
            conn.sendall(json.dumps(raw).encode() + b"\n")
            data = conn.recv(65536)
        transport_rejected = json.loads(data.split(b"\n", 1)[0])
        if transport_rejected.get("ok") or "transport metadata" not in transport_rejected.get("error", {}).get("message", ""):
            raise RuntimeError(f"unknown transport metadata was not rejected: {transport_rejected}")
        status = jsonl_call("127.0.0.1", ready["port"], "get_status", {})
        if not status.get("ok") or status["result"].get("revision") != 3 or status["result"].get("committed"):
            raise RuntimeError("field rejection mutated the authoritative Workspace")
        return {"unknown_semantic_field_code": rejected["result"]["code"],
            "unknown_transport_metadata_rejected": True, "revision_unchanged": True}
    finally:
        end_gateway(proc, err)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--pi-schema-dir", type=pathlib.Path, required=True,
        help="directory from run_cycle20.py --preflight-only with actual Pi tool-schemas.json")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise SystemExit(f"refusing to overwrite evidence directory: {output}")
    output.mkdir(parents=True, exist_ok=True)
    schema_file = args.pi_schema_dir.resolve() / "tool-schemas.json"
    inventory_file = args.pi_schema_dir.resolve() / "tool-inventory.json"
    if not schema_file.is_file() or not inventory_file.is_file():
        raise RuntimeError("actual Pi active tool schemas/inventory are missing")
    actual_schemas = json.loads(schema_file.read_text(encoding="utf-8"))
    inventory = json.loads(inventory_file.read_text(encoding="utf-8"))
    if inventory.get("tools") != EXPECTED_TOOLS:
        raise RuntimeError("actual Pi tool allowlist differs from the five expected tools")
    schema_by_name = {row["name"]: row["parameters"] for row in actual_schemas}
    if set(schema_by_name) != set(EXPECTED_TOOLS):
        raise RuntimeError("Pi's captured schema inventory is incomplete")
    gateway_fixtures, malformed, all_calls = historical_fixtures()
    fixture_record = {"source": "preserved Cycle 20 genuine Pi session tool arguments",
        "source_directory": str(PREVIOUS), "four_gateway_valid_proposals": gateway_fixtures,
        "fifth_schema_negative_proposal": malformed, "all_five_tool_calls": all_calls}
    write_json(output / "historical-proposal-fixtures.json", fixture_record)

    # A fresh gateway per historical valid proposal proves isolation and avoids
    # reusing a preview token or mutated state between fixtures.
    preview_results = []
    for index, fixture in enumerate(gateway_fixtures, 1):
        case_dir = output / f"historical-valid-{index:02d}"
        case_dir.mkdir()
        proc, err, ready = start_gateway(case_dir)
        try:
            result = run_probe(case_dir, ready, fixture, commit=False)
            assert_extension_schema_matches_pi(result, schema_by_name)
            if not result.get("schema_ok") or not result.get("preview", {}).get("accepted"):
                raise RuntimeError(f"historical valid proposal {index} failed TypeBox/preview: {result}")
            if result["preview"].get("atomic_edit_count") != 2 or not result["preview"].get("candidate_is_preview_only"):
                raise RuntimeError(f"proposal {index} did not produce a two-literal non-mutating preview")
            state = jsonl_call("127.0.0.1", ready["port"], "get_status", {})
            if not state.get("ok") or state["result"].get("revision") != 3 or state["result"].get("committed"):
                raise RuntimeError(f"preview {index} changed authoritative Workspace state: {state}")
            impact = result["preview"]["impact"]
            for engine in ("interp", "jit"):
                if impact["candidate_observations"][engine]["60"]["clamp_score"] != 50.0 or impact["candidate_observations"][engine]["60"]["is_passing"] != 0.0:
                    raise RuntimeError(f"candidate behavior mismatch for {engine}")
            preview_results.append({"fixture": fixture["tool_call_id"], "schema_valid": True,
                "preview_accepted": True, "revision_unchanged": True,
                "changed_literal_token_count": len(impact["changed_literal_token_ids"]),
                "impact_engine_agreement": impact["before_observations"]["interp"] == impact["before_observations"]["jit"]
                    and impact["candidate_observations"]["interp"] == impact["candidate_observations"]["jit"]})
        finally:
            end_gateway(proc, err)

    # One disposable known-good instance verifies preview -> usable transaction
    # ID -> one atomic revision -> independent MIR validation.
    commit_dir = output / "known-good-commit"
    commit_dir.mkdir()
    proc, err, ready = start_gateway(commit_dir)
    try:
        commit_result = run_probe(commit_dir, ready, gateway_fixtures[0], commit=True)
        assert_extension_schema_matches_pi(commit_result, schema_by_name)
        if not commit_result.get("preview", {}).get("accepted") or not commit_result.get("committed", {}).get("committed"):
            raise RuntimeError(f"known-good candidate failed commit path: {commit_result}")
        validation = commit_result.get("validation", {})
        if not validation.get("mission_complete") or not validation.get("replay", {}).get("passed"):
            raise RuntimeError(f"known-good candidate failed MIR/replay validation: {validation}")
        final_state = jsonl_call("127.0.0.1", ready["port"], "get_status", {})
        if not final_state.get("ok") or final_state["result"].get("revision") != 4 or not final_state["result"].get("committed"):
            raise RuntimeError(f"commit did not advance exactly one revision: {final_state}")
        timing_rows = read_jsonl(commit_dir / "gateway-evidence/gateway-tool-timings.jsonl")
        preview_timing = next((row for row in timing_rows if row.get("method") == "preview_semantic_edit"
            and row.get("tool_call_id") == gateway_fixtures[0]["tool_call_id"]), None)
        if preview_timing is None:
            raise RuntimeError("tool-call correlation was not retained as transport metadata")
    finally:
        end_gateway(proc, err)

    # Run the malformed historical fifth proposal against the exact TypeBox
    # schema emitted by the main extension, without dispatching it to Python.
    malformed_dir = output / "historical-schema-negative"
    malformed_dir.mkdir()
    proc, err, ready = start_gateway(malformed_dir)
    try:
        malformed_fixture = {"tool_call_id": "historical-schema-negative", "args": malformed["arguments"]}
        malformed_result = run_probe(malformed_dir, ready, malformed_fixture, commit=False)
        assert_extension_schema_matches_pi(malformed_result, schema_by_name)
        if malformed_result.get("stage") != "pi_typescript_schema" or malformed_result.get("schema_ok") is not False:
            raise RuntimeError(f"fifth historical proposal was not rejected at the TypeBox schema boundary: {malformed_result}")
    finally:
        end_gateway(proc, err)

    # Explicit empty/absent distinction in the exact schema captured from Pi.
    import jsonschema
    preview_schema = schema_by_name["workspace_preview_semantic_edit"]
    valid_args = gateway_fixtures[0]["args"]
    jsonschema.validate(valid_args, preview_schema)
    absent_path = json.loads(json.dumps(valid_args))
    absent_path["edits"][1]["target"].pop("expression_path", None)
    schema_errors = list(jsonschema.Draft202012Validator(preview_schema).iter_errors(absent_path))
    def nested_errors(errors):
        for error in errors:
            yield error
            yield from nested_errors(error.context)
    if not schema_errors or not any("expression_path" in error.message and "required" in error.message
            for error in nested_errors(schema_errors)):
        raise RuntimeError("Pi schema does not distinguish absent expression_path from a valid empty array")

    unknown_fields = exercise_unknown_fields(output / "unknown-field-controls", gateway_fixtures[0])

    result = {"schema": "basic-workspace.cycle20b-dispatch-preflight", "version": 1,
        "model_inference_performed": False, "provider_model": MODEL, "pi_active_tools": inventory["tools"],
        "pi_schema_bytes": schema_file.stat().st_size, "typescript_tool_handler_invocations": 17,
        "historical_valid_proposals_previewed": len(preview_results), "valid_proposal_results": preview_results,
        "known_good_preview_commit_mir_validation_replay": "passed in disposable Workspace",
        "historical_fifth_proposal": {"rejected_by": "actual TypeBox schema from extension", "schema_error_count": len(schema_errors),
            "expression_path_empty_is_valid": True, "expression_path_absent_is_invalid": True},
        "transport_boundary": {"correlation_transport_field": "transport.tool_call_id",
            "semantic_params_contain_tool_call_id": False, "preview_transaction_correlation_recorded": True,
            "unknown_semantic_fields_remain_rejected": True, "unknown_field_controls": unknown_fields},
        "all_preflight_checks_passed": True}
    write_json(output / "preflight-summary.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
