from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "pi-integration"
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(HERE)]

from basic_workspace.model import Workspace, WorkspaceError
from basic_workspace.portable_replay import PortableReplay
from basic_workspace.projection import build_projection, projection_semantics
from cycle20_gateway import senior
from cycle39_differential_campaign import generate_cases, injected_reducer_check, run_case


class Cycle39DifferentialTests(unittest.TestCase):
    def test_generation_is_fixed_seed_and_covers_seven_families(self):
        first = generate_cases(42)
        second = generate_cases(42)
        self.assertEqual(first, second)
        self.assertEqual({row["family"] for row in first}, {
            "clamp", "threshold_ge", "threshold_lt", "dependent_predicate",
            "sequential_override", "two_callees", "dependency_chain"})
        self.assertTrue(all(len(row["functions"]) <= 5 and len(row["operations"]) <= 8 for row in first))

    def test_one_case_per_template_matches_oracle_both_engines_and_replay(self):
        cases = generate_cases(7)
        outcomes = [run_case(row) for row in cases]
        self.assertTrue(all(row["classification"] == "passed" for row in outcomes), outcomes)
        self.assertGreaterEqual(len({json.dumps(row["dependency_edges"], sort_keys=True) for row in outcomes}), 4)

    def test_unknown_replay_operation_rejects_without_mutation(self):
        ws = Workspace(); doc = ws.create_empty_document("memory://cycle39/negative/unknown")["document_id"]
        replay = PortableReplay(ws, doc)
        replay.apply_operation(copy.deepcopy(generate_cases(1)[0]["operations"][0]))
        before = senior.normalized_state(projection_semantics(build_projection(ws, doc, ws.get_revision(doc))), replay.aliases)
        revision = ws.get_revision(doc)
        with self.assertRaises(WorkspaceError) as caught:
            replay.apply_operation({"operation": "unregistered_mutation"})
        self.assertEqual(caught.exception.code, "REPLAY_OPERATION_UNSUPPORTED")
        after = senior.normalized_state(projection_semantics(build_projection(ws, doc, ws.get_revision(doc))), replay.aliases)
        self.assertEqual(ws.get_revision(doc), revision)
        self.assertEqual(after, before)

    def test_incorrect_literal_precondition_rejects_atomically(self):
        case = generate_cases(1)[0]
        ws = Workspace(); doc = ws.create_empty_document("memory://cycle39/negative/literal")["document_id"]
        replay = PortableReplay(ws, doc)
        for operation in case["operations"][:1]: replay.apply_operation(copy.deepcopy(operation))
        before = senior.normalized_state(projection_semantics(build_projection(ws, doc, ws.get_revision(doc))), replay.aliases)
        revision = ws.get_revision(doc)
        edit = copy.deepcopy(case["operations"][-1])
        edit["edits"][0]["expected_value"] += 999
        with self.assertRaises(WorkspaceError) as caught:
            replay.apply_operation(edit)
        self.assertEqual(caught.exception.code, "EXPECTED_LITERAL_MISMATCH")
        self.assertEqual(ws.get_revision(doc), revision)
        self.assertEqual(senior.normalized_state(projection_semantics(build_projection(ws, doc, revision)), replay.aliases), before)

    def test_fixed_reducer_preserves_injected_failure_class(self):
        result = injected_reducer_check()
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["reduced"]["inputs"], [8])


if __name__ == "__main__":
    unittest.main()
