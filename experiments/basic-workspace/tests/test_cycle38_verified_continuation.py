from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PI = ROOT / "pi-integration"
import sys
sys.path.insert(0, str(PI))
sys.path.insert(0, str(ROOT))

from basic_workspace.model import WorkspaceError
from verified_rename_continuation import verify_rename_continuation


ATTEMPT = PI / "results/cycle38-longitudinal-stress/production-bridge-attempt-07"


class Cycle38VerifiedContinuationTests(unittest.TestCase):
    def package(self, mission: str) -> Path:
        return ATTEMPT / mission / "continuation-package"

    def test_both_rename_continuations_authenticate(self):
        for mission, final_revision in (("mission-a", 6), ("mission-b", 5)):
            with self.subTest(mission=mission):
                package = self.package(mission)
                checked = verify_rename_continuation(package / "continuation.json",
                    package / "host-trust-anchor.json", package, package / "maintenance-contract.json")
                self.assertTrue(checked["all_checks_passed"])
                self.assertEqual(checked["revision"], final_revision)
                identity_rows = json.loads((ATTEMPT / mission / "maintenance/gateway-evidence/baseline-reconstruction.json").read_text())["identity_mapping"]
                self.assertEqual(set(checked["aliases"]), {row["portable_handle"] for row in identity_rows})
                self.assertTrue(all(row["remapped"] for row in identity_rows))

    def test_modified_bundle_cannot_rebind_external_host_anchor(self):
        source = self.package("mission-a")
        with tempfile.TemporaryDirectory(prefix="atlas-cycle38-test-", dir="/var/tmp") as raw:
            package = Path(raw) / "package"
            shutil.copytree(source, package)
            bundle_path = package / "continuation.json"
            bundle = json.loads(bundle_path.read_text())
            bundle["semantic_fingerprint"] = "0" * 64
            bundle_path.write_text(json.dumps(bundle))
            with self.assertRaises(WorkspaceError) as caught:
                verify_rename_continuation(bundle_path, package / "host-trust-anchor.json", package,
                    package / "maintenance-contract.json")
            self.assertEqual(caught.exception.code, "CONTINUATION_TRUST_ANCHOR")

    def test_artifact_tampering_is_rejected_before_workspace_activation(self):
        source = self.package("mission-b")
        with tempfile.TemporaryDirectory(prefix="atlas-cycle38-test-", dir="/var/tmp") as raw:
            package = Path(raw) / "package"
            shutil.copytree(source, package)
            artifact = package / "rename/constructive-operations.json"
            artifact.write_text(artifact.read_text() + " ")
            with self.assertRaises(WorkspaceError) as caught:
                verify_rename_continuation(package / "continuation.json", package / "host-trust-anchor.json",
                    package, package / "maintenance-contract.json")
            self.assertEqual(caught.exception.code, "CONTINUATION_ARTIFACT_DIGEST")

    def test_destination_contract_is_bound_to_continuation(self):
        source = self.package("mission-a")
        with tempfile.TemporaryDirectory(prefix="atlas-cycle38-test-", dir="/var/tmp") as raw:
            package = Path(raw) / "package"
            shutil.copytree(source, package)
            destination = package / "other-maintenance-contract.json"
            contract = json.loads((package / "maintenance-contract.json").read_text())
            contract["mission_id"] = "cycle38.other.destination"
            destination.write_text(json.dumps(contract))
            with self.assertRaises(WorkspaceError) as caught:
                verify_rename_continuation(package / "continuation.json", package / "host-trust-anchor.json",
                    package, destination)
            self.assertEqual(caught.exception.code, "CONTINUATION_DESTINATION_MISMATCH")


if __name__ == "__main__":
    unittest.main()
