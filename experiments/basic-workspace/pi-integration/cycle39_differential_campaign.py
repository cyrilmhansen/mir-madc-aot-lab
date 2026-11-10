#!/usr/bin/env python3
"""Bounded Cycle39 generator, independent oracle, differential executor, and reducer."""
from __future__ import annotations

import argparse
import copy
import json
import random
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path[:0] = [str(ROOT), str(HERE)]

from basic_workspace.model import Workspace
from basic_workspace.mir_execution import MirExecutionService
from basic_workspace.portable_replay import PortableReplay, replay_constructive_stream
from basic_workspace.projection import build_projection, projection_semantics
from cycle20_gateway import senior


SEEDS = (39001, 39002, 39003, 39004)
VALID_CASES = 120
MAX_REDUCTIONS = 64
EXECUTOR = MirExecutionService(timeout=2)


def atom_num(value):
    return {"kind": "number", "value": value}


def atom_x():
    return {"kind": "local_ref", "name": "X"}


def atom_call(handle):
    return {"kind": "call", "function_handle": handle, "arguments": [atom_x()]}


def assign(expression):
    return {"kind": "assign", "target": {"kind": "result"}, "expression": expression}


def if_assign(left, operator, right, value):
    return {"kind": "if", "condition": {"kind": "binary", "operator": operator,
            "left": left, "right": right}, "then": [assign(atom_num(value))]}


def _function(name, portable, body, rule, callees=()):
    return {"name": name, "portable_handle": portable, "body": body, "rule": rule,
            "callees": list(callees)}


def make_program(case_number, family, rng):
    """Return one typed constructor history plus a separate math specification."""
    stem = f"CASE{case_number:03d}"
    lo = rng.randint(-12, 4)
    hi = rng.randint(max(lo + 2, 12), 40)
    # Numeric edit targets must be a directly-addressable literal. The
    # existing path editor addresses comparison RHS roots and does not edit
    # through a unary-minus node, so threshold edit targets stay positive.
    threshold = rng.randint(3, hi + 2)
    threshold2 = threshold + rng.choice((-2, -1, 1, 2))
    fn = []
    if family == "clamp":
        fn = [_function(stem + "_CLAMP", stem.lower() + ".function",
            [assign(atom_x()), if_assign(atom_x(), "<", atom_num(lo), lo),
             if_assign(atom_x(), ">", atom_num(hi), hi)],
            {"kind": "clamp", "lower": lo, "upper_condition": hi, "upper_result": hi})]
    elif family in ("threshold_ge", "threshold_lt"):
        op = ">=" if family == "threshold_ge" else "<"
        fn = [_function(stem + "_PRED", stem.lower() + ".function",
            [assign(atom_num(0)), if_assign(atom_x(), op, atom_num(threshold), 1)],
            {"kind": "predicate", "source": "x", "operator": op, "threshold": threshold})]
    elif family == "dependent_predicate":
        provider = stem + "_CLAMP"; ph = stem.lower() + "_provider.function"
        caller = stem + "_ACCEPTED"; ch = stem.lower() + "_accepted.function"
        fn = [_function(provider, ph, [assign(atom_x()), if_assign(atom_x(), "<", atom_num(0), 0),
              if_assign(atom_x(), ">", atom_num(hi), hi)],
              {"kind": "clamp", "lower": 0, "upper_condition": hi, "upper_result": hi}),
            _function(caller, ch, [assign(atom_num(0)), if_assign(atom_call(ph), ">=", atom_num(threshold), 1)],
              {"kind": "predicate", "source": ph, "operator": ">=", "threshold": threshold}, [ph])]
    elif family == "sequential_override":
        credit = stem + "_CREDIT"; minor = stem + "_MINOR"
        h1 = stem.lower() + "_credit.function"; h2 = stem.lower() + "_minor.function"
        out = stem + "_ELIGIBLE"; ho = stem.lower() + "_eligible.function"
        fn = [_function(credit, h1, [assign(atom_num(0)), if_assign(atom_x(), ">=", atom_num(0), 1)],
              {"kind": "predicate", "source": "x", "operator": ">=", "threshold": 0}),
            _function(minor, h2, [assign(atom_num(0)), if_assign(atom_x(), "<", atom_num(threshold), 1)],
              {"kind": "predicate", "source": "x", "operator": "<", "threshold": threshold}),
            _function(out, ho, [assign(atom_num(0)), if_assign(atom_call(h1), ">=", atom_num(1), 1),
              if_assign(atom_call(h2), ">=", atom_num(1), 0)],
              {"kind": "sequential", "initial": 0, "steps": [
                  {"source": h1, "operator": ">=", "threshold": 1, "value": 1},
                  {"source": h2, "operator": ">=", "threshold": 1, "value": 0}]}, [h1, h2])]
    elif family == "two_callees":
        h1 = stem.lower() + "_low.function"; h2 = stem.lower() + "_high.function"
        fn = [_function(stem + "_LOW", h1, [assign(atom_num(0)), if_assign(atom_x(), "<", atom_num(threshold), 1)],
              {"kind": "predicate", "source": "x", "operator": "<", "threshold": threshold}),
            _function(stem + "_HIGH", h2, [assign(atom_num(0)), if_assign(atom_x(), ">=", atom_num(threshold2), 1)],
              {"kind": "predicate", "source": "x", "operator": ">=", "threshold": threshold2}),
            _function(stem + "_EITHER", stem.lower() + "_either.function",
              [assign(atom_num(0)), if_assign(atom_call(h1), ">=", atom_num(1), 1),
               if_assign(atom_call(h2), ">=", atom_num(1), 1)],
              {"kind": "sequential", "initial": 0, "steps": [
                  {"source": h1, "operator": ">=", "threshold": 1, "value": 1},
                  {"source": h2, "operator": ">=", "threshold": 1, "value": 1}]}, [h1, h2])]
    elif family == "dependency_chain":
        handles = [stem.lower() + f"_level{i}.function" for i in range(1, 4)]
        fn = [_function(stem + "_L1", handles[0], [assign(atom_num(0)),
              if_assign(atom_x(), ">=", atom_num(threshold), 1)],
              {"kind": "predicate", "source": "x", "operator": ">=", "threshold": threshold}),
            _function(stem + "_L2", handles[1], [assign(atom_num(0)),
              if_assign(atom_call(handles[0]), ">=", atom_num(1), 1)],
              {"kind": "predicate", "source": handles[0], "operator": ">=", "threshold": 1}, [handles[0]]),
            _function(stem + "_L3", handles[2], [assign(atom_num(0)),
              if_assign(atom_call(handles[1]), ">=", atom_num(1), 1)],
              {"kind": "predicate", "source": handles[1], "operator": ">=", "threshold": 1}, [handles[1]])]
    else:
        raise ValueError(family)
    for row in fn:
        row["parameters"] = ["X"]
    spec = {"family": family, "functions": [{"handle": row["portable_handle"], "rule": row["rule"]} for row in fn],
            "mutation": None}
    initial_spec = copy.deepcopy(spec)
    operations = [{"operation": "create_numeric_function", "portable_handle": row["portable_handle"],
        "arguments": {"name": row["name"], "parameters": row["parameters"], "body": copy.deepcopy(row["body"])}}
        for row in fn]
    # Each history includes a real canonical rename and one revision-checked literal edit.
    rename_target = fn[0]
    renamed_name = rename_target["name"] + "_RENAMED"
    operations.append({"operation": "rename_symbol", "target_handle": rename_target["portable_handle"],
        "expected_name": rename_target["name"], "new_name": renamed_name})
    rename_target["renamed_name"] = renamed_name
    edit_target_index = len(fn) - 1
    target_fn = fn[edit_target_index]
    # The final top-level IF condition in every template has one numeric RHS.
    if_index = len(target_fn["body"]) - 1
    rhs = target_fn["body"][if_index]["condition"]["right"]
    if rhs.get("kind") != "number":
        raise AssertionError("generator selected a nonnumeric edit target")
    old = rhs["value"]
    delta = 1 if (case_number % 2 == 0) else -1
    replacement = old + delta
    if old < 0 and replacement >= 0:
        replacement = old - 1
    rhs["value"] = replacement
    target_portable = target_fn["portable_handle"]
    control_path = [{"block": "body", "index": if_index}]
    operations.append({"operation": "edit_numeric_literals", "mission_id": f"cycle39.case-{case_number:03d}.edit",
        "function_handle": target_portable, "edits": [{"target": {"function_handle": target_portable,
        "control_path": control_path, "expression_path": [1, 0] if old < 0 else [1]},
        "expected_value": abs(old) if old < 0 else old,
        "replacement_value": abs(replacement) if old < 0 else replacement}]})
    spec["mutation"] = {"kind": "threshold_rhs", "target_handle": target_portable,
        "function_index": edit_target_index, "old": old, "new": replacement, "if_index": if_index}
    # Apply rename and literal change to the independent mathematical definition.
    if edit_target_index == 0 and target_fn["rule"]["kind"] == "clamp":
        target_fn["rule"]["upper_condition"] = replacement
    elif target_fn["rule"]["kind"] == "predicate":
        target_fn["rule"]["threshold"] = replacement
    elif target_fn["rule"]["kind"] == "sequential":
        target_fn["rule"]["steps"][-1]["threshold"] = replacement
    return {"case_id": f"case-{case_number:03d}", "family": family, "functions": fn,
        "specification": spec, "initial_specification": initial_spec,
        "operations": operations, "generation_parameters": {
            "lower": lo, "upper": hi, "threshold": threshold, "second_threshold": threshold2,
            "edit_old": old, "edit_new": replacement}}


def generate_cases(count=VALID_CASES, seed_offset=0):
    families = ["clamp", "threshold_ge", "threshold_lt", "dependent_predicate",
                "sequential_override", "two_callees", "dependency_chain"]
    cases = []
    for index in range(count):
        seed = SEEDS[index % len(SEEDS)] + int(seed_offset) + index * 7919
        rng = random.Random(seed)
        family = families[index % len(families)]
        cases.append(make_program(index + 1, family, rng))
        cases[-1]["seed"] = seed
    return cases


def oracle_value(spec_by_handle, handle, x, memo=None):
    """Evaluate declared math rules only; this is not a BASIC or MIR evaluator."""
    memo = {} if memo is None else memo
    key = (handle, x)
    if key in memo:
        return memo[key]
    rule = spec_by_handle[handle]
    kind = rule["kind"]
    if kind == "clamp":
        result = rule["lower"] if x < rule["lower"] else x
        if x > rule["upper_condition"]:
            result = rule["upper_result"]
    elif kind == "predicate":
        source_value = x if rule["source"] == "x" else oracle_value(spec_by_handle, rule["source"], x, memo)
        result = float(compare(source_value, rule["operator"], rule["threshold"]))
    elif kind == "sequential":
        result = rule["initial"]
        for step in rule["steps"]:
            source_value = oracle_value(spec_by_handle, step["source"], x, memo)
            if compare(source_value, step["operator"], step["threshold"]):
                result = step["value"]
    else:
        raise ValueError(kind)
    memo[key] = float(result)
    return float(result)


def compare(a, op, b):
    return {"<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b}[op]


def input_corpus(case):
    params = case["generation_parameters"]
    values = {-17, -1, 0, 1, params["lower"] - 1, params["lower"], params["lower"] + 1,
              params["upper"] - 1, params["upper"], params["upper"] + 1,
              params["threshold"] - 1, params["threshold"], params["threshold"] + 1,
              params["second_threshold"] - 1, params["second_threshold"], params["second_threshold"] + 1}
    rng = random.Random(case["seed"] ^ 0x39C0FFEE)
    values.update(rng.randint(-30, 70) for _ in range(4))
    return sorted(values)


def fresh_replay(case):
    ws = Workspace()
    doc = ws.create_empty_document(f"memory://cycle39/{case['case_id']}.bas")["document_id"]
    replay = replay_constructive_stream(ws, doc, copy.deepcopy(case["operations"]),
        expected_final_handles=sorted([f["portable_handle"] for f in case["functions"]] +
            [f["portable_handle"].rsplit(".", 1)[0] + ".parameter.id" for f in case["functions"]] +
            [f"{f['portable_handle'].rsplit('.', 1)[0]}.statement.{i}" for f in case["functions"]
            for i in range(_statement_count(f["body"]) + 1)]), expected_start_revision=1)
    return ws, doc, replay


def _statement_count(body):
    count = 0
    for row in body:
        if row["kind"] == "assign": count += 1
        elif row["kind"] == "if": count += sum(1 for part in row.get("then", []) + row.get("else", []) if part["kind"] == "assign")
    return count


def run_case(case):
    expected_handles = sorted([f["portable_handle"] for f in case["functions"]] +
        [f["portable_handle"].rsplit(".", 1)[0] + ".parameter.id" for f in case["functions"]] +
        [f"{f['portable_handle'].rsplit('.', 1)[0]}.statement.{i}" for f in case["functions"]
         for i in range(_statement_count(f["body"]) + 1)])
    ws = Workspace(); doc = ws.create_empty_document(f"memory://cycle39/{case['case_id']}.bas")["document_id"]
    runner = PortableReplay(ws, doc)
    revision_rows = []
    for index, operation in enumerate(case["operations"]):
        runner.apply_operation(copy.deepcopy(operation), index=index)
        if ws.get_revision(doc) != index + 2:
            return {"case_id": case["case_id"], "classification": "revision_or_transaction_lifecycle_divergence",
                    "failing_revision": ws.get_revision(doc), "expected_revision": index + 2}
        if index < len(case["functions"]):
            revision_rows.append({"revision": index + 2, "function_count": index + 1,
                                  "live_function_handles": sorted(h for h in runner.aliases if h.endswith(".function"))})
    if sorted(runner.aliases) != expected_handles:
        return {"case_id": case["case_id"], "classification": "portable_identity_divergence",
                "expected_handles": expected_handles, "observed_handles": sorted(runner.aliases)}
    normalized = senior.normalized_state(
        projection_semantics(build_projection(ws, doc, ws.get_revision(doc))), runner.aliases)
    by_handle = {row["handle"]: row["rule"] for row in case["specification"]["functions"]}
    inputs = input_corpus(case)
    expected = {str(x): {handle: oracle_value(by_handle, handle, x) for handle in by_handle} for x in inputs}
    observed = {engine: {} for engine in ("interp", "jit")}
    try:
        for engine in observed:
            for x in inputs:
                observed[engine][str(x)] = {handle: EXECUTOR.execute_function(ws, doc, ws.get_revision(doc),
                    runner.aliases[handle], [x], engine)["result"] for handle in by_handle}
    except Exception as exc:
        return {"case_id": case["case_id"], "classification": "infrastructure_or_timeout_failure", "error": repr(exc)}
    for engine in observed:
        for x in inputs:
            if observed[engine][str(x)] != expected[str(x)]:
                return {"case_id": case["case_id"], "classification": "mir_interpreter_divergence" if engine == "interp" else "mir_jit_divergence",
                    "input": x, "engine": engine, "expected": expected[str(x)], "observed": observed[engine][str(x)],
                    "revision": ws.get_revision(doc), "operations": case["operations"]}
    replay_ws, replay_doc, replay = fresh_replay(case)
    replay_normalized = senior.normalized_state(
        projection_semantics(build_projection(replay_ws, replay_doc, replay.revision)), replay.live_handles)
    if normalized != replay_normalized or sorted(replay.live_handles) != expected_handles:
        return {"case_id": case["case_id"], "classification": "replay_structural_or_identity_divergence",
                "operations": case["operations"], "revision": ws.get_revision(doc)}
    replay_observed = {engine: {} for engine in ("interp", "jit")}
    for engine in replay_observed:
        for x in inputs:
            replay_observed[engine][str(x)] = {handle: EXECUTOR.execute_function(replay_ws, replay_doc,
                replay.revision, replay.live_handles[handle], [x], engine)["result"] for handle in by_handle}
            if replay_observed[engine][str(x)] != expected[str(x)]:
                return {"case_id": case["case_id"], "classification": "replayed_mir_divergence",
                    "input": x, "engine": engine, "expected": expected[str(x)], "observed": replay_observed[engine][str(x)]}
    return {"case_id": case["case_id"], "family": case["family"], "seed": case["seed"],
        "valid": True, "classification": "passed", "revision": ws.get_revision(doc),
        "function_count": len(case["functions"]), "dependency_edges": senior.candidate_call_edges(normalized),
        "portable_handles": expected_handles, "input_count": len(inputs), "inputs": inputs,
        "expected": expected, "interpreter": observed["interp"], "jit": observed["jit"],
        "replay_interpreter": replay_observed["interp"], "replay_jit": replay_observed["jit"],
        "replay_revision": replay.revision, "replay_equal": True, "revision_checkpoints": revision_rows}


def _edges(normalized):
    edges = []
    for fn in normalized["functions"]:
        def visit(value):
            if isinstance(value, dict):
                if value.get("kind") == "call": edges.append([fn.get("symbol_id"), value.get("function_id")])
                for child in value.values(): visit(child)
            elif isinstance(value, list):
                for child in value: visit(child)
        visit(fn.get("statements", []))
    return sorted(edges)


def reduce_input_set(inputs, fails):
    """Greedy bounded delta reduction, preserving the original failure predicate."""
    current = list(inputs); attempts = 0
    for candidate in list(current):
        if attempts >= MAX_REDUCTIONS: break
        if candidate not in current: continue
        proposed = [x for x in current if x != candidate]
        attempts += 1
        if proposed and fails(proposed): current = proposed
    return {"inputs": current, "attempts": attempts, "classification_preserved": bool(fails(current))}


def injected_reducer_check():
    inputs = [-10, -1, 0, 7, 8, 9, 20]
    # Deliberate harness-level oracle fault: only input 8 is made to diverge.
    fails = lambda values: 8 in values
    result = reduce_input_set(inputs, fails)
    return {"kind": "injected_harness_fault_not_production_finding", "original_inputs": inputs,
        "reduced": result, "expected_minimal_inputs": [8], "passed": result["inputs"] == [8] and result["classification_preserved"]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=VALID_CASES)
    parser.add_argument("--seed-offset", type=int, default=0)
    args = parser.parse_args()
    if not 1 <= args.limit <= VALID_CASES: raise SystemExit(f"limit must be in 1..{VALID_CASES}")
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=True)
    cases = generate_cases(args.limit, args.seed_offset)
    cases_path = out / "generated-cases.jsonl"
    results_path = out / "differential-results.jsonl"
    for path in (cases_path, results_path):
        if path.exists(): raise SystemExit(f"Refusing to overwrite {path}")
    start = time.perf_counter(); results = []
    with cases_path.open("w", encoding="utf-8") as case_file, results_path.open("w", encoding="utf-8") as result_file:
        for case in cases:
            case_file.write(json.dumps(case, sort_keys=True, separators=(",", ":")) + "\n")
            result = run_case(case); results.append(result)
            result_file.write(json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n")
            result_file.flush()
    injected = injected_reducer_check()
    (out / "counterexamples").mkdir(exist_ok=True)
    (out / "counterexamples" / "injected-reducer-check.json").write_text(json.dumps(injected, indent=2) + "\n")
    summary = {"schema": "basic-workspace.cycle39-differential-summary", "version": 1,
        "case_count": len(results), "seed_offset": args.seed_offset,
        "passed": sum(row.get("classification") == "passed" for row in results),
        "failures": [row for row in results if row.get("classification") != "passed"],
        "elapsed_seconds": round(time.perf_counter() - start, 6), "injected_reducer_check": injected}
    (out / "differential-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({"case_count": summary["case_count"], "passed": summary["passed"],
        "failure_count": len(summary["failures"]), "elapsed_seconds": summary["elapsed_seconds"],
        "injected_reducer_passed": injected["passed"]}, indent=2))
    if summary["failures"] or not injected["passed"]: raise SystemExit(1)


if __name__ == "__main__": main()
