from __future__ import annotations

import copy
import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PI = ROOT / "pi-integration"
RESULTS = PI / "results/cycle34-cross-function-authorization"
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(PI))

from basic_workspace.model import Workspace, WorkspaceError  # noqa: E402
from basic_workspace.portable_replay import replay_constructive_stream  # noqa: E402
from cycle20_gateway import Cycle20Gateway  # noqa: E402


class Cycle34CrossFunctionAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="atlas-cycle34-gateway-", dir="/var/tmp")
        self.addCleanup(self.temp.cleanup)
        self.gateway = Cycle20Gateway(pathlib.Path(self.temp.name) / "primary",
            contract_path=RESULTS / "primary-contract.json")
        self.gateway.handle("discover_functions", {}, "discover")

    def request(self, gateway=None):
        gateway = gateway or self.gateway
        return {"expected_revision": 3, "scope_mode": "per_target", "edits": [
            {"target": copy.deepcopy(row["target"]), "expected_value": row["expected_value"],
             "replacement_value": row["replacement_constraint"]["values"][0]}
            for row in gateway.edit_targets]}

    def snapshot(self, gateway=None):
        gateway = gateway or self.gateway
        return (gateway.ws.get_revision(gateway.doc),
            [(token.uid, token.text) for token in gateway.ws.documents[gateway.doc].tokens],
            gateway._normalized())

    def test_three_edits_span_two_functions_and_commit_as_one_revision(self):
        g = self.gateway
        before = self.snapshot()
        request = self.request()
        preview = g.handle("preview_semantic_edit", request, "multi-preview")
        self.assertTrue(preview["ok"], preview)
        self.assertEqual(preview["atomic_edit_count"], 3)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(preview["impact"]["directly_changed_functions"], ["CLAMP_SCORE", "IS_PASSING"])
        commit = g.handle("commit_preview", {"transaction_id": preview["transaction_id"]}, "multi-commit")
        self.assertTrue(commit["committed"], commit)
        self.assertEqual(commit["revision"], 4)
        self.assertEqual(commit["preserved_semantic_identities"], 11)
        validation = g.validate_current(4)
        self.assertTrue(validation["mission_complete"], validation)
        self.assertEqual(validation["replay"]["identity_remappings"], 11)
        self.assertEqual(validation["observed_results"], validation["expected_results"])
        self.assertEqual(g._dependency_edges(g._normalized()), [
            {"caller": "is_passing.function", "callee": "clamp_score.function"}])
        recorded = g.constructive_ops[-1]
        self.assertEqual(recorded["scope_mode"], "per_target")
        self.assertNotIn("function_handle", recorded)

    def test_authorization_rejections_are_non_mutating(self):
        g = self.gateway
        baseline = self.snapshot()
        good = self.request()
        controls = []
        controls.append(("legacy-global-handle", {**good, "function_handle": "clamp_score.function"}, "INVALID_EDIT_REQUEST"))
        controls.append(("stale-revision", {**good, "expected_revision": 2}, "STALE_REVISION"))
        partial = copy.deepcopy(good); partial["edits"] = partial["edits"][:2]
        controls.append(("incomplete-set", partial, "MISSION_EDIT_COUNT"))
        duplicate = copy.deepcopy(good); duplicate["edits"][1] = copy.deepcopy(duplicate["edits"][0])
        controls.append(("duplicate-target", duplicate, "DUPLICATE_EDIT_TARGET"))
        wrong_old = copy.deepcopy(good); wrong_old["edits"][0]["expected_value"] = 99
        controls.append(("wrong-old-value", wrong_old, "MISSION_LITERAL_VALUES"))
        extra = copy.deepcopy(good); extra["edits"][0]["replacement_value"] = 51
        controls.append(("wrong-replacement", extra, "MISSION_LITERAL_VALUES"))
        invented = copy.deepcopy(good); invented["edits"][0]["target"]["function_handle"] = "invented.function"
        controls.append(("invented-handle", invented, "MISSION_EDIT_TARGETS"))
        unauthorized = copy.deepcopy(good)
        unauthorized["edits"][2]["target"]["statement_handle"] = "is_passing.statement.2"
        controls.append(("unauthorized-path-mixed-with-valid", unauthorized, "MISSION_EDIT_TARGETS"))
        nonfinite = copy.deepcopy(good); nonfinite["edits"][0]["replacement_value"] = float("nan")
        controls.append(("nan", nonfinite, "INVALID_LITERAL_EDIT"))
        boolean = copy.deepcopy(good); boolean["edits"][0]["expected_value"] = True
        controls.append(("boolean-number", boolean, "INVALID_LITERAL_EDIT"))
        unknown = copy.deepcopy(good); unknown["edits"][0]["surprise"] = 1
        controls.append(("unknown-edit-field", unknown, "INVALID_EDIT_REQUEST"))
        for label, request, code in controls:
            with self.subTest(label=label):
                result = g.handle("preview_semantic_edit", request, label)
                self.assertFalse(result["ok"])
                self.assertEqual(result["code"], code)
                self.assertTrue(result["revision_unchanged"])
                self.assertFalse(result["authoritative_workspace_changed"])
                self.assertEqual(self.snapshot(), baseline)

    def test_commit_revalidates_the_exact_previewed_policy_and_candidate(self):
        g = self.gateway
        initial = self.snapshot()
        proposal = self.request()
        preview = g.handle("preview_semantic_edit", proposal, "candidate-preview")
        with self.assertRaises(WorkspaceError) as changed:
            g.transactions.commit(preview["transaction_id"],
                lambda record, revision: (record["operations"], {"tampered": True}, {}))
        self.assertEqual(changed.exception.code, "PREVIEW_CANDIDATE_CHANGED")
        self.assertEqual(self.snapshot(), initial)

        preview = g.handle("preview_semantic_edit", proposal, "policy-preview")
        record = g.transactions._pending[preview["transaction_id"]]
        record["metadata"]["request"]["edits"][2]["target"]["control_path"][0]["index"] = 1
        rejected = g.handle("commit_preview", {"transaction_id": preview["transaction_id"]}, "policy-tamper")
        self.assertFalse(rejected["committed"])
        self.assertEqual(rejected["code"], "MISSION_EDIT_TARGETS")
        self.assertEqual(self.snapshot(), initial)

    def test_version_one_mode_remains_single_function_and_request_shape(self):
        with tempfile.TemporaryDirectory(prefix="atlas-cycle34-v1-", dir="/var/tmp") as temp:
            g = Cycle20Gateway(pathlib.Path(temp) / "legacy")
            g.handle("discover_functions", {}, "discover")
            request = {"expected_revision": 3, "function_handle": "clamp_score.function", "edits": [
                {"target": copy.deepcopy(row["target"]), "expected_value": 100, "replacement_value": 50}
                for row in g.edit_targets]}
            self.assertTrue(g.handle("preview_semantic_edit", request, "legacy-valid")["ok"])
            cross = copy.deepcopy(request)
            cross["edits"][0] = {"target": {"function_handle": "is_passing.function",
                "control_path": [{"block": "body", "index": 0}], "expression_path": [1]},
                "expected_value": 60, "replacement_value": 45}
            result = g.handle("preview_semantic_edit", cross, "legacy-cross")
            self.assertFalse(result["ok"])
            self.assertEqual(result["code"], "MISSION_EDIT_TARGETS")
            self.assertEqual(g.ws.get_revision(g.doc), 3)

    def test_contract_scope_version_is_strict_and_boolean_is_not_version_one(self):
        with self.assertRaises(WorkspaceError) as caught:
            Cycle20Gateway._validate_contract_shape({"schema": "basic-workspace.numeric-literal-maintenance-contract",
                "version": True})
        self.assertEqual(caught.exception.code, "MISSION_CONTRACT_VERSION")

    def test_legacy_replay_envelope_cannot_hide_cross_function_target(self):
        stream_path = PI / "results/cycle20b-semantic-edit-recovery/real-agent-02/constructive-operations.json"
        stream = json.loads(stream_path.read_text(encoding="utf-8"))
        stream["operations"][-1]["function_handle"] = "is_passing.function"
        ws = Workspace(); doc = ws.create_empty_document("memory://cycle34/tampered-legacy-envelope.bas")["document_id"]
        with self.assertRaises(WorkspaceError) as caught:
            replay_constructive_stream(ws, doc, stream["operations"], expected_start_revision=1)
        self.assertEqual(caught.exception.code, "REPLAY_TARGET_INVALID")
        # Earlier constructors form the valid prefix; the mismatched edit itself was rejected.
        self.assertEqual(ws.get_revision(doc), 3)

    def test_second_contract_uses_configuration_only_and_same_policy_path(self):
        with tempfile.TemporaryDirectory(prefix="atlas-cycle34-secondary-", dir="/var/tmp") as temp:
            g = Cycle20Gateway(pathlib.Path(temp) / "secondary",
                contract_path=RESULTS / "secondary-contract.json")
            g.handle("discover_functions", {}, "discover")
            preview = g.handle("preview_semantic_edit", self.request(g), "secondary-preview")
            self.assertTrue(preview["ok"], preview)
            commit = g.handle("commit_preview", {"transaction_id": preview["transaction_id"]}, "secondary-commit")
            self.assertTrue(commit["committed"], commit)
            validation = g.validate_current(4)
            self.assertTrue(validation["mission_complete"], validation)
            for engine in ("interp", "jit"):
                self.assertEqual(validation["observed_results"][engine]["60"]["clamp_score"], 60.0)
                self.assertEqual(validation["observed_results"][engine]["60"]["is_passing"], 0.0)
                self.assertEqual(validation["observed_results"][engine]["80"]["is_passing"], 1.0)


if __name__ == "__main__":
    unittest.main()
