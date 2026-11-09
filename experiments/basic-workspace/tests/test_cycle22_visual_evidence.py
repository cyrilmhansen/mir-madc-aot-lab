import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts"
SPEC = importlib.util.spec_from_file_location("basic_visual_cycle22", SCRIPT / "basic-visual.py")
VISUAL = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = VISUAL
SPEC.loader.exec_module(VISUAL)
import visualization as VIS

RESULTS = ROOT / "pi-integration" / "results"
OUT = RESULTS / "cycle22-visual-evidence"
CASES = {
    "cycle20b": {
        "source": RESULTS / "cycle20b-semantic-edit-recovery" / "real-agent-02",
        "display": OUT / "cycle20b-real-agent-02-evidence-view.json",
        "base": 3,
        "committed": 4,
        "edit_count": 2,
        "session": "cycle20b-real-agent-02/real-agent-02",
        "inputs": ["49", "50", "51", "60"],
        "result_key": "clamp_score",
        "changed_value": "50",
    },
    "cycle21": {
        "source": RESULTS / "cycle21-reusable-maintenance" / "real-agent-01",
        "display": OUT / "cycle21-real-agent-01-evidence-view.json",
        "base": 4,
        "committed": 5,
        "edit_count": 1,
        "session": "cycle21.is-passing-threshold40.v1/real-agent-01",
        "inputs": ["39", "40", "50", "60"],
        "result_key": "is_passing",
        "changed_value": "40",
    },
}


class FaithfulMaintenanceVisualEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiled = {}
        cls.html = {}
        for key, spec in CASES.items():
            data = VISUAL.compile_campaign(spec["source"], spec["display"])
            cls.compiled[key] = data["campaigns"][0]
            cls.html[key] = (OUT / key / "visual-replay-generic.html").read_text()

    def frames(self, key):
        return self.compiled[key]["frames"]

    def event(self, key, kind):
        return next(f for f in self.frames(key) if f["event_type"] == kind)

    def test_preview_diff_is_visible_without_advancing_committed_program(self):
        for key, old, new in (("cycle21", ">= 60", ">= 40"), ("cycle20b", "> 100", "> 50")):
            with self.subTest(campaign=key):
                initial = self.event(key, "initial")
                preview = self.event(key, "preview")
                self.assertEqual(preview["revision"], CASES[key]["base"])
                self.assertEqual(preview["code"], initial["code"])
                diff = preview["proposal"]["diff"]
                self.assertIn("-", diff)
                self.assertIn(old, diff)
                self.assertIn(new, diff)
                self.assertIn("committed BASIC remains revision ", self.html[key])
                self.assertIn("diff-row ${isOld?'old':'new'}", self.html[key])
                self.assertIn("Proposed numeric source diff", self.html[key])

    def test_commit_advances_once_and_highlights_only_verified_changed_lines(self):
        for key, spec in CASES.items():
            with self.subTest(campaign=key):
                preview, commit = self.event(key, "preview"), self.event(key, "commit")
                self.assertEqual(preview["revision"], spec["base"])
                self.assertEqual(commit["revision"], spec["committed"])
                self.assertEqual(commit["revision"] - preview["revision"], 1)
                self.assertEqual(commit["highlights"]["mapping"], "verified_unique_line_difference")
                lines = commit["highlights"]["lines"]
                self.assertEqual(len(lines), spec["edit_count"])
                changed = [commit["code"].splitlines()[n - 1] for n in lines]
                self.assertTrue(all(spec["changed_value"] in line for line in changed))
                if key == "cycle21":
                    self.assertEqual(changed, ["  IF (CLAMP_SCORE(X) >= 40) THEN"])
                else:
                    self.assertEqual(changed, ["  IF (X > 50) THEN", "    CLAMP_SCORE = 50"])
                self.assertEqual(len(commit["changed_token_ids"]), spec["edit_count"])

    def test_recorded_engine_observations_and_host_expectations_are_revision_bound(self):
        spec = CASES["cycle21"]
        validations = [f for f in self.frames("cycle21") if f["event_type"] == "validation"]
        self.assertEqual(len(validations), 2)
        for frame in validations:
            obs = frame["observation"]
            self.assertEqual(frame["revision"], spec["committed"])
            self.assertEqual(obs["revision"], spec["committed"])
            self.assertEqual(frame["observation_freshness"], "current")
            self.assertEqual(obs["display_inputs"], [39, 40, 50, 60])
            self.assertTrue(obs["host_validation_passed"])
            self.assertEqual(obs["agreement"], True)
            for input_value, expected in (("39", 0.0), ("40", 1.0), ("50", 1.0), ("60", 1.0)):
                for engine in ("interp", "jit"):
                    self.assertEqual(obs["engine_results"][engine][input_value]["is_passing"], expected)
                    self.assertEqual(obs["expected_results"][engine][input_value]["is_passing"], expected)
        html = self.html["cycle21"]
        self.assertIn("Interpreter", html)
        self.assertIn("expected_provenance", html)
        self.assertIn("39", html)
        self.assertIn("60", html)

    def test_campaign_and_output_metadata_replace_inherited_session_identity(self):
        for key, spec in CASES.items():
            campaign = self.compiled[key]
            self.assertEqual(campaign["presentation_session_id"], spec["session"])
            self.assertTrue(all(f["session_id"] == spec["session"] for f in campaign["frames"]))
            self.assertNotIn("cycle20-real-agent-01", json.dumps(campaign))
            self.assertEqual(campaign["id"], spec["source"].joinpath("visual-source.json").exists() and json.loads((spec["source"] / "visual-source.json").read_text())["campaign"]["id"])

    def test_standalone_reports_include_diff_and_actual_validation_without_remote_dependencies(self):
        for key in CASES:
            html = self.html[key]
            self.assertIn("Proposed numeric source diff", html)
            self.assertIn("engine_results", html)
            self.assertNotIn('<script src=', html)
            self.assertNotIn('<link rel="stylesheet" href="http', html)

    def test_rejected_candidate_is_distinct_and_cannot_change_committed_revision(self):
        initial_code = "FUNCTION F(X)\n F = X\nEND FUNCTION\n"
        compiler = VIS.VisualFrameCompiler("test", "Test", "T.bas", 4, initial_code, {})
        compiler.consume({"event_id":"i","event_type":"initial","revision":4,"provenance":"host"})
        rejected = compiler.consume({"event_id":"r","event_type":"rejection","revision":4,"provenance":"MissionGateway",
            "preview":{"status":"rejected","diagnostic":"unauthorized target"}})
        self.assertEqual(rejected["state"], "rejected")
        self.assertEqual(rejected["revision"], 4)
        self.assertEqual(rejected["code"], initial_code)
        self.assertEqual(rejected["proposal"]["status"], "rejected")
        html = VIS.render_html({"campaigns":[{"id":"test","title":"Test","frames":[rejected]}]})
        self.assertIn("rejectedProposal", html)
        self.assertIn("Denied · no committed source change", html)


if __name__ == "__main__":
    unittest.main()
