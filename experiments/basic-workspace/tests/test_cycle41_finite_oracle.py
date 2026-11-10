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
RESULTS = PI / "results/cycle34-cross-function-authorization"
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(PI))

from basic_workspace.model import WorkspaceError  # noqa: E402
from cycle20_gateway import Cycle20Gateway  # noqa: E402
from verified_rename_continuation import verify_rename_continuation  # noqa: E402


def contract(validation):
    return {"schema": "basic-workspace.numeric-literal-maintenance-contract", "version": 3,
        "mission_id": "cycle41.test.v3", "objective": "test finite expected results",
        "base_document_revision": 3, "execution_profile_id": "basic-workspace.numeric-composition.v1",
        "allowed_function_handles": ["provider.function", "caller.function"],
        "authorized_targets": [{"target": {"function_handle": "provider.function", "control_path": [{"block": "body", "index": 0}], "expression_path": [1]},
            "expected_original_value": 10, "replacement_constraint": {"kind": "one_of", "values": [8]}, "label": "test"}],
        "minimum_edits": 1, "maximum_edits": 1,
        "unchanged_function_handles": [], "required_dependency_edges": [], "revision_increment": 1,
        "scope_mode": "per_target", "validation": validation}


class Cycle41FiniteOracleTests(unittest.TestCase):
    def valid_validation(self):
        return {"mode": "finite_expected_results", "inputs": [-1, 0, 1],
            "functions": [{"function_handle": "provider.function", "result_key": "provider"},
                {"function_handle": "caller.function", "result_key": "caller"}],
            "expected_results": [{"provider": 0, "caller": 0}, {"provider": 1, "caller": 0}, {"provider": 2, "caller": 1}]}

    def test_finite_vector_shape_and_positional_expectations(self):
        c = contract(self.valid_validation())
        Cycle20Gateway._validate_contract_shape(c)
        gateway = object.__new__(Cycle20Gateway); gateway.contract = c
        expected = gateway._expected_observations()
        self.assertEqual(expected["interp"]["-1"], {"provider": 0, "caller": 0})
        self.assertEqual(expected["interp"]["1"], {"provider": 2, "caller": 1})
        self.assertEqual(expected["interp"], expected["jit"])

    def test_finite_table_rejects_malformed_or_ambiguous_values(self):
        mutations = []
        v = self.valid_validation(); v["expected_results"].pop(); mutations.append(v)
        v = self.valid_validation(); v["inputs"].append(2); mutations.append(v)
        v = self.valid_validation(); v["expected_results"][0].pop("caller"); mutations.append(v)
        v = self.valid_validation(); v["expected_results"][0]["extra"] = 2; mutations.append(v)
        v = self.valid_validation(); v["functions"].append(copy.deepcopy(v["functions"][0])); mutations.append(v)
        v = self.valid_validation(); v["inputs"][1] = True; mutations.append(v)
        v = self.valid_validation(); v["expected_results"][1]["provider"] = False; mutations.append(v)
        v = self.valid_validation(); v["inputs"][1] = v["inputs"][0]; mutations.append(v)
        v = self.valid_validation(); v["expected_results"][2]["caller"] = float("inf"); mutations.append(v)
        v = self.valid_validation(); v["expected_results"][0]["provider"] = 10**10000; mutations.append(v)
        v = self.valid_validation(); v["functions"][1]["result_key"] = "provider"; mutations.append(v)
        v = self.valid_validation(); v["mode"] = "arbitrary_expression"; mutations.append(v)
        v = self.valid_validation(); v["inputs"] = list(range(65)); v["expected_results"] = [{"provider": 0, "caller": 0}] * 65; mutations.append(v)
        v = self.valid_validation(); v["functions"] = [{"function_handle": f"f{i}.function", "result_key": f"f{i}"} for i in range(9)]; v["expected_results"] = [{f"f{i}": 0 for i in range(9)} for _ in v["inputs"]]; mutations.append(v)
        for bad in mutations:
            with self.subTest(validation=bad):
                with self.assertRaises(WorkspaceError):
                    Cycle20Gateway._validate_contract_shape(contract(bad))

    def test_contract_version_and_unknown_fields_fail_closed(self):
        c = contract(self.valid_validation()); c["version"] = 4
        with self.assertRaises(WorkspaceError): Cycle20Gateway._validate_contract_shape(c)
        c = contract(self.valid_validation()); c["unexpected"] = True
        with self.assertRaises(WorkspaceError): Cycle20Gateway._validate_contract_shape(c)

    def test_v2_and_v3_commit_equivalent_authorized_mutation(self):
        source = json.loads((RESULTS / "primary-contract.json").read_text())
        v3 = copy.deepcopy(source); v3["version"] = 3
        functions = [{"function_handle": row["function_handle"], "result_key": row["result_key"]}
            for row in source["validation"]["functions"]]
        inputs = source["validation"]["inputs"]
        expected = []
        for x in inputs:
            score = min(50, max(0, x))
            expected.append({"clamp_score": score, "is_passing": int(score >= 45)})
        v3["validation"] = {"mode": "finite_expected_results", "inputs": inputs,
            "functions": functions, "expected_results": expected}
        with tempfile.TemporaryDirectory(prefix="atlas-cycle41-v2v3-", dir="/var/tmp") as temp:
            root = pathlib.Path(temp); v3_path = root / "v3-contract.json"
            v3_path.write_text(json.dumps(v3), encoding="utf-8")
            old = Cycle20Gateway(root / "v2-run", contract_path=RESULTS / "primary-contract.json")
            new = Cycle20Gateway(root / "v3-run", contract_path=v3_path)
            old.handle("discover_functions", {}, "discover-v2")
            new.handle("discover_functions", {}, "discover-v3")
            def request(g):
                return {"expected_revision": 3, "scope_mode": "per_target", "edits": [
                    {"target": copy.deepcopy(row["target"]), "expected_value": row["expected_value"],
                     "replacement_value": row["replacement_constraint"]["values"][0]} for row in g.edit_targets]}
            initial_old, initial_new = old._normalized(), new._normalized()
            pv2 = old.handle("preview_semantic_edit", request(old), "preview-v2")
            pv3 = new.handle("preview_semantic_edit", request(new), "preview-v3")
            self.assertTrue(pv2["ok"], pv2); self.assertTrue(pv3["ok"], pv3)
            self.assertEqual(old._normalized(), initial_old); self.assertEqual(new._normalized(), initial_new)
            self.assertTrue(old.handle("commit_preview", {"transaction_id": pv2["transaction_id"]}, "commit-v2")["committed"])
            self.assertTrue(new.handle("commit_preview", {"transaction_id": pv3["transaction_id"]}, "commit-v3")["committed"])
            val2, val3 = old.validate_current(4), new.validate_current(4)
            self.assertTrue(val2["mission_complete"], val2); self.assertTrue(val3["mission_complete"], val3)
            self.assertEqual(old._normalized(), new._normalized())
            self.assertEqual(old.constructive_ops, new.constructive_ops)
            self.assertEqual(val2["observed_results"], val3["observed_results"])

    def test_wrong_well_formed_table_rejects_candidate_before_commit(self):
        source = json.loads((RESULTS / "primary-contract.json").read_text())
        v3 = copy.deepcopy(source); v3["version"] = 3
        inputs = source["validation"]["inputs"]
        expected = []
        for x in inputs:
            score = min(50, max(0, x)); expected.append({"clamp_score": score, "is_passing": int(score >= 45)})
        expected[0]["clamp_score"] += 1
        v3["validation"] = {"mode": "finite_expected_results", "inputs": inputs,
            "functions": [{"function_handle": row["function_handle"], "result_key": row["result_key"]}
                for row in source["validation"]["functions"]], "expected_results": expected}
        with tempfile.TemporaryDirectory(prefix="atlas-cycle41-bad-table-", dir="/var/tmp") as temp:
            root = pathlib.Path(temp); path = root / "contract.json"; path.write_text(json.dumps(v3), encoding="utf-8")
            g = Cycle20Gateway(root / "gateway", contract_path=path); g.handle("discover_functions", {}, "discover")
            # A post-initialization file rewrite cannot replace the trusted
            # in-memory expectations used by preview/commit revalidation.
            repaired_file = copy.deepcopy(v3)
            repaired_file["validation"]["expected_results"][0]["clamp_score"] -= 1
            path.write_text(json.dumps(repaired_file), encoding="utf-8")
            request = {"expected_revision": 3, "scope_mode": "per_target", "edits": [
                {"target": copy.deepcopy(row["target"]), "expected_value": row["expected_value"],
                 "replacement_value": row["replacement_constraint"]["values"][0]} for row in g.edit_targets]}
            before = (g.ws.get_revision(g.doc), g._normalized())
            result = g.handle("preview_semantic_edit", request, "wrong-well-formed-table")
            self.assertFalse(result["ok"]); self.assertEqual(result["code"], "MISSION_PREVIEW_ORACLE")
            self.assertEqual((g.ws.get_revision(g.doc), g._normalized()), before)

    def test_consistently_reordered_input_rows_preserve_expected_map(self):
        c = contract(self.valid_validation()); gateway = object.__new__(Cycle20Gateway); gateway.contract = c
        before = gateway._expected_observations()["interp"]
        validation = c["validation"]
        validation["inputs"] = list(reversed(validation["inputs"]))
        validation["expected_results"] = list(reversed(validation["expected_results"]))
        Cycle20Gateway._validate_contract_shape(c)
        self.assertEqual(gateway._expected_observations()["interp"], before)

    def test_finite_oracle_handles_must_resolve_after_authenticated_replay(self):
        source = json.loads((RESULTS / "primary-contract.json").read_text())
        v3 = copy.deepcopy(source); v3["version"] = 3
        v3["validation"] = {"mode": "finite_expected_results", "inputs": [0],
            "functions": [{"function_handle": "invented.function", "result_key": "invented"}],
            "expected_results": [{"invented": 0}]}
        with tempfile.TemporaryDirectory(prefix="atlas-cycle41-unknown-handle-", dir="/var/tmp") as temp:
            root = pathlib.Path(temp); path = root / "contract.json"; path.write_text(json.dumps(v3), encoding="utf-8")
            with self.assertRaises(WorkspaceError) as caught:
                Cycle20Gateway(root / "gateway", contract_path=path)
            self.assertEqual(caught.exception.code, "MISSION_CONTRACT_HANDLE")

    def test_v3_destination_table_is_bound_by_external_continuation_anchor(self):
        workflow = PI / "results/cycle41-finite-oracle-coverage/attempt-02-primary/workflow-01"
        original_package = workflow / "continuation-package"
        original_anchor = workflow / "continuation-package-host-trust-anchor.json"
        with tempfile.TemporaryDirectory(prefix="atlas-cycle41-v3-anchor-", dir="/var/tmp") as temp:
            root = pathlib.Path(temp); package = root / "package"
            shutil.copytree(original_package, package)
            anchor = root / "host-anchor.json"; shutil.copyfile(original_anchor, anchor)
            contract_path = package / "maintenance-contract.json"
            changed = json.loads(contract_path.read_text())
            changed["validation"]["expected_results"][0][changed["validation"]["functions"][0]["result_key"]] += 1
            contract_path.write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaises(WorkspaceError) as caught:
                verify_rename_continuation(package / "continuation.json", anchor, package, contract_path)
            self.assertEqual(caught.exception.code, "CONTINUATION_ARTIFACT_DIGEST")
            # A separately supplied replacement contract is checked against the
            # destination identity and digest recorded in the trusted bundle.
            shutil.copyfile(original_package / "maintenance-contract.json", contract_path)
            alternate = root / "alternate-contract.json"
            alternate.write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaises(WorkspaceError) as caught:
                verify_rename_continuation(package / "continuation.json", anchor, package, alternate)
            self.assertEqual(caught.exception.code, "CONTINUATION_DESTINATION_MISMATCH")


if __name__ == "__main__": unittest.main()
