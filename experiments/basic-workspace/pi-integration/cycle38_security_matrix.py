#!/usr/bin/env python3
"""Run fail-closed continuation tampering controls and collect bridge controls."""
from __future__ import annotations

import copy
import json
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

from verified_rename_continuation import verify_rename_continuation
from basic_workspace.model import WorkspaceError


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def dump(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def continuation_cases(original: Path, original_anchor: Path, tmp: Path) -> list[dict]:
    package = tmp / "package"
    shutil.copytree(original, package)
    bundle_path = package / "continuation.json"
    anchor_path = tmp / "host-trust-anchor.json"
    shutil.copyfile(original_anchor, anchor_path)
    dest_path = package / "maintenance-contract.json"
    bundle_base, anchor_base = read(bundle_path), read(anchor_path)
    cases: list[dict] = []

    def check(name, attack, stage="continuation_receiver"):
        shutil.rmtree(package)
        shutil.copytree(original, package)
        shutil.copyfile(original_anchor, anchor_path)
        try:
            attack()
            verify_rename_continuation(bundle_path, anchor_path, package, dest_path)
            actual = "ACCEPTED_UNEXPECTEDLY"
        except WorkspaceError as exc:
            actual = exc.code
        cases.append({"case": name, "stage": stage, "expected": "reject", "actual": actual,
            "authoritative_revision_before": None, "authoritative_revision_after": None,
            "fingerprint_before": None, "fingerprint_after": None,
            "transaction_committed": False, "stage_transition_advanced": False,
            "state": "isolated evidence verification; no mutable Workspace was supplied"})

    def mutate_bundle(field, value):
        data = read(bundle_path); data[field] = value; dump(bundle_path, data)

    check("continuation bundle schema field", lambda: mutate_bundle("unexpected", True))
    check("wrong source sequence identity", lambda: mutate_bundle("source_sequence_id", "other-sequence"))
    check("wrong final revision", lambda: mutate_bundle("final_revision", bundle_base["final_revision"] + 2))
    check("altered post-rename fingerprint", lambda: mutate_bundle("semantic_fingerprint", "0" * 64))
    check("altered live identity ledger", lambda: mutate_bundle("live_handles", bundle_base["live_handles"][:-1]))
    check("unexpected retired identity", lambda: mutate_bundle("retired_handles", ["score_class.statement.0"]))
    check("wrong dependency graph", lambda: mutate_bundle("dependencies", []))
    check("wrong destination contract id", lambda: mutate_bundle("destination_contract_id", "other-contract"))
    check("wrong destination digest", lambda: mutate_bundle("destination_contract_sha256", "1" * 64))
    check("wrong source evidence root", lambda: mutate_bundle("source_evidence_root", "../outside"))
    check("operation count tampering", lambda: mutate_bundle("operation_count", 1))
    check("rename contract digest tampering", lambda: mutate_bundle("rename_contract_sha256", "2" * 64))
    check("external host anchor tampering", lambda: dump(anchor_path, {**anchor_base, "semantic_fingerprint": "3" * 64}))
    def bundle_and_internal_checksum():
        data = read(bundle_path)
        data["semantic_fingerprint"] = "4" * 64
        data["artifacts"]["rename_stream"]["sha256"] = "5" * 64
        dump(bundle_path, data)
    check("bundle and internal checksum changed against unchanged host anchor", bundle_and_internal_checksum)
    check("continuation artifact path traversal", lambda: (lambda d: (d["artifacts"]["rename_stream"].update({"path": "../escape"}), dump(bundle_path, d)))(read(bundle_path)))

    # Artifact-level attacks leave the independently anchored bundle intact;
    # the verifier must reject them against the per-artifact digest.
    artifact_names = [
        ("source handoff revision altered", "source/handoff.json"),
        ("source host anchor altered", "source/anchor.json"),
        ("rename contract altered", "rename-contract.json"),
        ("rename operation reordered", "rename/constructive-operations.json"),
        ("rename transaction journal altered", "rename/history.jsonl"),
        ("rename host validation receipt altered", "rename/mission-validation-host.json"),
        ("rename baseline identity map altered", "rename/baseline-reconstruction.json"),
        ("destination maintenance contract altered", "maintenance-contract.json"),
    ]
    for name, relative in artifact_names:
        path = package / relative
        original_bytes = path.read_bytes()
        def attack(path=path, original_bytes=original_bytes):
            if path.suffix == ".jsonl":
                path.write_text(original_bytes.decode("utf-8") + "{\"event\":\"tampered\"}\n", encoding="utf-8")
            else:
                data = json.loads(original_bytes)
                data["tampered_by_cycle38"] = True
                dump(path, data)
        check(name, attack)

    # Passing a different destination file is a boundary mismatch even when
    # the continuation package itself has not been altered.
    def wrong_destination():
        altered = read(dest_path); altered["mission_id"] = "mission-from-other-run"
        dump(dest_path, altered)
    check("destination contract substitution", wrong_destination)

    # Missing artifacts and incomplete source evidence fail before gateway
    # activation, rather than being treated as weaker proof.
    check("missing rename transcript", lambda: (package / "rename/history.jsonl").unlink())
    check("missing creation checkpoint", lambda: (package / "source/evidence/checkpoint-step-01.json").unlink())
    return cases


def bridge_cases(root: Path) -> list[dict]:
    rows: list[dict] = []
    for mission in ("mission-a", "mission-b"):
        mission_root = root / mission
        for path in sorted(mission_root.rglob("dispatch-output.json")):
            data = read(path)
            for index, result in enumerate(data.get("controls", [])):
                code = result.get("code", "UNKNOWN")
                rows.append({"case": f"{mission}:{path.parent.name}:control-{index + 1}",
                    "stage": "actual_typescript_jsonl_gateway", "expected": "reject", "actual": code,
                    "authoritative_revision_before": result.get("revision"),
                    "authoritative_revision_after": result.get("revision") if result.get("revision_unchanged") else None,
                    "fingerprint_before": None, "fingerprint_after": None,
                    "transaction_committed": False,
                    "stage_transition_advanced": False,
                    "state_unchanged": result.get("revision_unchanged") is True
                        and result.get("authoritative_workspace_changed") is False})
            for index, rejected in enumerate(data.get("schema_rejections", [])):
                rows.append({"case": f"{mission}:{path.parent.name}:schema-{index + 1}",
                    "stage": "typescript_tool_schema", "expected": "reject", "actual": "schema_rejected",
                    "authoritative_revision_before": None, "authoritative_revision_after": None,
                    "fingerprint_before": None, "fingerprint_after": None,
                    "transaction_committed": False, "stage_transition_advanced": False,
                    "rejected_fields": sorted(set(rejected.get("arguments", {})))})
    return rows


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--attempt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.attempt.resolve()
    all_rows = bridge_cases(root)
    package = root / "mission-a/continuation-package"
    anchor = root / "mission-a/continuation-package-host-trust-anchor.json"
    with tempfile.TemporaryDirectory(prefix="atlas-cycle38-negative-", dir="/var/tmp") as name:
        continuation = continuation_cases(package, anchor, Path(name))
    all_rows.extend(continuation)
    failures = [row for row in all_rows if row["actual"] in {"ACCEPTED_UNEXPECTEDLY", "UNKNOWN"}
        or (row.get("state_unchanged") is False)]
    result = {"schema": "basic-workspace.cycle38-negative-controls", "version": 1,
        "attempt": root.name, "minimum_cases": 40, "case_count": len(all_rows),
        "passed": not failures and len(all_rows) >= 40, "failures": failures, "cases": all_rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"cases": len(all_rows), "passed": result["passed"],
        "continuation_cases": len(continuation), "bridge_cases": len(all_rows) - len(continuation)}, indent=2))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
