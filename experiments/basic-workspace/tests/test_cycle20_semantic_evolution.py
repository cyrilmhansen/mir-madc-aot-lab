from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PI = ROOT / "pi-integration"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(PI))

from cycle20_gateway import Cycle20Gateway, MISSION_ID
from basic_workspace.model import Workspace, WorkspaceError


class Cycle20SemanticEvolutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cycle20-test-", dir="/var/tmp")
        self.addCleanup(self.temp.cleanup)
        self.gateway = Cycle20Gateway(Path(self.temp.name) / "campaign")

    def request(self):
        return {"expected_revision": 3, "function_handle": "clamp_score.function",
            "edits": [{"target": copy.deepcopy(row["target"]), "expected_value": 100,
                "replacement_value": 50} for row in self.gateway.edit_targets]}

    def discovered(self):
        result = self.gateway.handle("discover_functions", {}, "discover")
        self.assertEqual({row["handle"] for row in result["functions"]},
                         {"clamp_score.function", "is_passing.function"})
        return self.gateway.handle("inspect_program", {}, "inspect")

    def test_exact_cycle19b_stream_reconstruction_and_checkpoint(self):
        self.assertEqual(self.gateway.ws.get_revision(self.gateway.doc), 3)
        result = json.loads((self.gateway.output / "baseline-reconstruction.json").read_text())
        self.assertTrue(result["passed"])
        self.assertTrue(result["revision2_checkpoint_fingerprint_match"])
        self.assertTrue(result["revision3_normalized_semantics_match"])
        self.assertTrue(result["prior_interpreter_jit_results_match"])
        self.assertEqual(result["portable_identity_count"], 11)
        self.assertTrue(result["identities_remapped_from_source"])
        self.assertEqual(self.gateway.dependencies(), [
            {"caller": "IS_PASSING", "callee": "CLAMP_SCORE"}])

    def test_inspection_exposes_both_typed_locations_without_source_search(self):
        discovered = self.discovered()
        targets = discovered["editable_upper_bound_occurrences"]
        self.assertEqual(len(targets), 2)
        self.assertEqual([row["current_value"] for row in targets], [100.0, 100.0])
        self.assertTrue(any("control_path" in row["target"] for row in targets))
        self.assertTrue(any("statement_handle" in row["target"] for row in targets))
        self.assertTrue(all(row["target"]["function_handle"] == "clamp_score.function" for row in targets))

    def test_preview_is_atomic_candidate_and_shows_dependent_behavior(self):
        self.discovered()
        before_revision = self.gateway.ws.get_revision(self.gateway.doc)
        before_tokens = [(t.uid, t.text) for t in self.gateway.ws.documents[self.gateway.doc].tokens]
        result = self.gateway.handle("preview_semantic_edit", self.request(), "preview")
        self.assertTrue(result["ok"])
        self.assertTrue(result["candidate_is_preview_only"])
        self.assertEqual(result["atomic_edit_count"], 2)
        self.assertEqual(result["impact"]["directly_changed_functions"], ["CLAMP_SCORE"])
        self.assertEqual(result["impact"]["dependent_callers"], ["IS_PASSING"])
        self.assertEqual(result["impact"]["before_observations"]["interp"]["60"]["is_passing"], 1.0)
        self.assertEqual(result["impact"]["candidate_observations"]["interp"]["60"]["is_passing"], 0.0)
        self.assertEqual(self.gateway.ws.get_revision(self.gateway.doc), before_revision)
        self.assertEqual([(t.uid, t.text) for t in self.gateway.ws.documents[self.gateway.doc].tokens], before_tokens)

    def test_pi_transport_correlation_metadata_is_not_a_semantic_edit_field(self):
        self.discovered()
        request = self.request()
        request["toolCallId"] = "fixture-pi-call-17"
        result = self.gateway.handle("preview_semantic_edit", request, "gateway-request-17")
        self.assertTrue(result["ok"])
        self.assertEqual(result["atomic_edit_count"], 2)
        self.assertEqual(result["base_revision"], 3)
        self.assertEqual(self.gateway.ws.get_revision(self.gateway.doc), 3)
        self.assertIn(result["transaction_id"], self.gateway.preview_pending)

    def test_atomic_commit_preserves_ids_and_fresh_replay(self):
        self.discovered()
        preview = self.gateway.handle("preview_semantic_edit", self.request(), "preview")
        self.assertTrue(preview["ok"])
        commit = self.gateway.handle("commit_preview", {"transaction_id": preview["transaction_id"]}, "commit")
        self.assertTrue(commit["committed"])
        self.assertEqual(commit["revision"], 4)
        self.assertEqual(commit["preserved_semantic_identities"], 11)
        validation = self.gateway.validate_current(4)
        self.assertTrue(validation["mission_complete"])
        self.assertTrue(validation["IS_PASSING_structurally_unchanged"])
        self.assertTrue(validation["dependency_edges_unchanged"])
        self.assertTrue(validation["replay"]["passed"])
        self.assertEqual(validation["replay"]["identity_remappings"], 11)
        for engine in ("interp", "jit"):
            for value in (-100, -1, 0, 1, 49, 50, 51, 59, 60, 80, 99, 100, 101, 200):
                row = validation["observed_results"][engine][str(value)]
                self.assertEqual(row["clamp_score"], float(min(50, max(0, value))))
                self.assertEqual(row["is_passing"], 0.0)

    def test_rejected_mission_requests_never_mutate_workspace(self):
        self.discovered()
        before_revision = self.gateway.ws.get_revision(self.gateway.doc)
        before_tokens = [(t.uid, t.text) for t in self.gateway.ws.documents[self.gateway.doc].tokens]
        controls = []
        partial = self.request(); partial["edits"] = partial["edits"][:1]
        controls.append((partial, "MISSION_EDIT_COUNT"))
        wrong_func = self.request(); wrong_func["function_handle"] = "is_passing.function"
        controls.append((wrong_func, "MISSION_EDIT_SCOPE"))
        stale = self.request(); stale["expected_revision"] = 2
        controls.append((stale, "STALE_REVISION"))
        wrong_old = self.request(); wrong_old["edits"][0]["expected_value"] = 99
        controls.append((wrong_old, "MISSION_LITERAL_VALUES"))
        ambiguous = self.request(); ambiguous["edits"][1] = copy.deepcopy(ambiguous["edits"][0])
        controls.append((ambiguous, "DUPLICATE_EDIT_TARGET"))
        unauthorized = self.request(); unauthorized["edits"][0]["target"]["function_handle"] = "is_passing.function"
        controls.append((unauthorized, "MISSION_EDIT_TARGETS"))
        for index, (request, code) in enumerate(controls):
            with self.subTest(code=code):
                result = self.gateway.handle("preview_semantic_edit", request, f"control-{index}")
                self.assertFalse(result["ok"])
                self.assertEqual(result["code"], code)
                self.assertTrue(result["revision_unchanged"])
                self.assertFalse(result["authoritative_workspace_changed"])
                self.assertEqual(self.gateway.ws.get_revision(self.gateway.doc), before_revision)
                self.assertEqual([(t.uid, t.text) for t in self.gateway.ws.documents[self.gateway.doc].tokens], before_tokens)

    def test_workspace_transaction_rolls_back_partial_literal_edits(self):
        g = self.gateway
        first, second = g.edit_targets
        first_op = {"operation": "edit_numeric_literal_at_path", "function_id": g.aliases["clamp_score.function"],
            "target_kind": "if_condition_rhs", "control_path": first["target"]["control_path"],
            "expression_path": [1], "expected_value": 100, "replacement_value": 50}
        second_op = {"operation": "edit_numeric_literal_at_path", "function_id": g.aliases["clamp_score.function"],
            "target_kind": "assignment_rhs", "statement_id": g.aliases[second["target"]["statement_handle"]],
            "expression_path": [], "expected_value": 999, "replacement_value": 50}
        revision = g.ws.get_revision(g.doc)
        tokens = [(t.uid, t.text) for t in g.ws.documents[g.doc].tokens]
        with self.assertRaises(WorkspaceError) as raised:
            g.ws.apply_transaction(g.doc, revision, [first_op, second_op])
        self.assertEqual(raised.exception.code, "EXPECTED_LITERAL_MISMATCH")
        self.assertEqual(g.ws.get_revision(g.doc), revision)
        self.assertEqual([(t.uid, t.text) for t in g.ws.documents[g.doc].tokens], tokens)

    def test_literal_identity_is_token_stable_but_not_a_semantic_handle(self):
        g = self.gateway
        g.discovered.add("clamp_score.function")
        before = {token.uid: token.text for token in g.ws.documents[g.doc].tokens}
        preview = g.handle("preview_semantic_edit", self.request(), "preview")
        committed = g.handle("commit_preview", {"transaction_id": preview["transaction_id"]}, "commit")
        self.assertTrue(committed["committed"])
        after = {token.uid: token.text for token in g.ws.documents[g.doc].tokens}
        changed = [uid for uid in before if before[uid] != after[uid]]
        self.assertEqual(len(changed), 2)
        self.assertEqual(set(before), set(after))
        self.assertFalse(any("literal" in handle for handle in g.aliases))


if __name__ == "__main__":
    unittest.main()
