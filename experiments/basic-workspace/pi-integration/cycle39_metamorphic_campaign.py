#!/usr/bin/env python3
"""Bounded rename/edit/replay properties over generated Cycle39 histories."""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path[:0] = [str(ROOT), str(HERE)]
from basic_workspace.model import Workspace
from basic_workspace.mir_execution import MirExecutionService
from basic_workspace.portable_replay import PortableReplay, replay_constructive_stream
from basic_workspace.projection import build_projection, projection_semantics
from cycle20_gateway import senior
from cycle39_differential_campaign import generate_cases, input_corpus

EXECUTOR = MirExecutionService(timeout=2)


def normalized(ws, doc, aliases):
    return senior.normalized_state(projection_semantics(build_projection(ws, doc, ws.get_revision(doc))), aliases)


def apply_prefix(case, count):
    ws = Workspace(); doc = ws.create_empty_document(f"memory://cycle39/meta/{case['case_id']}")["document_id"]
    replay = PortableReplay(ws, doc)
    for i, op in enumerate(copy.deepcopy(case["operations"][:count])): replay.apply_operation(op, index=i)
    return ws, doc, replay


def observe(ws, doc, aliases, inputs):
    functions = [handle for handle in aliases if handle.endswith(".function")]
    result = {engine: {} for engine in ("interp", "jit")}
    for engine in result:
        for x in inputs:
            result[engine][str(x)] = {handle: EXECUTOR.execute_function(ws, doc, ws.get_revision(doc),
                aliases[handle], [x], engine)["result"] for handle in functions}
    return result


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--output", type=Path, required=True); ap.add_argument("--count", type=int, default=28)
    args = ap.parse_args(); cases = generate_cases(120)[:args.count]
    rows = []
    for case in cases:
        constructor_count = len(case["functions"])
        ws, doc, runner = apply_prefix(case, constructor_count)
        handles_before = dict(runner.aliases); norm_before = normalized(ws, doc, runner.aliases)
        corpus = input_corpus(case)
        # Keep metamorphic execution bounded while retaining thresholds and caps.
        chosen = sorted(set(corpus[:3] + corpus[-3:] + [case["generation_parameters"]["threshold"],
            case["generation_parameters"]["upper"]]))
        behavior_before = observe(ws, doc, runner.aliases, chosen)
        runner.apply_operation(copy.deepcopy(case["operations"][constructor_count]), index=constructor_count)
        behavior_after = observe(ws, doc, runner.aliases, chosen)
        rename_invariance = behavior_before == behavior_after and runner.aliases == handles_before

        before_edit_norm = normalized(ws, doc, runner.aliases)
        edit = copy.deepcopy(case["operations"][constructor_count + 1])
        runner.apply_operation(edit, index=constructor_count + 1)
        inverse = copy.deepcopy(edit)
        for row in inverse["edits"]:
            row["expected_value"], row["replacement_value"] = row["replacement_value"], row["expected_value"]
        runner.apply_operation(inverse, index=constructor_count + 2)
        edit_inverse = normalized(ws, doc, runner.aliases) == before_edit_norm and runner.aliases == handles_before

        ws1, doc1, replay1 = apply_prefix(case, len(case["operations"]))
        ws2, doc2, replay2 = apply_prefix(case, len(case["operations"]))
        replay_determinism = normalized(ws1, doc1, replay1.aliases) == normalized(ws2, doc2, replay2.aliases)
        replay_determinism = replay_determinism and replay1.aliases.keys() == replay2.aliases.keys()
        rows.append({"case_id": case["case_id"], "family": case["family"],
            "rename_behavior_and_portable_bindings_preserved": rename_invariance,
            "literal_edit_inverse_restores_normalized_state": edit_inverse,
            "equivalent_fresh_replays": replay_determinism,
            "revision_increments_for_inverse": 2, "transient_uuid_equality_required": False,
            "inputs": chosen})

    # Explicit provider-to-caller propagation fixture: a provider's upper
    # comparison changes from 10 to 11 while its branch result remains 10.
    # The caller's structure is unchanged, but its predicate at X=11 flips.
    provider = {"operation": "create_numeric_function", "portable_handle": "prop_provider.function",
        "arguments": {"name": "PROP_PROVIDER", "parameters": ["X"], "body": [
            {"kind": "assign", "target": {"kind": "result"}, "expression": {"kind": "local_ref", "name": "X"}},
            {"kind": "if", "condition": {"kind": "binary", "operator": ">", "left": {"kind": "local_ref", "name": "X"}, "right": {"kind": "number", "value": 10}}, "then": [
                {"kind": "assign", "target": {"kind": "result"}, "expression": {"kind": "number", "value": 10}}]}]}}
    caller = {"operation": "create_numeric_function", "portable_handle": "prop_caller.function",
        "arguments": {"name": "PROP_CALLER", "parameters": ["X"], "body": [
            {"kind": "assign", "target": {"kind": "result"}, "expression": {"kind": "number", "value": 0}},
            {"kind": "if", "condition": {"kind": "binary", "operator": ">=", "left": {"kind": "call", "function_handle": "prop_provider.function", "arguments": [{"kind": "local_ref", "name": "X"}]}, "right": {"kind": "number", "value": 11}}, "then": [
                {"kind": "assign", "target": {"kind": "result"}, "expression": {"kind": "number", "value": 1}}]}]}}
    ws = Workspace(); doc = ws.create_empty_document("memory://cycle39/metamorphic/provider")["document_id"]
    replay = PortableReplay(ws, doc); replay.apply_operation(provider); replay.apply_operation(caller)
    caller_before = normalized(ws, doc, replay.aliases)["functions"][1]
    before = {eng: EXECUTOR.execute_function(ws, doc, ws.get_revision(doc), replay.aliases["prop_caller.function"], [11], eng)["result"] for eng in ("interp", "jit")}
    edit = {"operation": "edit_numeric_literals", "mission_id": "cycle39.provider-propagation",
        "function_handle": "prop_provider.function", "edits": [{"target": {"function_handle": "prop_provider.function",
        "control_path": [{"block": "body", "index": 1}], "expression_path": [1]},
        "expected_value": 10, "replacement_value": 11}]}
    replay.apply_operation(edit)
    caller_after = normalized(ws, doc, replay.aliases)["functions"][1]
    after = {eng: EXECUTOR.execute_function(ws, doc, ws.get_revision(doc), replay.aliases["prop_caller.function"], [11], eng)["result"] for eng in ("interp", "jit")}
    propagation = {"caller_structure_unchanged": caller_before == caller_after,
        "provider_and_caller_outputs_before": before, "provider_and_caller_outputs_after": after,
        "caller_changed_from_zero_to_one": before == {"interp": 0.0, "jit": 0.0} and after == {"interp": 1.0, "jit": 1.0}}
    output = {"schema": "basic-workspace.cycle39-metamorphic-results", "version": 1,
        "case_count": len(rows), "all_case_properties_passed": all(
            row["rename_behavior_and_portable_bindings_preserved"] and row["literal_edit_inverse_restores_normalized_state"]
            and row["equivalent_fresh_replays"] for row in rows),
        "cases": rows, "provider_change_propagates_without_caller_structure_change": propagation,
        "provider_propagation_passed": propagation["caller_structure_unchanged"] and propagation["caller_changed_from_zero_to_one"]}
    path = args.output.resolve(); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"cases": len(rows), "all_case_properties_passed": output["all_case_properties_passed"],
        "provider_propagation_passed": output["provider_propagation_passed"]}, indent=2))
    if not output["all_case_properties_passed"] or not output["provider_propagation_passed"]: raise SystemExit(1)


if __name__ == "__main__": main()
