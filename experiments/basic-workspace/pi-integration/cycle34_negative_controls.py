#!/usr/bin/env python3
"""Record non-mutating Cycle34 v2 rejection controls against the real gateway class."""
from __future__ import annotations
import copy, hashlib, json, pathlib, sys, tempfile
HERE = pathlib.Path(__file__).resolve().parent
RESULTS = HERE / "results/cycle34-cross-function-authorization"
sys.path.insert(0, str(HERE.parent)); sys.path.insert(0, str(HERE))
from cycle20_gateway import Cycle20Gateway

def fingerprint(g):
    value = {"revision": g.ws.get_revision(g.doc), "semantics": g._normalized()}
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

def request_for(g):
    return {"expected_revision": 3, "scope_mode": "per_target", "edits": [
        {"target": copy.deepcopy(row["target"]), "expected_value": row["expected_value"],
         "replacement_value": row["replacement_constraint"]["values"][0]} for row in g.edit_targets]}

def run():
    rows = []
    with tempfile.TemporaryDirectory(prefix="atlas-cycle34-negative-", dir="/var/tmp") as temp:
        g = Cycle20Gateway(pathlib.Path(temp) / "gateway", contract_path=RESULTS / "primary-contract.json")
        g.handle("discover_functions", {}, "discover")
        good = request_for(g)
        cases = []
        def add(name, mutate, code):
            candidate = copy.deepcopy(good); mutate(candidate); cases.append((name, candidate, code))
        add("global-v1-handle-in-v2", lambda r: r.update(function_handle="clamp_score.function"), "INVALID_EDIT_REQUEST")
        add("invented-portable-handle", lambda r: r["edits"][0]["target"].update(function_handle="invented.function"), "MISSION_EDIT_TARGETS")
        add("unauthorized-third-function", lambda r: r["edits"][0]["target"].update(function_handle="score_class.function"), "MISSION_EDIT_TARGETS")
        add("unauthorized-path", lambda r: r["edits"][2]["target"].update(control_path=[{"block":"body","index":1}]), "MISSION_EDIT_TARGETS")
        add("extra-target", lambda r: r["edits"].append(copy.deepcopy(r["edits"][0])), "MISSION_EDIT_COUNT")
        add("incomplete-target-set", lambda r: r["edits"].pop(), "MISSION_EDIT_COUNT")
        add("duplicate-target", lambda r: r["edits"].__setitem__(1, copy.deepcopy(r["edits"][0])), "DUPLICATE_EDIT_TARGET")
        add("wrong-expected-value", lambda r: r["edits"][0].update(expected_value=99), "MISSION_LITERAL_VALUES")
        add("disallowed-replacement", lambda r: r["edits"][0].update(replacement_value=51), "MISSION_LITERAL_VALUES")
        add("nan", lambda r: r["edits"][0].update(replacement_value=float("nan")), "INVALID_LITERAL_EDIT")
        add("boolean-number", lambda r: r["edits"][0].update(expected_value=True), "INVALID_LITERAL_EDIT")
        add("stale-revision", lambda r: r.update(expected_revision=2), "STALE_REVISION")
        add("unknown-semantic-field", lambda r: r.update(unrecognized=True), "INVALID_EDIT_REQUEST")
        add("transport-field-leak", lambda r: r.update(toolCallId="transport-only"), "INVALID_EDIT_REQUEST")
        add("wrong-scope-mode", lambda r: r.update(scope_mode="global"), "INVALID_EDIT_REQUEST")
        initial = fingerprint(g)
        for name, candidate, expected in cases:
            before = g.ws.get_revision(g.doc)
            result = g.handle("preview_semantic_edit", candidate, name)
            after = g.ws.get_revision(g.doc)
            actual = result.get("code") if not result.get("ok") else "UNEXPECTED_ACCEPT"
            rows.append({"case": name, "expected_code": expected, "actual_code": actual,
                "passed": actual == expected, "revision_before": before, "revision_after": after,
                "normalized_state_unchanged": fingerprint(g) == initial,
                "committed": False, "rejection_stage": "preview_authorization"})
        preview = g.handle("preview_semantic_edit", good, "candidate-tamper-preview")
        before = g.ws.get_revision(g.doc)
        try:
            g.transactions.commit(preview["transaction_id"],
                lambda record, revision: (record["operations"], {"tampered": True}, {}))
            actual = "UNEXPECTED_ACCEPT"
        except Exception as exc:
            actual = getattr(exc, "code", type(exc).__name__)
        rows.append({"case": "candidate-changed-after-preview", "expected_code": "PREVIEW_CANDIDATE_CHANGED",
            "actual_code": actual, "passed": actual == "PREVIEW_CANDIDATE_CHANGED", "revision_before": before,
            "revision_after": g.ws.get_revision(g.doc), "normalized_state_unchanged": fingerprint(g) == initial,
            "committed": False, "rejection_stage": "transaction_kernel_candidate_fingerprint"})
        # A proposal approved at preview cannot be committed after its authorized request is altered.
        preview = g.handle("preview_semantic_edit", good, "commit-policy-preview")
        record = g.transactions._pending[preview["transaction_id"]]
        record["metadata"]["request"]["edits"][2]["target"]["control_path"][0]["index"] = 1
        before = g.ws.get_revision(g.doc)
        denied = g.handle("commit_preview", {"transaction_id": preview["transaction_id"]}, "commit-policy-tamper")
        rows.append({"case": "unauthorized-target-added-during-commit-revalidation",
            "expected_code": "MISSION_EDIT_TARGETS", "actual_code": denied.get("code"),
            "passed": denied.get("code") == "MISSION_EDIT_TARGETS", "revision_before": before,
            "revision_after": g.ws.get_revision(g.doc), "normalized_state_unchanged": fingerprint(g) == initial,
            "committed": bool(denied.get("committed")), "rejection_stage": "commit_revalidation"})
        with tempfile.TemporaryDirectory(prefix="atlas-cycle34-duplicate-", dir="/var/tmp") as dup_temp:
            duplicate_gateway = Cycle20Gateway(pathlib.Path(dup_temp) / "gateway",
                contract_path=RESULTS / "primary-contract.json")
            duplicate_gateway.handle("discover_functions", {}, "discover")
            duplicate_preview = duplicate_gateway.handle("preview_semantic_edit", request_for(duplicate_gateway), "preview")
            first = duplicate_gateway.handle("commit_preview", {"transaction_id": duplicate_preview["transaction_id"]}, "commit")
            before = duplicate_gateway.ws.get_revision(duplicate_gateway.doc)
            before_fingerprint = fingerprint(duplicate_gateway)
            duplicate = duplicate_gateway.handle("commit_preview", {"transaction_id": duplicate_preview["transaction_id"]}, "duplicate")
            rows.append({"case": "duplicate-commit", "expected_code": "STALE_REVISION",
                "actual_code": duplicate.get("code"), "passed": first.get("committed") is True and duplicate.get("code") == "STALE_REVISION",
                "revision_before": before, "revision_after": duplicate_gateway.ws.get_revision(duplicate_gateway.doc),
                "normalized_state_unchanged": fingerprint(duplicate_gateway) == before_fingerprint,
                "committed": bool(duplicate.get("committed")), "rejection_stage": "transaction_kernel_revision_check"})
        output = {"schema": "basic-workspace.cycle34-negative-controls", "version": 1,
            "mission_id": g.mission_id, "controls": rows, "all_passed": all(row["passed"] and row["normalized_state_unchanged"] for row in rows)}
        (RESULTS / "negative-controls.json").write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
        return output

if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
