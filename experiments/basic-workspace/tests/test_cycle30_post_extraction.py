from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest

PI = pathlib.Path(__file__).resolve().parents[1] / "pi-integration"
RESULT = PI / "results/cycle30-post-extraction-maintenance"
STREAM = PI / "results/cycle29-function-extraction/real-agent-01/constructive-operations.json"
HISTORY = PI / "results/cycle29-function-extraction/real-agent-01/history.jsonl"
VALIDATION = PI / "results/cycle29-function-extraction/real-agent-01/mission-2-validation-host.json"
CONTRACT = RESULT / "mission-contract.json"
RETIRED = {"score_class.statement.0", "score_class.statement.1"}

sys.path.insert(0, str(PI))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from basic_workspace.model import Workspace
from basic_workspace.portable_replay import replay_constructive_stream
spec = importlib.util.spec_from_file_location("cycle20_gateway_cycle30_tests", PI / "cycle20_gateway.py")
gateway_module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = gateway_module
spec.loader.exec_module(gateway_module)


class Cycle30PostExtractionTests(unittest.TestCase):
    def gateway(self, path):
        return gateway_module.Cycle20Gateway(path, contract_path=CONTRACT,
            baseline_stream_path=STREAM, baseline_history_path=HISTORY,
            baseline_validation_path=VALIDATION)

    def test_revision13_replay_and_retired_identity_safety(self):
        with tempfile.TemporaryDirectory(prefix="atlas-cycle30-test-", dir="/var/tmp") as temp:
            g = self.gateway(pathlib.Path(temp) / "gateway")
            self.assertEqual(g.ws.get_revision(g.doc), 13)
            self.assertEqual(len(g.aliases), 27)
            self.assertEqual(set(g.retired_handles), RETIRED)
            self.assertFalse(set(g.aliases) & RETIRED)
            discovery = g.handle("discover_functions", {}, "discover")
            self.assertEqual({row["name"] for row in discovery["functions"]},
                {"NORMALIZE_SCORE", "IS_PASSING", "IS_AT_CAP", "SCORE_CLASS", "BASE_SCORE_CLASS"})
            inspection = g.handle("inspect_program", {}, "inspect")
            self.assertEqual(set(inspection["retired_portable_handles"]), RETIRED)
            for handle in RETIRED:
                target = {"function_handle": "score_class.function", "statement_handle": handle, "expression_path": []}
                with self.assertRaises(Exception):
                    g._target_expression(g.baseline, target)
                replacement = json.loads(STREAM.read_text())["operations"][-1]
                replacement["anchor_statement_handle"] = handle
                with self.assertRaises(Exception):
                    operations = json.loads(STREAM.read_text())["operations"]
                    operations.append(replacement)
                    test_ws = Workspace(); test_doc = test_ws.create_empty_document("memory://cycle30/retired-anchor.bas")["document_id"]
                    replay_constructive_stream(test_ws, test_doc, operations)
            self.assertEqual(g.ws.get_revision(g.doc), 13)

    def test_numeric_edit_preview_commit_oracle_and_full_portable_replay(self):
        with tempfile.TemporaryDirectory(prefix="atlas-cycle30-test-", dir="/var/tmp") as temp:
            g = self.gateway(pathlib.Path(temp) / "gateway")
            g.handle("discover_functions", {}, "discover")
            g.handle("inspect_program", {}, "inspect")
            target = g.edit_targets[0]["target"]
            request = {"expected_revision": 13, "function_handle": "base_score_class.function",
                "edits": [{"target": target, "expected_value": 20, "replacement_value": 25}]}
            preview = g.handle("preview_semantic_edit", request, "preview")
            self.assertTrue(preview["accepted"])
            self.assertEqual(g.ws.get_revision(g.doc), 13)
            # Change a host-owned invariant after preview; commit reauthorization must fail.
            g.contract["required_dependency_edges"].pop()
            denied = g.handle("commit_preview", {"transaction_id": preview["transaction_id"]}, "denied-commit")
            self.assertFalse(denied["committed"])
            self.assertEqual(g.ws.get_revision(g.doc), 13)
            self.assertEqual(g.ws.render_document(g.doc), g.initial_code)

            g = self.gateway(pathlib.Path(temp) / "valid-gateway")
            g.handle("discover_functions", {}, "discover")
            g.handle("inspect_program", {}, "inspect")
            preview = g.handle("preview_semantic_edit", request, "preview")
            receipt = g.handle("commit_preview", {"transaction_id": preview["transaction_id"]}, "commit")
            self.assertTrue(receipt["committed"])
            self.assertEqual(receipt["revision"], 14)
            self.assertEqual(g.aliases, g.baseline_aliases)
            validation = g.handle("host_validate", {"expected_revision": 14}, "host-validate")
            self.assertTrue(validation["mission_complete"])
            self.assertEqual(validation["observed_results"]["interp"], validation["observed_results"]["jit"])
            for x in (20, 21, 24, 25):
                row = validation["observed_results"]["interp"][str(x)]
                self.assertEqual(row["base_score_class"], 0.0 if x < 25 else 1.0)
                self.assertEqual(row["score_class"], 0.0 if x < 25 else 1.0)
            self.assertTrue(validation["replay"]["passed"])
            self.assertEqual(validation["replay"]["identity_remappings"], 27)
            self.assertTrue(validation["replay"]["retired_handles_not_reused"])

    def test_contract_and_dispatch_preflight_are_recorded_without_inference(self):
        preflight = json.loads((RESULT / "production-bridge-preflight-05/summary.json").read_text())
        self.assertTrue(preflight["passed"])
        self.assertFalse(preflight["inference_performed"])
        self.assertEqual(preflight["baseline_revision"], 13)
        self.assertEqual(preflight["disposable_commit_revision"], 14)
        self.assertEqual(preflight["retired_identity_checks"]["edit_target_rejection_codes"], ["MISSION_EDIT_TARGETS"])
        self.assertEqual(preflight["retired_identity_checks"]["insertion_anchor_rejection_codes"], ["REPLAY_HANDLE_MISSING"])
        extended = json.loads((RESULT / "extended-boundary-checks.json").read_text())
        self.assertTrue(extended["passed"])
        self.assertEqual(extended["inputs"], [20, 21, 22, 23, 24, 25])
        self.assertEqual(extended["observed_results"]["interp"], extended["observed_results"]["jit"])


if __name__ == "__main__":
    unittest.main()
