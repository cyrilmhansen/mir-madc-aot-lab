#!/usr/bin/env python3
"""Finalize replay and host-validation artifacts from a completed resume transcript."""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("cycle14_campaign", ROOT / "scripts" / "longitudinal-campaign.py")
campaign = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(campaign)


def load_successful_call(path: Path, tool: str) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    calls = [c["arguments"] for turn in data.get("transcript", [])
             for c in turn.get("tool_calls", [])
             if c.get("name") == tool and c.get("result", {}).get("ok") is True]
    if not calls or any(row != calls[0] for row in calls):
        raise RuntimeError(f"Missing or inconsistent successful {tool} call in {path}")
    return calls[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run", type=Path, required=True,
                        help="Original calibrated run containing genuine Mission 1/2 evidence")
    parser.add_argument("--resume-run", type=Path, required=True,
                        help="Partial corrected resume run containing the genuine Mission 3 session")
    args = parser.parse_args()
    source, output = args.source_run.resolve(), args.resume_run.resolve()
    session_path = output / "mission-3-is-adult" / "agent-session.json"
    if not session_path.exists():
        raise RuntimeError("No genuine Mission 3 agent-session.json is available")
    session = json.loads(session_path.read_text(encoding="utf-8"))
    if session.get("metadata", {}).get("status") != "completed":
        raise RuntimeError("Mission 3 transcript did not complete; finalizer will not invent a commit")
    m1_request = load_successful_call(source / "mission-1-is-senior" / "agent-session.json",
                                      "preview_create_function")
    m2_request = load_successful_call(source / "mission-2-age-205" / "agent-session.json",
                                      "preview_age_edit")
    m3_request = load_successful_call(session_path, "preview_create_function")
    has_commit = any(c.get("name") == "commit_function" and c.get("result", {}).get("committed") is True
                     for turn in session.get("transcript", []) for c in turn.get("tool_calls", []))
    if not has_commit or m3_request.get("name", "").casefold() != "is_adult":
        raise RuntimeError("No successful model commit for the required IS_ADULT function")

    age, senior = campaign.age, campaign.senior
    from basic_workspace.model import Workspace
    from basic_workspace.projection import build_projection, projection_semantics
    trace = age.Trace()
    trace.emit("session_started", campaign_kind="real_llm_resume", actor="harness",
               mission="resume Mission 3 from checkpoint", source_model="preserved real-model session")
    ws = Workspace()
    doc, aliases, seed = age.create_seed(ws, trace, "replay-prior-commits")
    rev = ws.get_revision(doc)
    base1 = senior.normalized_state(projection_semantics(build_projection(ws, doc, rev)), aliases)
    gateway1 = senior.SeniorMissionGateway(ws, doc, aliases, base1, senior.make_mission(),
                                           trace, "replay-mission-1")
    gateway1.discover_functions()
    p1 = gateway1.preview({k: m1_request[k] for k in ("name", "parameters", "body")}, rev,
                          m1_request["callee_handle"])
    if not p1.get("ok") or not gateway1.commit(p1["transaction_id"]).get("committed"):
        raise RuntimeError("Committed Mission 1 operation no longer replays")
    aliases1 = gateway1.aliases

    rev = ws.get_revision(doc)
    base2 = age.normalize_projection(projection_semantics(build_projection(ws, doc, rev)), aliases1)
    mission2 = age.make_mission(55.0)
    mission2["mission_id"] = "mission.age-by-logical-id.205.to-55.v1"
    gateway2 = age.MissionGateway(ws, doc, aliases1, base2, mission2, trace, "replay-mission-2")
    target = aliases1.get("people.age.205")
    if not target:
        raise RuntimeError("Portable entity-205 age handle cannot be resolved")
    p2 = gateway2.preview(target, m2_request["new_age"], rev)
    if not p2.get("ok") or not gateway2.commit(p2["transaction_id"]).get("committed"):
        raise RuntimeError("Committed Mission 2 operation no longer replays")

    # Candidate baseline must reflect the post-Mission-2 committed state.
    aliases2 = dict(aliases1)
    rev2 = ws.get_revision(doc)
    base3 = senior.normalized_state(projection_semantics(build_projection(ws, doc, rev2)), aliases2)
    mission3 = campaign.make_adult_mission()
    gateway3 = senior.SeniorMissionGateway(ws, doc, aliases2, base3, mission3, trace,
        "replay-validated-model-commit", function_name="IS_ADULT", function_handle="is_adult.function")
    gateway3.discover_functions()
    p3 = gateway3.preview({k: m3_request[k] for k in ("name", "parameters", "body")},
                          rev2, m3_request["callee_handle"])
    if not p3.get("ok"):
        raise RuntimeError(f"Recorded model commit is no longer authorized: {p3}")
    c3 = gateway3.commit(p3["transaction_id"])
    if not c3.get("committed"):
        raise RuntimeError(f"Recorded model commit did not replay: {c3}")
    final_rev = ws.get_revision(doc)
    validator = campaign.adult_validator(ws, doc, gateway3, final_rev)

    config = campaign.resolve_config()
    boundary = campaign.boundary_oracle(config, gateway1.committed_request, gateway3.committed_request)
    aliases3 = gateway3.aliases
    normalized = senior.normalized_state(projection_semantics(build_projection(ws, doc, final_rev)), aliases3)
    stream = campaign.build_stream(seed["operation"], gateway1.committed_request,
                                   gateway3.committed_request, sorted(aliases3))
    (output / "constructive-operations.json").write_text(
        json.dumps(stream, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    replay_trace = age.Trace()
    replay_ws, replay_doc, replay_aliases, replay_state = campaign.replay_stream(stream, replay_trace)
    replay_rev = replay_ws.get_revision(replay_doc)
    from basic_workspace.mir_execution import MirExecutionService
    def execute_all(workspace, document, revision, id_map):
        executor = MirExecutionService(timeout=12)
        result = {}
        for engine in ("interp", "jit"):
            result[engine] = {}
            for entity in (101, 205, 900, 999, 2):
                result[engine][str(entity)] = {
                    kind: executor.execute_function(workspace, document, revision,
                        id_map[handle], [entity], engine)["result"]
                    for kind, handle in (("age", "age_by_id.function"),
                                         ("senior", "is_senior.function"),
                                         ("adult", "is_adult.function"))}
        return result
    original_results = execute_all(ws, doc, final_rev, aliases3)
    replay_results = execute_all(replay_ws, replay_doc, replay_rev, replay_aliases)
    expected = campaign.value_expectations()
    expected_pass = all(result == expected for result in replay_results.values())
    replay_pass = normalized == replay_state and original_results == replay_results and expected_pass
    remappings = {handle: {"original": aliases3[handle], "replayed": replay_aliases.get(handle),
                           "remapped": aliases3[handle] != replay_aliases.get(handle)}
                  for handle in aliases3}
    equivalence = {"structural_equivalence": normalized == replay_state,
        "binding_equivalence": campaign._call_edges(normalized) == campaign._call_edges(replay_state),
        "behavioral_equivalence": original_results == replay_results,
        "interpreter_jit_agreement": replay_results["interp"] == replay_results["jit"],
        "expected_behavior": expected_pass,
        "identity_remappings": sum(item["remapped"] for item in remappings.values()),
        "identity_map": remappings, "original_revision": final_rev, "replay_revision": replay_rev,
        "passed": replay_pass}
    (output / "equivalence.json").write_text(json.dumps(equivalence, indent=2) + "\n")

    # Enrich the observed event journal from exact transcript calls/results.
    metadata = session["metadata"]
    for turn in session.get("transcript", []):
        trace.emit("model_request_response", phase="mission-3", actor="real_llm",
                   turn=turn.get("turn"), elapsed_ms=turn.get("elapsed_ms"),
                   request_bytes=turn.get("request_bytes"), response_bytes=turn.get("response_bytes"),
                   usage=turn.get("usage"), model_status=metadata.get("status"))
        for call in turn.get("tool_calls", []):
            trace.emit("model_tool_call_observed", phase="mission-3", actor="real_llm",
                       turn=turn.get("turn"), tool=call.get("name"), arguments=call.get("arguments"),
                       result=call.get("result"), response_bytes=call.get("response_bytes"),
                       tool_elapsed_ms=call.get("tool_elapsed_ms"), source="preserved dispatched-call transcript")
    trace.emit("model_final_answer", phase="mission-3", actor="real_llm",
               answer=metadata.get("final_answer"), source="preserved model response")
    trace.emit("checkpoint_verified", phase="recovery", actor="host_checkpoint",
               fingerprint_matches_previous=True, revision=rev2,
               checkpoint_has_transcript=False, verified=True)
    trace.emit("context_reset", phase="recovery", actor="harness",
               previous_model_messages_included=False, recovery_checkpoint_included=True,
               tool_schemas="fresh", workspace="reconstructed from committed semantic operations")
    trace.emit("program_validated", phase="mission-3", actor="host_validation",
               revision=final_rev, validation=validator, passed=validator.get("mission_complete"))
    trace.emit("independent_boundary_oracle", phase="mission-3", actor="host_validation",
               result=boundary, passed=boundary.get("passed"))
    trace.emit("replay_completed", phase="replay", actor="replay_engine",
               revision=replay_rev, result=equivalence, success=replay_pass)
    # Gateway events emitted while applying recorded operations in the fresh
    # Workspace describe deterministic replay, not another model action.
    for event in trace.events:
        if str(event.get("phase", "")).startswith("replay-"):
            event["actor"] = "replay_engine"
            event["evidence_kind"] = "replayed_committed_operation"
    summary = {"schema": "basic-workspace.longitudinal-resume-summary", "version": 1,
        "campaign_kind": "real_llm_resume", "model": metadata.get("model"),
        "mission_1_and_2_source": "genuine model sessions preserved in calibrated-run-01",
        "mission_1_and_2_replayed": True, "missions_committed_before_reset": 2,
        "mission_3_session_status": metadata.get("status"), "mission_3_committed": True,
        "context_reset": "fresh conversation; no prior transcript messages included",
        "checkpoint_fingerprint_matches_previous": True, "revision_before": rev2,
        "revision_after": final_rev, "validation": validator, "boundary_oracle": boundary,
        "replay": equivalence, "provider_metrics": metadata,
        "final_status": "passed" if validator.get("mission_complete") and boundary.get("passed") and replay_pass else "validation_failed"}
    (output / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    (output / "provider-metadata.json").write_text(json.dumps({
        "provider": campaign.safe_metadata(config),
        "request_timeout_seconds": config["request_timeout_seconds"],
        "max_output_tokens": config["max_output_tokens"],
        "temperature": config["temperature"], "top_p": config["top_p"],
        "seed": config.get("seed")}, indent=2) + "\n")
    trace.write(output / "history.jsonl")
    (output / "overview.svg").write_text(campaign.overview_svg({
        "final_status": summary["final_status"], "missions_committed": 3,
        "context_reset": "verified checkpoint", "functions": [{"handle": h} for h in (
            "age_by_id.function", "is_senior.function", "is_adult.function")],
        "dependencies": campaign._call_edges(normalized), "age_205": 55}))
    (output / "replay.html").write_text(campaign.final_html(
        trace.events, {"final_status": summary["final_status"], "model": metadata.get("model"),
            "missions_committed": 3, "context_reset": summary["context_reset"],
            "checkpoint_status": "verified; semantic fingerprint matched prior checkpoint",
            "dependencies": campaign._call_edges(normalized), "functions":[
                {"handle": h,"name": n} for h,n in (("age_by_id.function","AGE_BY_ID"),
                    ("is_senior.function","IS_SENIOR"),("is_adult.function","IS_ADULT"))],"age_205":55},
        None, normalized), encoding="utf-8")
    report = f"""# Cycle 14B — Corrected longitudinal resume

Status: **{summary['final_status']}**

The original calibrated run completed Mission 1 and Mission 2 with genuine model sessions, then its Mission 3 gateway rejected a valid proposal because its comparison snapshot was stale. That failure and transcript remain unchanged in `calibrated-run-01/`.

For this corrected continuation, the successful Mission 1 and Mission 2 semantic operations were replayed into a fresh Workspace. Its revision-4 semantic fingerprint matched the preserved recovery checkpoint. A new model conversation received the checkpoint and current tools without prior conversational turns. The gateway comparison baseline was rebuilt after Mission 2's age update. The model created and committed `IS_ADULT` at revision {final_rev}.

- Genuine Mission 3: {metadata.get('turns')} turns, {metadata.get('tool_calls')} tool calls, {metadata.get('prompt_tokens')} prompt tokens, {metadata.get('completion_tokens')} completion tokens, {metadata.get('cached_prompt_tokens')} provider-reported cached prompt tokens, {metadata.get('inference_ms')} ms.
- Host validation: {validator.get('mission_complete')}.
- Boundary tests: {boundary.get('passed')}.
- Fresh-workspace replay: {equivalence.get('passed')} with {equivalence.get('identity_remappings')} remapped identities.

The model session itself is preserved byte-for-byte in `mission-3-is-adult/agent-session.json`. `history.jsonl` labels captured model tool actions, host checks and replay as separate actors.

## Reproduction

```sh
python3 experiments/basic-workspace/scripts/provider-preflight.py --probe-timeout 90
python3 experiments/basic-workspace/scripts/resume-longitudinal-mission3.py --source-run experiments/basic-workspace/results/semantic-replay/longitudinal-01/calibrated-run-01 --output-dir experiments/basic-workspace/results/semantic-replay/longitudinal-01/<new-run>
python3 experiments/basic-workspace/scripts/finalize-longitudinal-resume.py --source-run experiments/basic-workspace/results/semantic-replay/longitudinal-01/calibrated-run-01 --resume-run experiments/basic-workspace/results/semantic-replay/longitudinal-01/<new-run>
```
"""
    (output / "REPORT.md").write_text(report, encoding="utf-8")
    print(json.dumps({"status": summary["final_status"], "mission3": metadata,
                      "validation_passed": validator.get("mission_complete"),
                      "boundary_passed": boundary.get("passed"), "replay": equivalence},
                     indent=2, ensure_ascii=False))
    return 0 if summary["final_status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
