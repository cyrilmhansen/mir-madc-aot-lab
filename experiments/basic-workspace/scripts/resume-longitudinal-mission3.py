#!/usr/bin/env python3
"""Resume Cycle 14 Mission 3 from committed Mission 1/2 evidence.

This creates a fresh Workspace by replaying only the prior committed semantic
operations, verifies a freshly generated checkpoint against the old checkpoint,
then opens a new model conversation containing no prior transcript.
"""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_campaign_spec = importlib.util.spec_from_file_location(
    "cycle14_longitudinal_campaign", ROOT / "scripts" / "longitudinal-campaign.py")
campaign = importlib.util.module_from_spec(_campaign_spec)
assert _campaign_spec and _campaign_spec.loader
_campaign_spec.loader.exec_module(campaign)


def load_age_module():
    spec = importlib.util.spec_from_file_location("cycle14_age", ROOT / "scripts" / "age-by-id-campaign.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def successful_call(path: Path, tool_name: str) -> dict[str, Any]:
    session = json.loads(path.read_text(encoding="utf-8"))
    found = []
    for turn in session.get("transcript", []):
        for call in turn.get("tool_calls", []):
            if call.get("name") == tool_name and call.get("result", {}).get("ok") is True:
                found.append(call.get("arguments"))
    if not found:
        raise RuntimeError(f"No successful {tool_name} call recorded in {path}")
    # Repeated previews in the original transcript are model activity; the
    # constructive continuation needs the committed operation only once.
    if any(value != found[0] for value in found):
        raise RuntimeError(f"Conflicting successful {tool_name} arguments in {path}")
    return copy.deepcopy(found[0])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    source = args.source_run.resolve()
    output = args.output_dir.resolve()
    if output.exists() and any(output.iterdir()):
        raise RuntimeError(f"Refusing to overwrite evidence directory: {output}")
    output.mkdir(parents=True, exist_ok=True)
    (output / "mission-3-is-adult").mkdir()
    started = time.perf_counter()
    trace = campaign.age.Trace()
    trace.emit("resume_started", campaign_kind="real_llm_resume", actor="harness",
               source_run=str(source.relative_to(ROOT.parent.parent.parent.parent)) if source.is_relative_to(ROOT.parent.parent.parent.parent) else "prior-cycle14-run",
               previous_missions="committed model operations replayed into a fresh Workspace",
               prior_conversation_included=False)

    old_run_checkpoint = json.loads((source / "recovery-checkpoint.json").read_text(encoding="utf-8"))
    create_request = successful_call(source / "mission-1-is-senior" / "agent-session.json",
                                     "preview_create_function")
    age_request = successful_call(source / "mission-2-age-205" / "agent-session.json", "preview_age_edit")
    if create_request.get("name", "").casefold() != "is_senior" or age_request.get("new_age") != 55:
        raise RuntimeError("Source transcripts do not contain the expected committed Mission 1/2 operations")

    workspace = campaign.Workspace()
    doc, aliases, seed = campaign.age.create_seed(workspace, trace, "reconstructed-seed")
    rev = workspace.get_revision(doc)
    base1 = campaign.senior.normalized_state(
        campaign.projection_semantics(campaign.build_projection(workspace, doc, rev)), aliases)
    m1 = campaign.senior.make_mission()
    gateway1 = campaign.senior.SeniorMissionGateway(
        workspace, doc, aliases, base1, m1, trace, "replay-mission-1")
    gateway1.discover_functions()
    preview1 = gateway1.preview({"name": create_request["name"],
                                 "parameters": create_request["parameters"],
                                 "body": create_request["body"]}, rev,
                                create_request["callee_handle"])
    if not preview1.get("ok"):
        raise RuntimeError(f"Mission 1 committed operation failed replay preview: {preview1}")
    commit1 = gateway1.commit(preview1["transaction_id"])
    if not commit1.get("committed"):
        raise RuntimeError(f"Mission 1 committed operation failed replay commit: {commit1}")
    aliases1 = gateway1.aliases

    m2 = campaign.age.make_mission(55.0)
    m2["mission_id"] = "mission.age-by-logical-id.205.to-55.v1"
    rev2_base = workspace.get_revision(doc)
    base2 = campaign.age.normalize_projection(
        campaign.projection_semantics(campaign.build_projection(workspace, doc, rev2_base)), aliases1)
    age_gateway = campaign.age.MissionGateway(workspace, doc, aliases1, base2, m2, trace,
                                              "replay-mission-2")
    target = aliases1.get("people.age.205")
    if not target:
        raise RuntimeError("Committed Mission 2 target has no portable semantic handle")
    preview2 = age_gateway.preview(target, age_request["new_age"], rev2_base)
    if not preview2.get("ok"):
        raise RuntimeError(f"Mission 2 committed operation failed replay preview: {preview2}")
    commit2 = age_gateway.commit(preview2["transaction_id"])
    if not commit2.get("committed"):
        raise RuntimeError(f"Mission 2 committed operation failed replay commit: {commit2}")
    revision = workspace.get_revision(doc)

    # Key correction: the Mission 3 baseline is taken after Mission 2's committed edit.
    aliases2 = dict(aliases1)
    base3 = campaign.senior.normalized_state(
        campaign.projection_semantics(campaign.build_projection(workspace, doc, revision)), aliases2)
    observed = campaign.senior.execute_program(workspace, doc, revision, aliases2)
    expected = {engine: {"101": {"age": 25.0, "senior": 0.0},
                         "205": {"age": 55.0, "senior": 1.0},
                         "900": {"age": 53.0, "senior": 1.0},
                         "999": {"age": -1.0, "senior": 0.0},
                         "2": {"age": -1.0, "senior": 0.0}}
                for engine in ("interp", "jit")}
    if observed != expected:
        raise RuntimeError("Replayed Mission 1/2 behavior differs from its committed evidence")

    m3 = campaign.make_adult_mission()
    checkpoint = campaign.make_checkpoint(workspace, doc, aliases2,
        [{"mission_id": m1["mission_id"], "status": "committed_and_validated",
          "revision": revision - 1, "result": True},
         {"mission_id": m2["mission_id"], "status": "committed_and_validated",
          "revision": revision, "result": True}], observed, m3)
    # A fresh reconstruction has a new document ID, so compare the semantic
    # fingerprint and verified facts, then bind the checkpoint to that document.
    if checkpoint["semantic_fingerprint"] != old_run_checkpoint["semantic_fingerprint"]:
        raise RuntimeError("Reconstructed revision does not match the recorded recovery checkpoint")
    checkpoint_check = campaign.validate_checkpoint(checkpoint, workspace, doc,
                                                      campaign.PROFILE_ID, aliases2)
    if not checkpoint_check.get("ok"):
        raise RuntimeError(f"Fresh recovery checkpoint failed verification: {checkpoint_check}")
    checkpoint_for_agent = {k: v for k, v in checkpoint.items() if k != "document"}
    checkpoint_for_agent["document"] = {"revision": revision}
    (output / "recovery-checkpoint.json").write_text(
        json.dumps(checkpoint, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (output / "mission-3-is-adult" / "mission.json").write_text(
        json.dumps(m3, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (output / "execution-profile.json").write_text(
        json.dumps(campaign.age.make_profile(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    trace.emit("checkpoint_created", phase="recovery", actor="host_checkpoint",
               revision=revision, semantic_fingerprint=checkpoint["semantic_fingerprint"],
               checkpoint_bytes=(output / "recovery-checkpoint.json").stat().st_size,
               contains_transcript=False, verified=checkpoint_check,
               verified_against_previous_fingerprint=True)
    trace.emit("context_reset", phase="recovery", actor="harness",
               previous_model_context_included=False, included_checkpoint=True,
               included_tool_schemas="fresh current schema", workspace="fresh semantic replay")

    gateway3 = campaign.senior.SeniorMissionGateway(workspace, doc, aliases2, base3, m3,
        trace, "mission-3-resumed", function_name="IS_ADULT", function_handle="is_adult.function")
    adult_validator = lambda requested: campaign.adult_validator(workspace, doc, gateway3, requested)
    config = campaign.resolve_config()
    endpoint = campaign.make_chat_endpoint(config)
    campaign.senior.OUT = output / "mission-3-is-adult"
    session = campaign.senior.run_model_session(endpoint, workspace, doc, gateway3, trace,
        max_turns=8, max_calls=14, function_name="IS_ADULT", threshold=18.0,
        validator=adult_validator, recovery_checkpoint=checkpoint_for_agent)
    result_revision = workspace.get_revision(doc)
    validation = adult_validator(result_revision) if gateway3.committed else {
        "reliable": True, "mission_complete": False, "executed_revision": None,
        "diagnostics": ["No model commit"]}
    trace.emit("host_correctness_judgment", phase="mission-3", actor="host_validation",
               revision=result_revision, committed=gateway3.committed,
               validation=validation, passed=validation.get("mission_complete", False))

    summary = {"schema": "basic-workspace.longitudinal-resume-summary", "version": 1,
        "campaign_kind": "real_llm_resume", "model": config["model"],
        "source_campaign": "calibrated-run-01", "missions_1_2": "committed operations replayed from genuine transcripts",
        "missions_committed_before_resume": 2, "context_reset": "fresh conversation; no prior turns included",
        "checkpoint_verified": True, "checkpoint_fingerprint_matches_prior": True,
        "mission_3": {"model_session": session, "committed": gateway3.committed,
                       "validation": validation},
        "final_revision": result_revision, "elapsed_ms": round((time.perf_counter()-started)*1000, 3),
        "final_status": "passed" if gateway3.committed and validation.get("mission_complete") else "mission_3_failed"}
    if gateway3.committed:
        aliases3 = gateway3.aliases
        normalized = campaign.senior.normalized_state(
            campaign.projection_semantics(campaign.build_projection(workspace, doc, result_revision)), aliases3)
        stream = campaign.build_stream(seed["operation"], gateway1.committed_request,
                              gateway3.committed_request, sorted(aliases3))
        (output / "constructive-operations.json").write_text(
            json.dumps(stream, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        replay_trace = campaign.age.Trace()
        replay_ws, replay_doc, replay_aliases, replay_normalized = campaign.replay_stream(stream, replay_trace)
        replay_revision = replay_ws.get_revision(replay_doc)
        original_results = campaign.execute_all(workspace, doc, result_revision, aliases3)
        replay_results = campaign.execute_all(replay_ws, replay_doc, replay_revision, replay_aliases)
        replay_ok = (normalized == replay_normalized and original_results == replay_results and
                     all(v == campaign.value_expectations() for v in replay_results.values()))
        equivalence = {"structural_equivalence": normalized == replay_normalized,
            "binding_equivalence": campaign._call_edges(normalized) == campaign._call_edges(replay_normalized),
            "behavioral_equivalence": original_results == replay_results,
            "interpreter_jit_agreement": replay_results["interp"] == replay_results["jit"],
            "expected_behavior": all(v == campaign.value_expectations() for v in replay_results.values()),
            "original_revision": result_revision, "replay_revision": replay_revision,
            "identity_remappings": sum(aliases3[h] != replay_aliases.get(h) for h in aliases3),
            "passed": replay_ok}
        (output / "equivalence.json").write_text(
            json.dumps(equivalence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        summary["replay"] = equivalence
        summary["final_behavior"] = original_results
        summary["dependencies"] = campaign._call_edges(normalized)
    trace.write(output / "history.jsonl")
    (output / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    (output / "REPORT.md").write_text(
        "# Cycle 14B — Corrected Mission 3 resume\n\n"
        f"Status: **{summary['final_status']}**\n\n"
        "Missions 1 and 2 are not new model trials here. Their successful semantic operations "
        "were replayed into a fresh Workspace from the genuine `calibrated-run-01` tool transcripts. "
        "The checkpoint fingerprint matched the previous run. Mission 3 used a new model context "
        "with only the verified checkpoint, current tool schemas, and objective. The corrected gateway "
        "baseline was captured after the age-55 commit. The original failed Mission 3 transcript is preserved.\n\n"
        "See `mission-3-is-adult/agent-session.json`, `history.jsonl`, `recovery-checkpoint.json`, "
        "and, if committed, `constructive-operations.json` and `equivalence.json`.\n",
        encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if summary["final_status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
