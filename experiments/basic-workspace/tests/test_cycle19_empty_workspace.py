"""Deterministic safety and replay checks for Cycle 19's empty Workspace path."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PI_DIR = ROOT / "pi-integration"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(PI_DIR))
from cycle19_gateway import Cycle19Gateway  # noqa: E402
from pi_lifecycle import completion_states  # noqa: E402


def assign(value):
    return {"kind": "assign", "target": {"kind": "result"}, "expression": value}


def ref(name="X"):
    return {"kind": "local_ref", "name": name}


def number(value):
    return {"kind": "number", "value": value}


def comparison(operator, left, right):
    return {"kind": "binary", "operator": operator, "left": left, "right": right}


def clamp_request():
    return {"name": "CLAMP_SCORE", "parameters": ["X"], "body": [
        assign(ref()),
        {"kind": "if", "condition": comparison("<", ref(), number(0)), "then": [assign(number(0))]},
        {"kind": "if", "condition": comparison(">", ref(), number(100)), "then": [assign(number(100))]},
    ]}


def passing_request():
    return {"name": "IS_PASSING", "parameters": ["X"], "body": [
        assign(number(0)),
        {"kind": "if", "condition": comparison(">=", {
            "kind": "call", "function_handle": "clamp_score.function", "arguments": [ref()]}, number(60)),
         "then": [assign(number(1))]},
    ]}


class Cycle19EmptyWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="atlas-cycle19-test-", dir="/var/tmp")
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name)
        self.gateway = Cycle19Gateway(self.output)

    def commit_clamp(self):
        g = self.gateway
        self.assertEqual(g.ws.get_revision(g.doc), 1)
        self.assertEqual(len(g.ws.documents[g.doc].tokens), 0)
        self.assertEqual(g.handle("inspect_program", {}, "inspect") ["structure"], {"functions": []})
        g.handle("discover_functions", {}, "discover-empty")
        preview = g.handle("preview_create_function", {"expected_revision": 1, **clamp_request()}, "preview-clamp")
        self.assertTrue(preview["ok"])
        self.assertEqual(g.ws.get_revision(g.doc), 1, "preview must not change the canonical revision")
        committed = g.handle("commit_preview", {"transaction_id": preview["transaction_id"]}, "commit-clamp")
        self.assertTrue(committed["committed"])
        self.assertEqual(committed["revision"], 2)
        return g.handle("host_validate", {"expected_revision": 2}, "validate-clamp")

    def advance_and_commit_passing(self):
        first = self.commit_clamp()
        self.assertTrue(first["mission_complete"])
        checkpoint = self.gateway.create_checkpoint()["checkpoint"]
        self.assertTrue(self.gateway.advance_mission2(checkpoint)["ok"])
        discovered = self.gateway.handle("discover_functions", {}, "discover-clamp")
        self.assertEqual([row["handle"] for row in discovered["functions"]], ["clamp_score.function"])
        # The discovered portable handle lives on the typed call expression;
        # the gateway must not require a redundant top-level duplicate.
        preview = self.gateway.handle("preview_create_function", {"expected_revision": 2,
            **passing_request()}, "preview-passing")
        self.assertTrue(preview["ok"])
        committed = self.gateway.handle("commit_preview", {"transaction_id": preview["transaction_id"]}, "commit-passing")
        self.assertTrue(committed["committed"])
        return self.gateway.handle("host_validate", {"expected_revision": 3}, "validate-passing")

    def test_empty_document_and_two_function_replay(self):
        result = self.advance_and_commit_passing()
        self.assertTrue(result["mission_complete"])
        self.assertTrue(result["engines_agree"])
        self.assertTrue(result["replay"]["passed"])
        self.assertEqual(result["replay"]["identity_remappings"], 11)
        self.assertEqual(self.gateway.ws.get_revision(self.gateway.doc), 3)
        self.assertEqual([f["name"] for f in self.gateway.ws.documents[self.gateway.doc].functions],
                         ["CLAMP_SCORE", "IS_PASSING"])
        self.assertTrue((self.output / "constructive-operations.json").exists())
        stream = json.loads((self.output / "constructive-operations.json").read_text())
        self.assertEqual(len(stream["operations"]), 2)
        self.assertEqual(stream["operations"][1]["callee_handle"], "clamp_score.function")

    def test_mission_one_rejects_wrong_function_and_stale_revision(self):
        g = self.gateway
        before = list(g.ws.documents[g.doc].tokens)
        bad = dict(clamp_request(), name="UNRELATED")
        rejected = g.handle("preview_create_function", {"expected_revision": 1, **bad}, "bad-name")
        self.assertFalse(rejected["ok"])
        self.assertEqual(rejected["code"], "MISSION_SIGNATURE")
        stale = g.handle("preview_create_function", {"expected_revision": 0, **clamp_request()}, "stale")
        self.assertEqual(stale["code"], "STALE_REVISION")
        self.assertEqual(g.ws.get_revision(g.doc), 1)
        self.assertEqual(g.ws.documents[g.doc].tokens, before)

    def test_mission_two_requires_verified_checkpoint_and_discovery(self):
        self.commit_clamp()
        g = self.gateway
        self.assertFalse(g.advance_mission2({"revision": 2})["ok"])
        checkpoint = g.create_checkpoint()["checkpoint"]
        bad = dict(checkpoint, semantic_fingerprint="0" * 64)
        self.assertEqual(g.advance_mission2(bad)["code"], "CHECKPOINT_MISMATCH")
        self.assertEqual(g.phase, 1)
        self.assertTrue(g.advance_mission2(checkpoint)["ok"])
        before = list(g.ws.documents[g.doc].tokens)
        undiscovered = g.handle("preview_create_function", {"expected_revision": 2,
            "callee_handle": "clamp_score.function", **passing_request()}, "undiscovered")
        self.assertEqual(undiscovered["code"], "FUNCTION_NOT_DISCOVERED")
        self.assertEqual(g.ws.documents[g.doc].tokens, before)

    def test_mission_two_rejects_wrong_dependency_and_stale_baseline(self):
        self.commit_clamp()
        g = self.gateway
        checkpoint = g.create_checkpoint()["checkpoint"]
        g.advance_mission2(checkpoint)
        g.handle("discover_functions", {}, "discover")
        bad = passing_request()
        bad["body"][1]["condition"]["left"]["function_handle"] = "unknown.function"
        rejected = g.handle("preview_create_function", {"expected_revision": 2,
            "callee_handle": "clamp_score.function", **bad}, "wrong-call")
        self.assertIn(rejected["code"], {"UNKNOWN_FUNCTION_HANDLE", "MISSION_DEPENDENCY_REQUIRED"})
        stale = g.handle("preview_create_function", {"expected_revision": 1,
            "callee_handle": "clamp_score.function", **passing_request()}, "stale-m2")
        self.assertEqual(stale["code"], "STALE_REVISION")
        self.assertEqual(g.ws.get_revision(g.doc), 2)
        self.assertEqual(len(g.ws.documents[g.doc].functions), 1)

    def test_failed_second_mission_preserves_first_committed_function(self):
        self.commit_clamp()
        g = self.gateway
        first_tokens = list(g.ws.documents[g.doc].tokens)
        checkpoint = g.create_checkpoint()["checkpoint"]
        g.advance_mission2(checkpoint)
        g.handle("discover_functions", {}, "discover")
        denied = g.handle("preview_create_function", {"expected_revision": 2,
            "callee_handle": "clamp_score.function", **dict(passing_request(), name="OTHER")}, "denied")
        self.assertFalse(denied["ok"])
        self.assertEqual(g.ws.documents[g.doc].tokens, first_tokens)
        self.assertEqual(g.ws.get_revision(g.doc), 2)

    def test_initial_visual_state_is_empty_and_commits_advance_snapshots(self):
        bundle = json.loads((self.output / "visual-source.json").read_text())
        self.assertEqual(bundle["initial"], {"revision": 1, "code": "", "dependencies": []})
        self.assertEqual(bundle["snapshots"], {"1": ""})
        self.commit_clamp()
        events = [json.loads(line) for line in (self.output / "visual-events.jsonl").read_text().splitlines()]
        commits = [event for event in events if event.get("event_type") == "commit"]
        self.assertEqual(len(commits), 1)
        self.assertEqual(commits[0]["revision"], 2)
        self.assertIn("FUNCTION CLAMP_SCORE", commits[0]["snapshot"])

    def test_completion_classifier_accepts_cycle19_host_oracle_shape(self):
        result = self.commit_clamp()
        states = completion_states(committed=True, validation=result, timed_out=False,
            exit_code=0, agent_end_seen=True, agent_settled_seen=True,
            authorization_status="authorized")
        self.assertEqual(states["semantic_program"], "passed")
        self.assertEqual(states["host_validation"], "passed")
        self.assertEqual(states["program_commit"], "committed")


if __name__ == "__main__":
    unittest.main()
