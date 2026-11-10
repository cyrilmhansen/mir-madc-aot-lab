#!/usr/bin/env python3
"""Bounded canonical replay metamorphic checks for Cycle38 histories."""
from __future__ import annotations

import copy
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(HERE))
from basic_workspace.model import Workspace
from basic_workspace.mir_execution import MirExecutionService
from basic_workspace.portable_replay import PortableReplay
from basic_workspace.projection import build_projection, projection_semantics
from cycle20_gateway import senior

ATTEMPT = HERE / "results/cycle38-longitudinal-stress/production-bridge-attempt-08"
EXECUTOR = MirExecutionService(timeout=20)


def read(path): return json.loads(path.read_text(encoding="utf-8"))
def normalized(runner):
    return senior.normalized_state(projection_semantics(build_projection(runner.ws, runner.doc,
        runner.ws.get_revision(runner.doc))), runner.aliases)


def start(mission, operations):
    ws = Workspace(); doc = ws.create_empty_document(f"memory://cycle38/metamorphic/{mission}.bas")["document_id"]
    runner = PortableReplay(ws, doc)
    for i, op in enumerate(operations): runner.apply_operation(copy.deepcopy(op), index=i)
    return runner


def observations(runner, inputs):
    functions = sorted(h for h in runner.aliases if h.endswith(".function"))
    return {engine: {str(x): {h: EXECUTOR.execute_function(runner.ws, runner.doc,
        runner.ws.get_revision(runner.doc), runner.aliases[h], [x], engine)["result"] for h in functions}
        for x in inputs} for engine in ("interp", "jit")}


def main():
    global ATTEMPT
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt",type=Path,default=ATTEMPT)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args(); ATTEMPT=args.attempt.resolve()
    results = []
    for mission in ("mission-a", "mission-b"):
        stream = read(ATTEMPT / mission / "maintenance/gateway-evidence/constructive-operations.json")
        operations = stream["operations"]
        rename_op_index = next(i for i, op in enumerate(operations) if op["operation"] == "rename_symbol")
        edit_index = next(i for i, op in enumerate(operations) if op["operation"] == "edit_numeric_literals")
        base = start(mission, operations[:rename_op_index])
        before = normalized(base); handles_before = set(base.aliases)
        token_ids_before = {token.uid for token in base.ws.documents[base.doc].tokens}
        rename_op = copy.deepcopy(operations[rename_op_index])
        base.apply_operation(rename_op)
        inverse_rename = {"operation": "rename_symbol", "target_handle": rename_op["target_handle"],
            "expected_name": rename_op["new_name"], "new_name": rename_op["expected_name"]}
        base.apply_operation(inverse_rename)
        rename_restored = normalized(base) == before and set(base.aliases) == handles_before
        token_identity_preserved = {token.uid for token in base.ws.documents[base.doc].tokens} == token_ids_before

        # Restore forward order for the literal inverse experiment.
        final = start(mission, operations[:edit_index])
        baseline_pre_edit = normalized(final); alias_pre_edit = dict(final.aliases)
        baseline_tokens = {token.uid: token.text for token in final.ws.documents[final.doc].tokens}
        edit = copy.deepcopy(operations[edit_index]); final.apply_operation(edit)
        inverse_edit = copy.deepcopy(edit)
        for row in inverse_edit["edits"]:
            row["expected_value"], row["replacement_value"] = row["replacement_value"], row["expected_value"]
        final.apply_operation(inverse_edit)
        edit_restored = normalized(final) == baseline_pre_edit and final.aliases == alias_pre_edit
        values_restored = {token.uid: token.text for token in final.ws.documents[final.doc].tokens} == baseline_tokens
        # Compare two independent full fresh replays modulo process-local UUIDs.
        run1 = start(mission, operations); run2 = start(mission, operations)
        equivalent = normalized(run1) == normalized(run2) and set(run1.aliases) == set(run2.aliases)
        inputs = read(ATTEMPT / mission / "independent-oracle-observations.json")["inputs"]
        equivalent = equivalent and observations(run1, inputs) == observations(run2, inputs)

        # Swapping rename/edit is replayable and semantically commutative here,
        # but violates the host contract's revision-bound order (maintenance
        # baseline is the post-rename revision). This is reported separately.
        reordered = copy.deepcopy(operations)
        reordered[rename_op_index], reordered[edit_index] = reordered[edit_index], reordered[rename_op_index]
        reordered_runner = start(mission, reordered)
        commutes_semantically = normalized(reordered_runner) == normalized(run1)
        results.append({"mission": mission, "rename_a_to_b_to_a": {"passed": rename_restored,
            "portable_identity_preserved": set(base.aliases) == handles_before,
            "token_identity_set_preserved": token_identity_preserved,
            "revision_increments": 2},
            "literal_v1_v2_v1": {"passed": edit_restored and values_restored,
            "portable_identity_map_unchanged": final.aliases == alias_pre_edit,
            "revision_increments": 2},
            "independent_equivalent_replays": {"passed": equivalent, "transient_uuid_equality_required": False},
            "rename_maintenance_reordering": {"semantic_replay_equivalent": commutes_semantically,
            "host_authorization_permits_reordering": False,
            "reason": "maintenance contract is bound to the revision after rename; semantic commutation does not override revision authorization"}})
    output = {"schema": "basic-workspace.cycle38-metamorphic-results", "version": 1,
        "all_semantic_checks_passed": all(row["rename_a_to_b_to_a"]["passed"]
            and row["literal_v1_v2_v1"]["passed"] and row["independent_equivalent_replays"]["passed"] for row in results),
        "results": results}
    path = args.output.resolve()
    if path.exists(): raise SystemExit(f"Refusing to overwrite metamorphic evidence: {path}")
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": output["all_semantic_checks_passed"], "missions": len(results)}, indent=2))
    if not output["all_semantic_checks_passed"]: raise SystemExit(1)


if __name__ == "__main__": main()
