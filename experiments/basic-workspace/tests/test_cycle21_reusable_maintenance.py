from __future__ import annotations

import importlib.util
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PI = ROOT / "pi-integration"
SCHEMA_DIR = PI / "results/cycle21-reusable-maintenance/schema-preflight-02"


def _load_runner():
    path = PI / "run_cycle20.py"
    spec = importlib.util.spec_from_file_location("cycle21_maintenance_runner", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ReusableMaintenanceContractTests(unittest.TestCase):
    def test_historical_cycle20_gateway_time_is_aggregated(self):
        source = PI / "results/cycle20b-semantic-edit-recovery/real-agent-02/gateway-tool-timings.jsonl"
        rows = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line]
        summary = _load_runner().aggregate_gateway_timings(rows)
        self.assertEqual(summary["total_ms"], 276.538)
        self.assertEqual(summary["call_count"], 5)
        self.assertEqual(summary["by_method_ms"]["validate_mission"], 132.636)

    @unittest.skipUnless(shutil.which("bun") and (SCHEMA_DIR / "tool-schemas.json").is_file(),
        "Cycle 21 production-dispatch regression requires Bun and the captured Pi schema")
    def test_both_contracts_cross_the_real_typescript_and_jsonl_boundary(self):
        with tempfile.TemporaryDirectory(prefix="cycle21-contract-", dir="/var/tmp") as temp:
            output = pathlib.Path(temp) / "preflight"
            result = subprocess.run([sys.executable, str(PI / "cycle21_preflight.py"),
                "--output", str(output), "--pi-schema-dir", str(SCHEMA_DIR)],
                capture_output=True, text=True, timeout=120)
            self.assertEqual(result.returncode, 0, result.stderr[-3000:] + result.stdout[-3000:])
            summary = json.loads((output / "preflight-summary.json").read_text(encoding="utf-8"))
            self.assertTrue(summary["all_preflight_checks_passed"])
            self.assertEqual(len(summary["mission_a_historical_proposals"]), 4)
            self.assertEqual(summary["active_tools"], ["workspace_discover_functions", "workspace_inspect_program",
                "workspace_preview_semantic_edit", "workspace_commit_preview", "workspace_validate_mission"])
            self.assertTrue(summary["mission_a_disposable_commit_validation_replay"] == "passed")
            self.assertTrue(summary["mission_b_disposable_commit_validation_replay"] == "passed")
            self.assertTrue(all(row["revision_unchanged"] for row in summary["negative_controls"]))
            self.assertEqual(summary["active_pi_schema_bytes"], (SCHEMA_DIR / "tool-schemas.json").stat().st_size)


if __name__ == "__main__":
    unittest.main()
