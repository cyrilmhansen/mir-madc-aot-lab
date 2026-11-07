from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results" / "semantic-replay"


class SemanticReplayCampaignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.run([sys.executable, str(ROOT / "scripts" / "semantic_replay_campaign.py")],
                       cwd=ROOT, check=True, timeout=20, capture_output=True, text=True)
        subprocess.run([sys.executable, str(ROOT / "scripts" / "render-semantic-replay.py")],
                       cwd=ROOT, check=True, timeout=10, capture_output=True, text=True)

    def test_fresh_workspace_replay_and_engine_equivalence(self):
        report = json.loads((RESULTS / "equivalence.json").read_text(encoding="utf-8"))
        self.assertTrue(report["structural_equivalence"])
        self.assertTrue(report["binding_equivalence"])
        self.assertTrue(report["behavioral_equivalence"])
        self.assertTrue(report["execution_engine_agreement"])
        self.assertEqual(3, report["identifier_remapping_count"])
        self.assertEqual(18.0, report["initial_outputs"]["interp"]["result"])
        self.assertEqual(27.0, report["replay_outputs"]["jit"]["result"])

    def test_denied_operation_does_not_change_revision_or_snapshot(self):
        events = [json.loads(line) for line in (RESULTS / "history.jsonl").read_text(encoding="utf-8").splitlines()]
        denied = next(event for event in events if event["event"] == "transaction_rejected")
        self.assertEqual("MISSION_OPERATION_FORBIDDEN", denied["code"])
        self.assertTrue(denied["authoritative_state_unchanged"])
        self.assertEqual(denied["base_revision"], denied["resulting_revision"])
        commits = [event for event in events if event["event"] == "transaction_committed" and event["phase"] == "original"]
        self.assertEqual(denied["resulting_revision"], commits[-1]["resulting_revision"])

    def test_constructive_stream_has_handles_not_original_workspace_ids(self):
        stream = json.loads((RESULTS / "constructive-operations.json").read_text(encoding="utf-8"))
        encoded = json.dumps(stream)
        self.assertEqual("basic-workspace.constructive-metafile", stream["schema"])
        self.assertIn("double.parameter.x", encoded)
        self.assertNotIn("sym_", encoded)
        self.assertNotIn("stmt_", encoded)

    def test_visuals_are_rendered_from_trace_and_label_uncommitted_states(self):
        html = (RESULTS / "replay.html").read_text(encoding="utf-8")
        svg = (RESULTS / "overview.svg").read_text(encoding="utf-8")
        self.assertIn("PREVIEW · not committed", html)
        self.assertIn("DENIED · state unchanged", html)
        self.assertIn("DENIED", svg)
        self.assertIn("COMMITTED", svg)
        events = [json.loads(line) for line in (RESULTS / "history.jsonl").read_text(encoding="utf-8").splitlines()]
        preview = next(e for e in events if e["event"] == "preview_accepted" and e["phase"] == "original" and e["operation"] == "edit_assignment_expression")
        prior_commit = next(e for e in events if e["event"] == "transaction_committed" and e["phase"] == "original" and e["resulting_revision"] == preview["base_revision"])
        later_commit = next(e for e in events if e["event"] == "transaction_committed" and e["phase"] == "original" and e["resulting_revision"] == preview["resulting_revision"])
        self.assertIn("* 2", prior_commit["program_snapshot"])
        self.assertIn("* 3", later_commit["program_snapshot"])
        self.assertIn("* 3", preview["preview_diff"])

    def test_rendering_the_same_trace_is_deterministic(self):
        html_before = (RESULTS / "replay.html").read_bytes()
        svg_before = (RESULTS / "overview.svg").read_bytes()
        subprocess.run([sys.executable, str(ROOT / "scripts" / "render-semantic-replay.py")],
                       cwd=ROOT, check=True, timeout=10, capture_output=True, text=True)
        self.assertEqual(html_before, (RESULTS / "replay.html").read_bytes())
        self.assertEqual(svg_before, (RESULTS / "overview.svg").read_bytes())

    def test_kitty_ansi_playback_consumes_the_recorded_trace(self):
        completed = subprocess.run([sys.executable, str(ROOT / "scripts" / "kitty-replay.py"),
                                    str(RESULTS / "history.jsonl"), "--auto", "0.001", "--no-clear"],
                                   cwd=ROOT, check=True, timeout=10, capture_output=True, text=True)
        self.assertIn("DENIED — STATE UNCHANGED", completed.stdout)
        self.assertIn("replay equivalence result", completed.stdout.lower())


if __name__ == "__main__":
    unittest.main()
