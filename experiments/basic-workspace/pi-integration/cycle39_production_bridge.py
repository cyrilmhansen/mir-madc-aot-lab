#!/usr/bin/env python3
"""Selected Cycle39 generated constructors through real Cycle19 TS/JSONL gateway."""
from __future__ import annotations

import argparse
import copy
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path[:0] = [str(ROOT), str(HERE)]

import cycle36_preflight as c36
from basic_workspace.model import Workspace
from basic_workspace.mir_execution import MirExecutionService
from basic_workspace.portable_replay import replay_constructive_stream
from basic_workspace.projection import build_projection, projection_semantics
from cycle19_gateway import PROFILE_ID
from cycle20_gateway import senior
from cycle39_differential_campaign import generate_cases, oracle_value
from run_cycle16 import gateway_call


TOOLS = {"workspace_discover_functions", "workspace_inspect_program", "workspace_preview_function",
         "workspace_commit_preview", "workspace_validate_mission"}
INPUTS = [-11, -1, 0, 1, 7, 8, 9, 17, 18, 19, 29, 30]
EXECUTOR = MirExecutionService(timeout=2)


def write(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def sequence_for(case):
    initial = case["initial_specification"]
    function_ops = case["operations"][:len(case["functions"])]
    handles = [row["portable_handle"] for row in case["functions"]]
    steps = []
    spec_by_handle = {row["handle"]: row["rule"] for row in initial["functions"]}
    for index, (fn, operation) in enumerate(zip(case["functions"], function_ops)):
        args = operation["arguments"]
        callees = sorted({call["function_handle"] for call in _walk(args["body"]) if call.get("kind") == "call"})
        available = handles[:index]
        expected_edges = [{"caller_handle": handles[index], "callee_handle": callee} for callee in callees]
        expected = {str(x): {case["functions"][j]["name"].casefold(): oracle_value(
            spec_by_handle, handles[j], x) for j in range(index + 1)} for x in INPUTS}
        steps.append({"step_id": f"{case['case_id']}-step-{index+1:02d}",
            "mission_id": f"cycle39.{case['case_id']}.production.{index+1:02d}",
            "expected_base_revision": index + 1,
            "function": {"name": args["name"], "portable_handle": handles[index],
                "parameters": args["parameters"], "return_type": "numeric"},
            "required_callees": callees, "required_dependency_edges": expected_edges,
            "required_existing_function_handles_unchanged": available,
            "validation": {"inputs": INPUTS, "expected_results": expected}})
    return {"schema": "basic-workspace.numeric-function-creation-sequence", "version": 1,
        "sequence_id": f"cycle39.{case['case_id']}.production-sequence.v1",
        "objective": f"Host-authorized generated constructor workload {case['case_id']}",
        "execution_profile_id": PROFILE_ID, "starting_revision": 1,
        "maximum_steps": max(1, len(steps)), "steps": steps}


def _walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values(): yield from _walk(child)
    elif isinstance(value, list):
        for child in value: yield from _walk(child)


def _stop(proc):
    if proc and proc.poll() is None:
        proc.terminate()
        try: proc.wait(timeout=5)
        except subprocess.TimeoutExpired: proc.kill(); proc.wait(timeout=5)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--count", type=int, default=16)
    args = parser.parse_args(); out = args.output.resolve(); out.mkdir(parents=True, exist_ok=True)
    if not 1 <= args.count <= 16: raise SystemExit("count must be 1..16")
    selected = generate_cases(16)[:args.count]
    rows = []
    for case in selected:
        arm = out / case["case_id"]; arm.mkdir(parents=True, exist_ok=True)
        sequence = sequence_for(case); contract_path = arm / "creation-sequence.json"
        write(contract_path, sequence)
        evidence = arm / "gateway-evidence"; err_path = arm / "gateway.stderr.log"
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join((str(ROOT), str(HERE), env.get("PYTHONPATH", "")))
        proc = subprocess.Popen([sys.executable, str(HERE / "cycle19_gateway.py"), "--output", str(evidence),
            "--port", "0", "--creation-sequence", str(contract_path)], stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=err_path.open("w", encoding="utf-8"), text=True, env=env)
        try:
            line = proc.stdout.readline()
            if not line: raise RuntimeError(f"Cycle19 did not start for {case['case_id']}")
            ready = json.loads(line)
            if ready.get("revision") != 1: raise RuntimeError(f"Expected empty rev1, got {ready}")
            premature = gateway_call("127.0.0.1", ready["port"], "host_advance_creation_sequence", {"checkpoint": {}})
            if premature.get("progress_advanced"): raise RuntimeError("Host progression advanced without a validated commit")
            step_rows = []
            for index, step in enumerate(sequence["steps"]):
                operation = case["operations"][index]
                request = {"expected_revision": index + 1, **copy.deepcopy(operation["arguments"])}
                unauthorized_name = copy.deepcopy(request); unauthorized_name["name"] = "UNAUTHORIZED_FUNCTION"
                controls = [{**request, "expected_revision": index}, unauthorized_name]
                if step["required_callees"]:
                    wrong_dependency = copy.deepcopy(request)
                    changed = False
                    for node in _walk(wrong_dependency["body"]):
                        if node.get("kind") == "call":
                            node["function_handle"] = "invented.function"; changed = True; break
                    if changed: controls.append(wrong_dependency)
                schema_bad = {**request, "unknown_semantic_field": True}
                dispatch_dir = arm / f"step-{index+1:02d}"; dispatch_dir.mkdir()
                dispatch_start = time.perf_counter()
                result = c36.dispatch(ready, {"authoring_mode": "atomic_create",
                    "correlation_id": f"cycle39-{case['case_id']}-{index+1:02d}",
                    "preview_args": request, "controls": controls + [schema_bad], "commit": True}, dispatch_dir, "atomic_create")
                dispatch_ms = (time.perf_counter() - dispatch_start) * 1000
                if not result.get("schema_ok") or set(result.get("active_tools", [])) != TOOLS:
                    raise RuntimeError("actual TypeScript schema/tool inventory mismatch")
                rejected = result.get("controls", [])
                expected_codes = ["STALE_REVISION", "MISSION_SIGNATURE"] + ( ["MISSION_DEPENDENCY_REQUIRED"] if step["required_callees"] else [] )
                if (len(rejected) != len(expected_codes) or [row.get("code") for row in rejected] != expected_codes
                        or any(row.get("revision") != index + 1 or row.get("authoritative_workspace_changed") is not False for row in rejected)):
                    raise RuntimeError(f"stale preview control changed state or had wrong classification: {rejected}")
                if len(result.get("schema_rejections", [])) != 1:
                    raise RuntimeError("unknown semantic field did not fail TypeScript schema validation")
                if result.get("preview", {}).get("base_revision") != index + 1:
                    raise RuntimeError("accepted preview was not bound to the current unchanged revision")
                if result["preview"].get("candidate_is_preview_only") is not True:
                    raise RuntimeError("preview did not report a temporary candidate")
                if result.get("committed", {}).get("revision") != index + 2:
                    raise RuntimeError("constructor did not advance exactly one revision")
                validation_start = time.perf_counter()
                host = gateway_call("127.0.0.1", ready["port"], "host_validate", {"expected_revision": index + 2})
                validation_ms = (time.perf_counter() - validation_start) * 1000
                expected = step["validation"]["expected_results"]
                if (not host.get("mission_complete") or host.get("engines_agree") is not True
                        or host["observed_results"]["interp"] != expected
                        or host["observed_results"]["jit"] != expected):
                    raise RuntimeError(f"host independent-profile validation failed at rev {index+2}")
                checkpoint_start = time.perf_counter()
                checkpoint = gateway_call("127.0.0.1", ready["port"], "create_checkpoint", {})
                advanced = gateway_call("127.0.0.1", ready["port"], "host_advance_creation_sequence",
                    {"checkpoint": checkpoint.get("checkpoint", {})})
                checkpoint_progression_ms = (time.perf_counter() - checkpoint_start) * 1000
                if not checkpoint.get("ok") or not advanced.get("ok"):
                    raise RuntimeError("checkpoint progression failed")
                step_rows.append({"revision": index + 2, "portable_handle": step["function"]["portable_handle"],
                    "dependency_edges": step["required_dependency_edges"], "schema_ok": True,
                    "preview_non_mutating": True, "host_validated": True, "checkpoint_advanced": True,
                    "negative_controls": [row.get("code") for row in result.get("controls", [])],
                    "schema_rejections": len(result.get("schema_rejections", [])),
                    "bridge_dispatch_ms": round(dispatch_ms, 3), "host_validation_ms": round(validation_ms, 3),
                    "checkpoint_and_progression_ms": round(checkpoint_progression_ms, 3)})
            status = gateway_call("127.0.0.1", ready["port"], "get_status", {})
            if not status.get("sequence_complete"):
                raise RuntimeError("configured sequence did not complete")
            stream = json.loads((evidence / "constructive-operations.json").read_text(encoding="utf-8"))
            rws = Workspace(); rdoc = rws.create_empty_document(f"memory://cycle39/bridge-replay/{case['case_id']}")["document_id"]
            replay = replay_constructive_stream(rws, rdoc, stream["operations"],
                expected_final_handles=stream["portable_handles"], expected_start_revision=1)
            rows.append({"case_id": case["case_id"], "family": case["family"], "steps": step_rows,
                "bridge": "TypeScript extension -> JSONL -> Cycle19Gateway",
                "final_revision": status["revision"], "sequence_complete": True,
                "portable_history_replayed": replay.revision == status["revision"],
                "function_count": len(case["functions"]), "handles": sorted(replay.live_handles)})
        finally:
            _stop(proc)
    output = {"schema": "basic-workspace.cycle39-production-bridge", "version": 1,
        "case_count": len(rows), "all_passed": all(row["portable_history_replayed"] for row in rows),
        "selection_method": "first 16 fixed-seed cases, round-robin across seven families",
        "workflows": rows}
    write(out / "production-bridge-summary.json", output)
    print(json.dumps({"workflows": len(rows), "all_passed": output["all_passed"]}, indent=2))
    if not output["all_passed"]: raise SystemExit(1)


if __name__ == "__main__": main()
