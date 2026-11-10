#!/usr/bin/env python3
"""Model-free Cycle36 construction-to-maintenance bridge campaign."""
from __future__ import annotations

import argparse
import copy
import hashlib
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
RESULTS = HERE / "results/cycle36-verified-handoff"
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(HERE))
from basic_workspace.model import Workspace, WorkspaceError
from basic_workspace.projection import build_projection, projection_semantics
from basic_workspace.portable_replay import replay_constructive_stream
from basic_workspace.mir_execution import MirExecutionService
from cycle20_gateway import Cycle20Gateway
from run_cycle16 import gateway_call
from verified_handoff import build_handoff, verify_handoff

PROFILE = "basic-workspace.numeric-composition.v1"
EXECUTOR = MirExecutionService(timeout=20)
CREATION_TOOLS = {"workspace_discover_functions", "workspace_inspect_program", "workspace_preview_function",
    "workspace_commit_preview", "workspace_validate_mission"}
EDIT_TOOLS = {"workspace_discover_functions", "workspace_inspect_program", "workspace_preview_semantic_edit",
    "workspace_commit_preview", "workspace_validate_mission"}
INPUTS = {
    "mission-a": [-20, -1, 0, 1, 59, 60, 69, 70, 79, 80, 81, 89, 90, 99, 100, 101, 150],
    "mission-b": [-10, -1, 0, 18, 54, 55, 59, 60, 61, 64, 65, 80, 100, 150],
}


def read(path):
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def write(path, value):
    path = pathlib.Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def oracle(label, x):
    if label == "mission-a":
        bounded = min(100, max(0, x)); excellent = int(bounded >= 90)
        return {"bounded_score": float(bounded), "is_passing": float(bounded >= 60),
            "is_excellent": float(excellent), "high_priority": float(excellent)}
    normalized = min(100, max(0, x)); senior = int(normalized >= 65)
    return {"normalized_age": float(normalized), "is_senior": float(senior), "senior_flag": float(senior)}


def sequence_contract(label):
    names = (["BOUNDED_SCORE", "IS_PASSING", "IS_EXCELLENT", "HIGH_PRIORITY"] if label == "mission-a"
        else ["NORMALIZED_AGE", "IS_SENIOR", "SENIOR_FLAG"])
    handles = [name.lower() + ".function" for name in names]
    edges = ({"IS_PASSING": ["BOUNDED_SCORE"], "IS_EXCELLENT": ["BOUNDED_SCORE"],
              "HIGH_PRIORITY": ["IS_EXCELLENT"]} if label == "mission-a"
        else {"IS_SENIOR": ["NORMALIZED_AGE"], "SENIOR_FLAG": ["IS_SENIOR"]})
    inputs = INPUTS[label]; steps = []
    keys_by_count = names
    for index, name in enumerate(names):
        existing = names[:index]
        callee_names = edges.get(name, [])
        function_edges = [{"caller_handle": handles[index], "callee_handle": handles[names.index(callee)]}
            for callee in callee_names]
        expected = {str(x): {key.lower(): value for key, value in oracle(label, x).items()
            if key.upper() in keys_by_count[:index + 1]} for x in inputs}
        steps.append({"step_id": f"step-{index + 1:02d}-{name.lower()}",
            "mission_id": f"cycle36.{label}.{index + 1:02d}.v1", "expected_base_revision": index + 1,
            "function": {"name": name, "portable_handle": handles[index], "parameters": ["X"], "return_type": "numeric"},
            "required_callees": [handles[names.index(callee)] for callee in callee_names],
            "required_dependency_edges": function_edges,
            "required_existing_function_handles_unchanged": handles[:index],
            "validation": {"inputs": inputs, "expected_results": expected}})
    return {"schema": "basic-workspace.numeric-function-creation-sequence", "version": 1,
        "sequence_id": f"cycle36.{label}.creation.v1", "objective": f"Construct the Cycle36 {label} dependency program.",
        "execution_profile_id": PROFILE, "starting_revision": 1, "maximum_steps": 8, "steps": steps}


def fn_request(label, name):
    ref = lambda: {"kind": "local_ref", "name": "X"}
    number = lambda value: {"kind": "number", "value": value}
    assign = lambda expr: {"kind": "assign", "target": {"kind": "result"}, "expression": expr}
    binary = lambda op, left, right: {"kind": "binary", "operator": op, "left": left, "right": right}
    call = lambda handle: {"kind": "call", "function_handle": handle, "arguments": [ref()]}
    branch = lambda cond, value: {"kind": "if", "condition": cond, "then": [assign(number(value))]}
    if name in {"BOUNDED_SCORE", "NORMALIZED_AGE"}:
        body = [assign(ref()), branch(binary("<", ref(), number(0)), 0), branch(binary(">", ref(), number(100)), 100)]
    elif name in {"IS_PASSING", "IS_EXCELLENT"}:
        threshold = 60 if name == "IS_PASSING" else 90
        body = [assign(number(0)), branch(binary(">=", call("bounded_score.function"), number(threshold)), 1)]
    elif name == "HIGH_PRIORITY":
        body = [assign(number(0)), branch(binary(">=", call("is_excellent.function"), number(1)), 1)]
    elif name == "IS_SENIOR":
        body = [assign(number(0)), branch(binary(">=", call("normalized_age.function"), number(65)), 1)]
    elif name == "SENIOR_FLAG":
        body = [assign(number(0)), branch(binary(">=", call("is_senior.function"), number(1)), 1)]
    else:
        raise ValueError(name)
    return {"name": name, "parameters": ["X"], "body": body}


def stop(proc):
    if proc and proc.poll() is None:
        proc.terminate()
        try: proc.wait(timeout=5)
        except subprocess.TimeoutExpired: proc.kill(); proc.wait(timeout=5)


def dispatch(ready, request, outdir, mode):
    inp, result = outdir / "dispatch-input.json", outdir / "dispatch-output.json"
    write(inp, request)
    env = os.environ.copy(); env.update({"BASIC_WS_AUTHORING_MODE": mode,
        "BASIC_WS_PI_GATEWAY": f"127.0.0.1:{ready['port']}",
        "BASIC_WS_DISPATCH_PROBE_INPUT": str(inp), "BASIC_WS_DISPATCH_PROBE_OUTPUT": str(result),
        "NODE_PATH": "/usr/lib/node_modules/@earendil-works/pi-coding-agent/node_modules"})
    run = subprocess.run(["bun", str(HERE / "cycle20b_dispatch_probe.ts")], env=env,
        capture_output=True, text=True, timeout=90)
    (outdir / "dispatch.stdout.log").write_text(run.stdout, encoding="utf-8")
    (outdir / "dispatch.stderr.log").write_text(run.stderr, encoding="utf-8")
    if run.returncode or not result.is_file():
        raise RuntimeError(f"TypeScript production dispatch failed: {run.stderr[-2000:]}")
    return read(result)


def create_program(label, out):
    sequence = sequence_contract(label); seq_path = out / label / "creation-sequence.json"
    write(seq_path, sequence)
    arm = out / label / "creation"; evidence = arm / "gateway-evidence"
    arm.mkdir(parents=True); error = (arm / "gateway.stderr.log").open("w", encoding="utf-8")
    env = os.environ.copy(); env["PYTHONPATH"] = os.pathsep.join((str(ROOT), str(HERE), env.get("PYTHONPATH", "")))
    proc = subprocess.Popen([sys.executable, str(HERE / "cycle19_gateway.py"), "--output", str(evidence),
        "--port", "0", "--creation-sequence", str(seq_path)], stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=error, text=True, env=env)
    try:
        ready_line = proc.stdout.readline()
        if not ready_line: raise RuntimeError(f"creation gateway failed to start; see {arm/'gateway.stderr.log'}")
        ready = json.loads(ready_line)
        if not ready.get("ready") or ready.get("revision") != 1: raise RuntimeError(f"unexpected empty state: {ready}")
        revisions, schemas, steps = {}, None, []
        premature = gateway_call("127.0.0.1", ready["port"], "host_advance_creation_sequence", {"checkpoint": {}})
        if premature.get("code") != "SEQUENCE_STEP_NOT_VALIDATED": raise RuntimeError("host progression advanced before validation")
        for i, step in enumerate(sequence["steps"]):
            step_dir = arm / f"step-{i + 1:02d}"; step_dir.mkdir()
            args = {"expected_revision": step["expected_base_revision"], **fn_request(label, step["function"]["name"])}
            controls = [{**args, "name": "UNAUTHORIZED_FUNCTION"},
                {**args, "expected_revision": args["expected_revision"] - 1},
                {**args, "unknown_semantic_field": 1}]
            if step["required_callees"]:
                wrong = copy.deepcopy(args)
                def tamper_call(node):
                    if isinstance(node, dict):
                        if node.get("kind") == "call": node["function_handle"] = "invented.function"; return True
                        return any(tamper_call(child) for child in node.values())
                    if isinstance(node, list): return any(tamper_call(child) for child in node)
                    return False
                tamper_call(wrong["body"]); controls.append(wrong)
            result = dispatch(ready, {"authoring_mode": "atomic_create",
                "correlation_id": f"cycle36-{label}-{i}-{time.time_ns()}", "preview_args": args,
                "controls": controls, "commit": True}, step_dir, "atomic_create")
            if not result.get("schema_ok") or set(result.get("active_tools", [])) != CREATION_TOOLS:
                raise RuntimeError("creation schema or five-tool inventory mismatch")
            if schemas is None: schemas = result["schemas"]
            codes = [row.get("code") for row in result.get("controls", [])]
            if codes[:2] != ["MISSION_SIGNATURE", "STALE_REVISION"]:
                raise RuntimeError(f"creation negative controls failed: {codes}")
            if step["required_callees"] and codes[-1] != "MISSION_DEPENDENCY_REQUIRED":
                raise RuntimeError(f"dependency control failed: {codes}")
            if not result["preview"].get("candidate_is_preview_only") or result["preview"].get("base_revision") != i + 1:
                raise RuntimeError("creation preview changed state or used a stale revision")
            committed = result.get("committed", {})
            if not committed.get("committed") or committed.get("revision") != i + 2:
                raise RuntimeError(f"constructor did not commit exactly one revision: {committed}")
            host = gateway_call("127.0.0.1", ready["port"], "host_validate", {"expected_revision": i + 2})
            expected = step["validation"]["expected_results"]
            if not host.get("mission_complete") or not host.get("engines_agree"):
                raise RuntimeError(f"host validation failed at revision {i+2}: {host}")
            if host["observed_results"]["interp"] != expected or host["observed_results"]["jit"] != expected:
                raise RuntimeError(f"independent creation oracle mismatch at revision {i+2}")
            checkpoint = gateway_call("127.0.0.1", ready["port"], "create_checkpoint", {})
            if not checkpoint.get("ok"): raise RuntimeError(f"validated creation produced no checkpoint: {checkpoint}")
            advanced = gateway_call("127.0.0.1", ready["port"], "host_advance_creation_sequence", {"checkpoint": checkpoint["checkpoint"]})
            if not advanced.get("ok"): raise RuntimeError(f"host progression failed: {advanced}")
            revisions[str(i + 2)] = {"expected": expected, "interpreter": host["observed_results"]["interp"],
                "jit": host["observed_results"]["jit"], "revision": i + 2,
                "fingerprint": checkpoint["checkpoint"]["semantic_fingerprint"]}
            steps.append({"step_id": step["step_id"], "revision": i + 2, "portable_handle": committed["portable_handle"],
                "bound_callee_handles": committed["bound_callee_handles"], "preview_non_mutating": True,
                "schema_bytes_compact": len(json.dumps(result["schemas"], separators=(",", ":")).encode()),
                "rejected_controls": codes})
        status = gateway_call("127.0.0.1", ready["port"], "get_status", {})
        if not status.get("sequence_complete") or status.get("revision") != len(sequence["steps"]) + 1:
            raise RuntimeError(f"sequence incomplete: {status}")
        write(arm / "independent-oracle-observations.json", {"source": "cycle36_preflight.oracle",
            "input_corpus": INPUTS[label], "revisions": revisions})
        write(arm / "bridge-summary.json", {"bridge": "actual TypeScript extension handler -> JSONL -> Cycle19Gateway",
            "inference_performed": False, "tools": sorted(CREATION_TOOLS), "steps": steps,
            "final_revision": status["revision"], "function_count": len(status["function_handles"]),
            "host_progression_only": True, "premature_progression_rejected": premature.get("code"),
            "schemas": schemas})
        return {"sequence": sequence, "sequence_path": seq_path, "arm": arm, "evidence": evidence,
            "steps": steps, "observations": revisions, "schema": schemas, "final_revision": status["revision"]}
    finally:
        stop(proc); error.close()


def _replay_source(evidence):
    stream = read(evidence / "constructive-operations.json")
    ws = Workspace(); doc = ws.create_empty_document("memory://cycle36/targets.bas")["document_id"]
    replay = replay_constructive_stream(ws, doc, stream["operations"], expected_final_handles=stream["portable_handles"],
        expected_retired_handles=stream.get("retired_handles", []), expected_start_revision=1)
    raw = projection_semantics(build_projection(ws, doc, replay.revision))
    from cycle20_gateway import senior
    normalized = senior.normalized_state(raw, replay.live_handles)
    return stream, ws, doc, replay, normalized


def edit_contract(label, creation, mission_dir):
    stream, ws, doc, replay, baseline = _replay_source(creation["evidence"])
    if label == "mission-a":
        functions = {"bounded_score.function": ("BOUNDED_SCORE", "bounded_score"),
            "is_passing.function": ("IS_PASSING", "is_passing"),
            "is_excellent.function": ("IS_EXCELLENT", "is_excellent"),
            "high_priority.function": ("HIGH_PRIORITY", "high_priority")}
        cap_h, pass_h, excellent_h = "bounded_score.function", "is_passing.function", "is_excellent.function"
        cap_name, threshold_old, threshold_new, cap_new, maximum, excellent_threshold = "BOUNDED_SCORE", 60, 70, 80, 80, 90
        edges = [(pass_h, cap_h), (excellent_h, cap_h), ("high_priority.function", excellent_h)]
        objective = "Cap BOUNDED_SCORE at 80 and set IS_PASSING's threshold to 70 in one atomic edit."
    else:
        functions = {"normalized_age.function": ("NORMALIZED_AGE", "normalized_age"),
            "is_senior.function": ("IS_SENIOR", "is_senior"), "senior_flag.function": ("SENIOR_FLAG", "senior_flag")}
        cap_h, pass_h, excellent_h = "normalized_age.function", "is_senior.function", None
        cap_name, threshold_old, threshold_new, cap_new, maximum, excellent_threshold = "NORMALIZED_AGE", 65, 55, 60, 60, None
        edges = [(pass_h, cap_h), ("senior_flag.function", pass_h)]
        objective = "Cap NORMALIZED_AGE at 60 and set IS_SENIOR's threshold to 55 in one atomic edit."
    # Construct explicit target paths from the typed, replayed baseline. The
    # actual Cycle20 contract constructor re-resolves every path and old value.
    state = baseline
    control_index = 2 if label == "mission-a" else 2
    comparison = {"function_handle": cap_h, "control_path": [{"block": "body", "index": control_index}], "expression_path": [1]}
    _fn, _statement, selected = Cycle20Gateway._target_expression(state, comparison)
    if float(selected["value"]) != 100: raise RuntimeError("cap comparison path was not verified against the typed baseline")
    statement_candidates = []
    for handle in stream["portable_handles"]:
        if handle.startswith(cap_h.rsplit(".", 1)[0] + ".statement."):
            target = {"function_handle": cap_h, "statement_handle": handle, "expression_path": []}
            try:
                _f, _s, selected = Cycle20Gateway._target_expression(state, target)
                if float(selected["value"]) == 100: statement_candidates.append(target)
            except WorkspaceError:
                pass
    if len(statement_candidates) != 1: raise RuntimeError(f"expected one cap result statement, found {statement_candidates}")
    passing_target = {"function_handle": pass_h,
        "control_path": [{"block": "body", "index": 1}], "expression_path": [1]}
    _fn, _statement, selected = Cycle20Gateway._target_expression(state, passing_target)
    if float(selected["value"]) != threshold_old: raise RuntimeError("threshold target path did not match the expected old value")
    targets = [
        {"target": comparison, "expected_original_value": 100,
         "replacement_constraint": {"kind": "one_of", "values": [cap_new]}, "label": f"{cap_name} upper comparison"},
        {"target": statement_candidates[0], "expected_original_value": 100,
         "replacement_constraint": {"kind": "one_of", "values": [cap_new]}, "label": f"{cap_name} upper result"},
        {"target": passing_target, "expected_original_value": threshold_old,
         "replacement_constraint": {"kind": "one_of", "values": [threshold_new]}, "label": f"{functions[pass_h][0]} threshold"}]
    validation_functions = []
    for handle, (name, key) in functions.items():
        if handle == cap_h:
            spec = {"kind": "clamp", "minimum": 0, "maximum": maximum}
        elif label == "mission-a" and handle == "is_passing.function":
            spec = {"kind": "threshold_call", "callee_handle": cap_h, "threshold": threshold_new, "true_value": 1, "false_value": 0}
        elif label == "mission-a" and handle == "is_excellent.function":
            spec = {"kind": "threshold_call", "callee_handle": cap_h, "threshold": excellent_threshold, "true_value": 1, "false_value": 0}
        elif label == "mission-b" and handle == "is_senior.function":
            spec = {"kind": "threshold_call", "callee_handle": cap_h, "threshold": threshold_new, "true_value": 1, "false_value": 0}
        else:
            callee = "is_excellent.function" if label == "mission-a" else "is_senior.function"
            spec = {"kind": "threshold_call", "callee_handle": callee,
                "threshold": 1, "true_value": 1, "false_value": 0}
        validation_functions.append({"function_handle": handle, "result_key": key, "oracle": spec})
    contract = {"schema": "basic-workspace.numeric-literal-maintenance-contract", "version": 2,
        "scope_mode": "per_target", "mission_id": f"cycle36.{label}.maintenance.v1", "objective": objective,
        "base_document_revision": creation["final_revision"], "execution_profile_id": PROFILE,
        "allowed_function_handles": [cap_h, pass_h], "authorized_targets": targets,
        "minimum_edits": 3, "maximum_edits": 3,
        "unchanged_function_handles": [handle for handle in functions if handle not in {cap_h, pass_h}],
        "required_dependency_edges": [{"caller_handle": caller, "callee_handle": callee} for caller, callee in edges],
        "revision_increment": 1, "validation": {"inputs": INPUTS[label], "functions": validation_functions}}
    path = mission_dir / "maintenance-contract.json"; write(path, contract)
    return path, contract


def expected_all(label, maintained, x):
    if label == "mission-a":
        cap = 80 if maintained else 100; passing = 70 if maintained else 60
        score = min(cap, max(0, x)); excellent = int(score >= 90)
        return {"bounded_score": float(score), "is_passing": float(score >= passing),
            "is_excellent": float(excellent), "high_priority": float(excellent)}
    cap = 60 if maintained else 100; threshold = 55 if maintained else 65
    age = min(cap, max(0, x)); senior = int(age >= threshold)
    return {"normalized_age": float(age), "is_senior": float(senior), "senior_flag": float(senior)}


def observe_all(ws, doc, revision, aliases, values):
    observed = {"interp": {}, "jit": {}}
    for engine in observed:
        for value in values:
            names = {"bounded_score.function": "bounded_score", "is_passing.function": "is_passing",
                "is_excellent.function": "is_excellent", "high_priority.function": "high_priority",
                "normalized_age.function": "normalized_age", "is_senior.function": "is_senior",
                "senior_flag.function": "senior_flag"}
            row = {names[handle]: EXECUTOR.execute_function(ws, doc, revision, aliases[handle], [value], engine)["result"]
                for handle in aliases if handle in names}
            observed[engine][str(value)] = row
    return observed


def run_maintenance(label, creation, out):
    mission_dir = out / label; contract_path, contract = edit_contract(label, creation, mission_dir)
    source = creation["evidence"]
    handoff_dir = mission_dir / "handoff"; handoff_path = handoff_dir / "handoff.json"; anchor_path = handoff_dir / "host-trust-anchor.json"
    bundle, anchor = build_handoff(source, creation["sequence_path"], contract_path, handoff_path, anchor_path)
    evidence = mission_dir / "maintenance" / "gateway-evidence"; evidence.parent.mkdir(parents=True, exist_ok=True)
    error = (mission_dir / "maintenance" / "gateway.stderr.log").open("w", encoding="utf-8")
    env = os.environ.copy(); env["PYTHONPATH"] = os.pathsep.join((str(ROOT), str(HERE), env.get("PYTHONPATH", "")))
    proc = subprocess.Popen([sys.executable, str(HERE / "cycle20_gateway.py"), "--output", str(evidence), "--contract", str(contract_path),
        "--verified-handoff", str(handoff_path), "--handoff-anchor", str(anchor_path), "--handoff-evidence-root", str(source), "--port", "0"],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=error, text=True, env=env)
    try:
        line = proc.stdout.readline()
        if not line: raise RuntimeError(f"maintenance gateway failed to start: {error.name}")
        ready = json.loads(line)
        if not ready.get("ready") or ready.get("revision") != creation["final_revision"] or not ready.get("baseline_verified"):
            raise RuntimeError(f"maintenance receiver did not authenticate the handoff: {ready}")
        if not read(evidence / "verified-handoff.json").get("passed"): raise RuntimeError("handoff verification receipt missing")
        replayed_start = gateway_call("127.0.0.1", ready["port"], "get_status", {})
        if replayed_start.get("revision") != creation["final_revision"]: raise RuntimeError("reconstructed revision mismatch")
        before = read(evidence / "baseline-observations.json")["observed_results"]
        expected_before = {str(x): expected_all(label, False, x) for x in INPUTS[label]}
        if before.get("interp") != expected_before or before.get("jit") != expected_before:
            raise RuntimeError("freshly reconstructed baseline differs from independent creation oracle")
        # Discovery is performed through actual TS handlers by the dispatch
        # probe; acquire target descriptors from the authenticated contract.
        edits = [{"target": row["target"], "expected_value": row["expected_original_value"],
            "replacement_value": row["replacement_constraint"]["values"][0]} for row in contract["authorized_targets"]]
        request = {"expected_revision": creation["final_revision"], "scope_mode": "per_target", "edits": edits}
        mixed = copy.deepcopy(request); mixed["edits"][2]["target"]["function_handle"] = "unauthorized.function"
        stale = copy.deepcopy(request); stale["expected_revision"] -= 1
        schema_legacy = copy.deepcopy(request); schema_legacy["function_handle"] = contract["allowed_function_handles"][0]
        transport = copy.deepcopy(request); transport["toolCallId"] = "transport-only"
        unknown = copy.deepcopy(request); unknown["edits"][0]["unexpected"] = True
        result = dispatch(ready, {"authoring_mode": "semantic_edit_multi",
            "correlation_id": f"cycle36-{label}-maintenance-{time.time_ns()}", "preview_args": request,
            "controls": [mixed, stale, schema_legacy, transport, unknown], "commit": True, "duplicate_commit": True},
            mission_dir / "maintenance", "semantic_edit_multi")
        if not result.get("ok"):
            raise RuntimeError(f"production TypeScript tool flow failed: {result.get('error')}")
        if not result.get("schema_ok") or set(result.get("active_tools", [])) != EDIT_TOOLS:
            raise RuntimeError("maintenance tool schema/inventory mismatch")
        control_codes = [row.get("code") for row in result.get("controls", [])]
        if control_codes[:2] != ["MISSION_EDIT_TARGETS", "STALE_REVISION"]:
            raise RuntimeError(f"maintenance authorization controls failed: {control_codes}")
        def keys_recursive(value):
            if isinstance(value, dict):
                return set(value) | set().union(*(keys_recursive(child) for child in value.values()))
            if isinstance(value, list): return set().union(*(keys_recursive(child) for child in value)) if value else set()
            return set()
        schema_fields = set().union(*(keys_recursive(row.get("arguments", {})) for row in result.get("schema_rejections", [])))
        if not {"function_handle", "toolCallId", "unexpected"}.issubset(schema_fields):
            raise RuntimeError(f"typed schema did not reject the expected fields: {schema_fields}")
        if not result["preview"].get("candidate_is_preview_only") or result["preview"].get("base_revision") != creation["final_revision"]:
            raise RuntimeError("maintenance preview mutated baseline or used wrong revision")
        if result.get("committed", {}).get("revision") != creation["final_revision"] + 1:
            raise RuntimeError("maintenance did not commit all three edits in one revision")
        host = gateway_call("127.0.0.1", ready["port"], "host_validate", {"expected_revision": creation["final_revision"] + 1})
        expected_after = {str(x): expected_all(label, True, x) for x in INPUTS[label]}
        if not host.get("mission_complete") or host.get("observed_results", {}).get("interp") != expected_after or host.get("observed_results", {}).get("jit") != expected_after:
            raise RuntimeError(f"final independent host validation failed: {host.get('diagnostics')}")
        # Validate every prefix of the complete portable stream and execute it
        # independently through both MIR engines against the arithmetic oracle.
        final_stream = read(evidence / "constructive-operations.json")
        prefix_rows = {}
        for prefix in range(1, len(final_stream["operations"]) + 1):
            ws = Workspace(); doc = ws.create_empty_document(f"memory://cycle36/{label}/prefix-{prefix}.bas")["document_id"]
            replay = replay_constructive_stream(ws, doc, final_stream["operations"][:prefix], expected_start_revision=1)
            state = __import__("cycle20_gateway").senior.normalized_state(
                projection_semantics(build_projection(ws, doc, replay.revision)), replay.live_handles)
            observed = observe_all(ws, doc, replay.revision, replay.live_handles, INPUTS[label])
            maintained = prefix == len(final_stream["operations"])
            key_by_handle = {"bounded_score.function": "bounded_score", "is_passing.function": "is_passing",
                "is_excellent.function": "is_excellent", "high_priority.function": "high_priority",
                "normalized_age.function": "normalized_age", "is_senior.function": "is_senior", "senior_flag.function": "senior_flag"}
            present = {key_by_handle[handle] for handle in replay.live_handles if handle in key_by_handle}
            expect = {str(x): {key: value for key, value in expected_all(label, maintained, x).items() if key in present}
                for x in INPUTS[label]}
            if observed["interp"] != expect or observed["jit"] != expect:
                raise RuntimeError(f"replayed prefix revision {replay.revision} differs from independent oracle")
            prefix_rows[str(replay.revision)] = {"normalized_semantics": state, "portable_handles": sorted(replay.live_handles),
                "dependencies": sorted({(edge["caller"], edge["callee"]) for edge in __import__("cycle20_gateway")._call_edges(state)}),
                "interpreter": observed["interp"], "jit": observed["jit"], "oracle_match": True}
        write(mission_dir / "revision-prefix-equivalence.json", {"prefixes": prefix_rows,
            "full_stream_operations": len(final_stream["operations"]), "passed": True})
        write(mission_dir / "independent-oracle-observations.json", {"input_corpus": INPUTS[label],
            "before_expected": expected_before, "before_interpreter": before["interp"],
            "before_jit": before["jit"], "after_expected": expected_after,
            "after_interpreter": host["observed_results"]["interp"], "after_jit": host["observed_results"]["jit"],
            "independent_reference": "cycle36_preflight.expected_all", "all_agree": True})
        summary = {"production_bridge": "actual TypeScript extension handlers -> JSONL -> Cycle20Gateway",
            "inference_performed": False, "handoff_verified": True, "base_revision": creation["final_revision"],
            "preview_revision_unchanged": creation["final_revision"], "committed_revision": creation["final_revision"] + 1,
            "atomic_edits": len(edits), "active_tools": sorted(result["active_tools"]),
            "schema_bytes_compact": len(json.dumps(result["schemas"], separators=(",", ":")).encode()),
            "rejected_controls": control_codes, "duplicate_commit_code": result.get("duplicate_commit", {}).get("code"),
            "validation_passed": host["mission_complete"], "replay_passed": host["replay"]["passed"],
            "portable_identity_count": len(final_stream["portable_handles"]), "revision_prefixes": len(prefix_rows)}
        write(mission_dir / "maintenance-bridge-summary.json", summary)
        return {"contract": contract, "contract_path": contract_path, "handoff": bundle, "anchor": anchor,
            "bridge": summary, "host_validation": host, "prefixes": prefix_rows, "gateway_evidence": evidence}
    finally:
        stop(proc); error.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=pathlib.Path, default=RESULTS / "production-bridge")
    args = parser.parse_args(); out = args.output.resolve()
    if out.exists() and any(out.iterdir()): raise SystemExit(f"refusing to overwrite nonempty evidence: {out}")
    if not shutil.which("bun"): raise SystemExit("Bun is required for the real TypeScript bridge")
    out.mkdir(parents=True, exist_ok=True)
    creation_results, maintenance_results = {}, {}
    for label in ("mission-a", "mission-b"):
        creation = create_program(label, out)
        creation_results[label] = creation
        maintenance_results[label] = run_maintenance(label, creation, out)
    write(out / "bridge-validation.json", {"schema": "basic-workspace.cycle36-production-bridge",
        "version": 1, "inference_performed": False,
        "missions": {label: maintenance_results[label]["bridge"] for label in creation_results}, "passed": True})
    print(json.dumps({label: {"creation_revision": creation_results[label]["final_revision"],
        "maintenance_revision": maintenance_results[label]["bridge"]["committed_revision"], "passed": True}
        for label in creation_results}, indent=2))


if __name__ == "__main__": main()
