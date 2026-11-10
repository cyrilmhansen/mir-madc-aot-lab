from __future__ import annotations

import copy
import json
import pathlib
import shutil
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PI = ROOT / "pi-integration"
RESULTS = PI / "results/cycle36-verified-handoff/production-bridge-attempt-06"
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(PI))

from basic_workspace.model import WorkspaceError  # noqa: E402
from cycle20_gateway import Cycle20Gateway  # noqa: E402
from verified_handoff import verify_handoff  # noqa: E402


def read(path):
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


class Cycle36VerifiedHandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="atlas-cycle36-handoff-", dir="/var/tmp")
        self.addCleanup(self.tmp.cleanup)
        self.temp = pathlib.Path(self.tmp.name)

    def paths(self, mission="mission-a"):
        root = RESULTS / mission
        return (root / "handoff/handoff.json", root / "handoff/host-trust-anchor.json",
            root / "creation/gateway-evidence", root / "maintenance-contract.json")

    def test_both_missions_verify_from_separate_anchor(self):
        for mission, revision, handles in (("mission-a", 5, 21), ("mission-b", 4, 16)):
            with self.subTest(mission=mission):
                handoff, anchor, root, contract = self.paths(mission)
                result = verify_handoff(handoff, anchor, root, contract)
                self.assertTrue(result["passed"])
                self.assertEqual(result["revision"], revision)
                self.assertEqual(result["portable_handle_count"], handles)
                self.assertEqual(result["checkpoint_count"], revision - 1)

    def test_modified_bundle_and_internal_digest_do_not_override_trust_anchor(self):
        handoff, anchor, root, contract = self.paths()
        target = self.temp / "handoff.json"
        value = read(handoff)
        value["artifacts"]["constructive_stream"]["sha256"] = "0" * 64
        value["source_sequence_id"] = "attacker-selected"
        target.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaises(WorkspaceError) as caught:
            verify_handoff(target, anchor, root, contract)
        self.assertEqual(caught.exception.code, "HANDOFF_TRUST_ANCHOR_MISMATCH")

    def test_missing_bundle_anchor_and_unsupported_schema_fail_closed(self):
        handoff, anchor, root, contract = self.paths()
        with self.assertRaises(WorkspaceError) as missing:
            verify_handoff(self.temp / "absent.json", anchor, root, contract)
        self.assertEqual(missing.exception.code, "HANDOFF_MISSING")
        with self.assertRaises(WorkspaceError) as missing_anchor:
            verify_handoff(handoff, self.temp / "absent-anchor.json", root, contract)
        self.assertEqual(missing_anchor.exception.code, "HANDOFF_ANCHOR_MISSING")
        unsupported = read(handoff); unsupported["version"] = 9
        bad = self.temp / "unsupported-version.json"; bad.write_text(json.dumps(unsupported), encoding="utf-8")
        with self.assertRaises(WorkspaceError) as version:
            verify_handoff(bad, anchor, root, contract)
        self.assertEqual(version.exception.code, "HANDOFF_SCHEMA")

    def test_source_artifact_tampering_fails_digest_check(self):
        handoff, anchor, root, contract = self.paths()
        copied_root = self.temp / "evidence"
        shutil.copytree(root, copied_root)
        with (copied_root / "constructive-operations.json").open("a", encoding="utf-8") as stream:
            stream.write(" ")
        with self.assertRaises(WorkspaceError) as caught:
            verify_handoff(handoff, anchor, copied_root, contract)
        self.assertEqual(caught.exception.code, "HANDOFF_ARTIFACT_DIGEST")

    def test_destination_contract_is_bound_to_trusted_anchor(self):
        handoff, anchor, root, _contract = self.paths()
        other_contract = self.paths("mission-b")[3]
        with self.assertRaises(WorkspaceError) as caught:
            verify_handoff(handoff, anchor, root, other_contract)
        self.assertEqual(caught.exception.code, "HANDOFF_TRUST_BINDING")

    def _gateway(self, label):
        handoff, anchor, root, contract = self.paths(label)
        return Cycle20Gateway(self.temp / f"gateway-{label}-{len(list(self.temp.iterdir()))}",
            contract_path=contract, verified_handoff_path=handoff, handoff_anchor_path=anchor,
            handoff_evidence_root=root)

    @staticmethod
    def _request(gateway):
        return {"expected_revision": gateway.base_revision, "scope_mode": "per_target", "edits": [
            {"target": copy.deepcopy(row["target"]), "expected_value": row["expected_value"],
             "replacement_value": row["replacement_constraint"]["values"][0]} for row in gateway.edit_targets]}

    @staticmethod
    def _snapshot(gateway):
        return (gateway.ws.get_revision(gateway.doc), gateway.ws.render_document(gateway.doc),
            [(token.uid, token.text) for token in gateway.ws.documents[gateway.doc].tokens], gateway._normalized())

    def test_rejected_cross_function_proposals_are_non_mutating(self):
        gateway = self._gateway("mission-a")
        good = self._request(gateway)
        before = self._snapshot(gateway)
        undiscovered = gateway.handle("preview_semantic_edit", good, "undiscovered")
        self.assertEqual(undiscovered["code"], "FUNCTION_NOT_DISCOVERED")
        self.assertEqual(self._snapshot(gateway), before)
        gateway.handle("discover_functions", {}, "discover-all")
        controls = []
        stale = copy.deepcopy(good); stale["expected_revision"] -= 1
        controls.append((stale, "STALE_REVISION"))
        wrong_old = copy.deepcopy(good); wrong_old["edits"][0]["expected_value"] = -1
        controls.append((wrong_old, "MISSION_LITERAL_VALUES"))
        bad_value = copy.deepcopy(good); bad_value["edits"][0]["replacement_value"] = 81
        controls.append((bad_value, "MISSION_LITERAL_VALUES"))
        invented = copy.deepcopy(good); invented["edits"][0]["target"]["function_handle"] = "invented.function"
        controls.append((invented, "MISSION_EDIT_TARGETS"))
        wrong_path = copy.deepcopy(good); wrong_path["edits"][0]["target"]["control_path"][0]["index"] = 0
        controls.append((wrong_path, "MISSION_EDIT_TARGETS"))
        incomplete = copy.deepcopy(good); incomplete["edits"] = incomplete["edits"][:-1]
        controls.append((incomplete, "MISSION_EDIT_COUNT"))
        duplicate = copy.deepcopy(good); duplicate["edits"][1] = copy.deepcopy(duplicate["edits"][0])
        controls.append((duplicate, "DUPLICATE_EDIT_TARGET"))
        unknown = copy.deepcopy(good); unknown["extra"] = True
        controls.append((unknown, "INVALID_EDIT_REQUEST"))
        mixed = copy.deepcopy(good); mixed["edits"][2]["target"]["function_handle"] = "third.function"
        controls.append((mixed, "MISSION_EDIT_TARGETS"))
        for index, (request, code) in enumerate(controls):
            with self.subTest(code=code, index=index):
                result = gateway.handle("preview_semantic_edit", request, f"reject-{index}")
                self.assertFalse(result["ok"])
                self.assertEqual(result["code"], code)
                self.assertEqual(self._snapshot(gateway), before)

    def test_preview_restart_candidate_revalidation_and_one_atomic_commit(self):
        gateway = self._gateway("mission-a"); gateway.handle("discover_functions", {}, "discover")
        before = self._snapshot(gateway)
        request = self._request(gateway)
        preview = gateway.handle("preview_semantic_edit", request, "preview")
        self.assertTrue(preview["ok"])
        self.assertEqual(self._snapshot(gateway), before)
        restarted = self._gateway("mission-a")
        lost = restarted.handle("commit_preview", {"transaction_id": preview["transaction_id"]}, "restart-commit")
        self.assertEqual(lost["code"], "PREVIEW_NOT_FOUND")
        self.assertEqual(restarted.ws.get_revision(restarted.doc), 5)
        with self.assertRaises(WorkspaceError) as changed:
            gateway.transactions.commit(preview["transaction_id"],
                lambda record, revision: (record["operations"], {"tampered_candidate": True}, {}))
        self.assertEqual(changed.exception.code, "PREVIEW_CANDIDATE_CHANGED")
        self.assertEqual(self._snapshot(gateway), before)
        preview = gateway.handle("preview_semantic_edit", request, "preview-accepted")
        commit = gateway.handle("commit_preview", {"transaction_id": preview["transaction_id"]}, "commit")
        self.assertTrue(commit["committed"])
        self.assertEqual(commit["revision"], 6)
        validation = gateway.validate_current(6)
        self.assertTrue(validation["mission_complete"])
        duplicate = gateway.handle("commit_preview", {"transaction_id": preview["transaction_id"]}, "duplicate")
        self.assertFalse(duplicate["committed"])
        self.assertEqual(duplicate["code"], "STALE_REVISION")
        self.assertEqual(gateway.ws.get_revision(gateway.doc), 6)


if __name__ == "__main__":
    unittest.main()
