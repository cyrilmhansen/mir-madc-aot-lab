from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PI = ROOT / "pi-integration"
# The 16B transcript remains immutable. Dispatch regressions are exercised
# against the current Pi 1.5 active schema, which now supports 1..8 edits.
SCHEMA_DIR = PI / "results/cycle21-reusable-maintenance/schema-preflight-02"


@unittest.skipUnless(shutil.which("bun") and (SCHEMA_DIR / "tool-schemas.json").is_file(),
    "Cycle 20B integration regression requires the installed Pi schema capture and Bun")
class Cycle20BDispatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="cycle20b-dispatch-", dir="/var/tmp")
        cls.output = pathlib.Path(cls.temp.name) / "preflight"
        completed = subprocess.run([sys.executable, str(PI / "cycle20b_preflight.py"),
            "--output", str(cls.output), "--pi-schema-dir", str(SCHEMA_DIR)],
            capture_output=True, text=True, timeout=90)
        cls.run_result = completed
        cls.summary = None
        summary_path = cls.output / "preflight-summary.json"
        if summary_path.is_file():
            cls.summary = json.loads(summary_path.read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_real_extension_handler_dispatches_four_historical_proposals(self):
        self.assertEqual(self.run_result.returncode, 0, self.run_result.stderr[-2000:])
        self.assertEqual(self.summary["historical_valid_proposals_previewed"], 4)
        self.assertTrue(all(row["schema_valid"] and row["preview_accepted"] and
            row["revision_unchanged"] and row["changed_literal_token_count"] == 2
            for row in self.summary["valid_proposal_results"]))

    def test_known_good_extension_dispatch_commits_and_replays_candidate(self):
        self.assertEqual(self.run_result.returncode, 0, self.run_result.stderr[-2000:])
        result = json.loads((self.output / "known-good-commit/probe-result.json").read_text())
        self.assertTrue(result["preview"]["accepted"])
        self.assertTrue(result["committed"]["committed"])
        self.assertEqual(result["committed"]["revision"], 4)
        self.assertTrue(result["validation"]["mission_complete"])
        self.assertTrue(result["validation"]["replay"]["passed"])

    def test_fifth_historical_call_is_schema_rejected_for_missing_empty_path(self):
        self.assertEqual(self.run_result.returncode, 0, self.run_result.stderr[-2000:])
        probe = json.loads((self.output / "historical-schema-negative/probe-result.json").read_text())
        self.assertFalse(probe["schema_ok"])
        self.assertTrue(any("expression_path" in error["message"] for error in probe["schema_errors"]))
        self.assertTrue(self.summary["historical_fifth_proposal"]["expression_path_empty_is_valid"])
        self.assertTrue(self.summary["historical_fifth_proposal"]["expression_path_absent_is_invalid"])

    def test_transport_correlation_is_outside_semantic_args_and_unknown_fields_fail(self):
        self.assertEqual(self.run_result.returncode, 0, self.run_result.stderr[-2000:])
        boundary = self.summary["transport_boundary"]
        self.assertEqual(boundary["correlation_transport_field"], "transport.tool_call_id")
        self.assertFalse(boundary["semantic_params_contain_tool_call_id"])
        self.assertTrue(boundary["preview_transaction_correlation_recorded"])
        controls = boundary["unknown_field_controls"]
        self.assertEqual(controls["unknown_semantic_field_code"], "INVALID_EDIT_REQUEST")
        self.assertTrue(controls["unknown_transport_metadata_rejected"])
        self.assertTrue(controls["revision_unchanged"])


if __name__ == "__main__":
    unittest.main()
