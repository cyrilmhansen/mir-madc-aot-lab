import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "render-code-replay.py"
SPEC = importlib.util.spec_from_file_location("code_replay", SCRIPT)
REPLAY = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(REPLAY)


class CodeFirstReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frames14 = REPLAY.adapt_cycle14_history()
        cls.frames13 = REPLAY.adapt_cycle13_history()
        cls.by_id = {frame["id"]: frame for frame in cls.frames14}

    def test_longitudinal_chronology_has_checkpoint_and_context_reset(self):
        ids = [frame["id"] for frame in self.frames14]
        self.assertEqual(ids.index("p14-checkpoint") + 1, ids.index("p14-reset"))
        self.assertLess(ids.index("p14-reset"), ids.index("p14-m3-discovery"))
        self.assertEqual(len(self.frames14), 18)

    def test_preview_keeps_committed_age_42_until_revision_four(self):
        preview = self.by_id["p14-m2-preview"]
        committed = self.by_id["p14-m2-commit"]
        self.assertEqual(preview["revision"], 3)
        self.assertIn("PERSON_AGE(1) = 42", preview["code"])
        self.assertEqual(preview["proposal"]["annotation"], "42 → 55")
        self.assertEqual(committed["revision"], 4)
        self.assertIn("PERSON_AGE(1) = 55", committed["code"])

    def test_rejected_first_resume_attempt_has_no_committed_change(self):
        rejected = self.by_id["p14-m3-first-reject"]
        previous = self.by_id["p14-reset"]
        self.assertEqual(rejected["state"], "rejected")
        self.assertEqual(rejected["revision"], previous["revision"])
        self.assertEqual(rejected["code"], previous["code"])
        self.assertEqual(rejected["proposal"]["status"], "rejected")

    def test_adult_preview_and_commit_keep_bound_call_visible(self):
        preview = self.by_id["p14-m3-preview"]
        committed = self.by_id["p14-m3-commit"]
        self.assertEqual(preview["revision"], 4)
        self.assertNotIn("FUNCTION IS_ADULT", preview["code"])
        self.assertTrue(any("AGE_BY_ID(ID)" in line for line in preview["proposal"]["append_lines"]))
        self.assertEqual(committed["revision"], 5)
        self.assertIn("FUNCTION IS_ADULT(ID)", committed["code"])
        self.assertTrue(any("AGE_BY_ID(ID)" in line for line in committed["code"].splitlines()))
        self.assertTrue(self.by_id["p14-m3-check"]["validation"]["passed"])

    def test_real_cycle13_campaign_is_represented_separately(self):
        self.assertEqual(len(self.frames13), 5)
        preview = next(frame for frame in self.frames13 if frame["id"] == "p13-preview")
        self.assertEqual(preview["state"], "proposed")
        self.assertNotIn("FUNCTION IS_SENIOR", preview["code"])
        self.assertTrue(any("AGE_BY_ID(ID)" in line for line in preview["proposal"]["append_lines"]))

    def test_html_is_offline_code_first_and_supports_deep_linked_frames(self):
        html_path = REPLAY.OUT14 / "visual-replay.html"
        page = html_path.read_text(encoding="utf-8")
        self.assertIn('id="source"', page)
        self.assertIn('id="frames-data"', page)
        self.assertIn("history.replaceState", page)
        self.assertIn("Evidence and diagnostics", page)
        self.assertNotIn("https://", page)


if __name__ == "__main__":
    unittest.main()
