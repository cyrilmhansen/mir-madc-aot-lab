#!/usr/bin/env python3
"""Finalize Cycle 20 artifacts from a completed Pi run without rerunning inference."""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
from collections import Counter

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent


def read_jsonl(path: pathlib.Path):
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def write_json(path: pathlib.Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def finalize(out: pathlib.Path):
    lifecycle_path = out / "pi-lifecycle.jsonl"
    pi_path = out / "pi-session.jsonl"
    history_path = out / "history.jsonl"
    for path in (lifecycle_path, pi_path, history_path):
        if not path.is_file():
            raise RuntimeError(f"missing completed-run evidence: {path.name}")
    lifecycle = read_jsonl(lifecycle_path)
    pi_events = read_jsonl(pi_path)
    history = read_jsonl(history_path)
    if not any(row.get("record_type") == "launcher_timeout" for row in lifecycle):
        raise RuntimeError("offline finalizer requires a completed bounded/timeout run")
    commits = [row for row in history if row.get("event") == "transaction_committed"]
    rejections = [row for row in history if row.get("event") == "transaction_rejected"]
    if commits:
        raise RuntimeError("this no-commit finalizer will not infer or rewrite a committed run")
    if not rejections or any(not row.get("authoritative_state_unchanged") for row in rejections):
        raise RuntimeError("rejection evidence does not prove an unchanged authoritative state")

    # Pi repeats each assistant message's running usage snapshot on streamed
    # deltas. Count completed assistant messages only to avoid multiplying it.
    completed_messages = [row.get("message", {}) for row in pi_events
        if row.get("type") == "message_end" and row.get("message", {}).get("role") == "assistant"]
    usage = [message.get("usage") for message in completed_messages
        if isinstance(message.get("usage"), dict)]
    usage_fields = ("input", "output", "cacheRead", "cacheWrite", "totalTokens")
    reported_usage = None
    if usage:
        reported_usage = {key: sum(row.get(key, 0) or 0 for row in usage) for key in usage_fields}
    starts = [row for row in pi_events if row.get("type") == "tool_execution_start"]
    ends = [row for row in pi_events if row.get("type") == "tool_execution_end"]
    model_turns = sum(row.get("event_type") == "turn_start" for row in lifecycle)
    tool_counts = Counter(row.get("toolName") for row in starts)
    lifecycle_end = next((row for row in reversed(lifecycle) if row.get("record_type") == "pi_process_exit"), {})
    timeout = next(row for row in reversed(lifecycle) if row.get("record_type") == "launcher_timeout")
    pi_state = json.loads((out / "baseline-reconstruction.json").read_text(encoding="utf-8"))
    if not pi_state.get("passed"):
        raise RuntimeError("preserved baseline reconstruction record is not valid")

    session = {"model": "Qwen3.8-Flash-Next-Sushi-STQ-2.75bpw", "event_count": len(pi_events),
        "model_turns": model_turns, "tool_call_starts": len(starts), "tool_call_ends": len(ends),
        "tool_calls_by_name": dict(tool_counts), "provider_usage": reported_usage,
        "provider_usage_status": f"aggregated from {len(usage)} completed assistant message_end records; the seventh request was still pending at timeout",
        "schema_rejected_tool_calls": sum(bool(row.get("isError")) for row in ends),
        "session_bytes": pi_path.stat().st_size, "lifecycle_event_count": len(lifecycle),
        "launcher_timeout_seconds": timeout.get("timeout_seconds"),
        "elapsed_ms": lifecycle_end.get("elapsed_ms"), "exit_code": lifecycle_end.get("exit_code"),
        "timed_out": lifecycle_end.get("timed_out"), "agent_end_seen": lifecycle_end.get("agent_end_seen"),
        "agent_settled_seen": lifecycle_end.get("agent_settled_seen"),
        "pending_tool_count": lifecycle_end.get("pending_tool_count"),
        "last_observer_record": lifecycle[-1].get("record_type") if lifecycle else None}
    write_json(out / "session-metrics.json", session)

    completion = {"completion_states": {
        "semantic_program_correctness": "mission_not_achieved; the unchanged revision-3 baseline retains its previously validated behavior",
        "mission_authorization": "no proposal authorized; four proposals rejected by the gateway and one was rejected by Pi schema validation",
        "authoritative_commit": False,
        "host_validation": "candidate validation not run because there was no accepted preview or commit",
        "pi_agent_settlement": "not_settled; no agent_end/agent_settled event before timeout",
        "launcher_process_outcome": "timed_out_then_SIGTERM; exit 143"},
        "workspace_revision": 3, "revision_unchanged": True,
        "rejected_proposals": len(rejections), "committed_transactions": 0,
        "evidence_source": "preserved Pi event stream and MissionGateway history; no model actions synthesized"}
    write_json(out / "completion-states.json", completion)

    # Add one host-observed lifecycle marker to the presentation stream. This is
    # derived only from the recorded timeout/process-exit events, not from an
    # inferred model action. The original Pi/session and gateway journals stay
    # byte-for-byte intact.
    visual_path = out / "visual-events.jsonl"
    visual_events = read_jsonl(visual_path)
    tool_events = read_jsonl(out / "pi-tool-lifecycle.jsonl")
    tool_starts = {row.get("toolCallId"): row for row in tool_events
        if row.get("type") == "tool_execution_start" and row.get("toolName") == "workspace_preview_semantic_edit"}
    gateway_rejection_args = []
    preview_attempts = []
    for row in tool_events:
        if row.get("type") != "tool_execution_end" or row.get("toolName") != "workspace_preview_semantic_edit":
            continue
        details = row.get("result", {}).get("details", {})
        start = tool_starts.get(row.get("toolCallId"), {})
        args = start.get("args", {})
        preview_attempts.append({"tool_call_id": row.get("toolCallId"),
            "boundary": "pi_schema" if row.get("isError") else "mission_gateway",
            "accepted": False, "error_code": details.get("code") if not row.get("isError") else "PI_TOOL_SCHEMA_VALIDATION",
            "error_text": (row.get("result", {}).get("content", [{}])[0].get("text", "")
                if row.get("isError") else details.get("message")),
            "submitted_edits": args.get("edits", [])})
        if not row.get("isError") and details.get("code") == "INVALID_EDIT_REQUEST":
            gateway_rejection_args.append({"tool_call_id": row.get("toolCallId"),
                "function_handle": args.get("function_handle"), "edits": args.get("edits", [])})
    write_json(out / "attempt-analysis.json", {"schema": "basic-workspace.cycle20-attempt-analysis",
        "version": 1, "base_revision": 3, "authoritative_revision_after_session": 3,
        "committed_semantic_changes": [], "attempts": preview_attempts,
        "intended_literal_changes_observed_in_model_arguments": [
            {"function": "CLAMP_SCORE", "target": "IF comparison RHS at body[1].then[0].expression[1]", "from": 100, "to": 50},
            {"function": "CLAMP_SCORE", "target": "result assignment clamp_score.statement.2 RHS", "from": 100, "to": 50}],
        "candidate_was_gateway_previewed": False,
        "interpretation": "The model repeatedly proposed the two intended changes, but transport-envelope rejection prevented a candidate projection from being authorized or executed."})
    rejection_frames = [row for row in visual_events if row.get("event_type") == "rejection"]
    if len(rejection_frames) != len(gateway_rejection_args):
        raise RuntimeError("gateway rejection events do not correlate one-to-one with recorded Pi calls")
    for frame, proposal in zip(rejection_frames, gateway_rejection_args):
        frame["provenance"] = "Genuine Pi proposal · MissionGateway rejection"
        frame["focus"] = {"handles": [proposal["function_handle"], "clamp_score.statement.2"],
            "mapping": "verified_function_boundary"}
        frame["description"] = (f"The model submitted {len(proposal['edits'])} literal edit(s) as tool call "
            f"{proposal['tool_call_id']}. The gateway rejected the request envelope as INVALID_EDIT_REQUEST; "
            "it did not preview or apply the candidate. Committed BASIC remains revision 3.")
        frame["preview"] = {"status": "rejected", "function": "CLAMP_SCORE",
            "message": "Gateway rejected the request envelope before preview. No source change was committed.",
            "tool_call_id": proposal["tool_call_id"], "submitted_edits": proposal["edits"]}
    status_id = "cycle20-agent-timeout-observed"
    if not any(row.get("event_id") == status_id for row in visual_events):
        last_sequence = max((row.get("presentation_sequence", 0) for row in visual_events), default=0)
        visual_events.append({"event_id": status_id, "frame_id": status_id,
            "presentation_sequence": last_sequence + 1, "event_type": "mission_status", "revision": 3,
            "session_id": "cycle20-real-agent-01", "mission_id": "cycle20.clamp-score-cap50.v1",
            "provenance": "Host lifecycle observation · genuine Pi session",
            "title": "Pi session timed out", "description": "The bounded 240-second Pi session ended with no accepted preview, commit, or pending tool call. The last three edit proposals were rejected before mutation.",
            "mission_status": "Mission not committed · baseline remains at revision 3 · agent session timed out",
            "lifecycle": {"timed_out": True, "exit_code": lifecycle_end.get("exit_code"),
                "agent_end_seen": lifecycle_end.get("agent_end_seen"),
                "agent_settled_seen": lifecycle_end.get("agent_settled_seen"),
                "pending_tool_count": lifecycle_end.get("pending_tool_count")}})
    with visual_path.open("w", encoding="utf-8") as stream:
        for row in visual_events:
            stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")

    schema_path = out / "tool-schemas.json"
    visual_path = out / "visual-frames-generic.json"
    timing_path = out / "gateway-tool-timings.jsonl"
    timing_rows = read_jsonl(timing_path) if timing_path.is_file() else []
    renderer = subprocess.run([sys.executable, str(ROOT / "scripts/basic-visual.py"), "replay", str(out)],
        capture_output=True, text=True)
    if renderer.returncode:
        (out / "visual-replay-error.txt").write_text(renderer.stderr, encoding="utf-8")
        raise RuntimeError(f"offline visualizer failed: {renderer.stderr[-1000:]}")
    frames = json.loads(visual_path.read_text(encoding="utf-8"))
    summary = {"schema": "basic-workspace.cycle20-summary", "version": 1,
        "campaign_kind": "genuine_pi_semantic_maintenance", "model": session["model"], "pi_version": "1.5.0",
        "baseline_reconstruction_passed": True, "workspace_revision": 3, "committed": False,
        "preview_accepted": False, "host_candidate_validation": "not run", "completion_states": completion["completion_states"],
        "session": session, "active_tools": json.loads((out / "tool-inventory.json").read_text())["tools"],
        "tool_schema_bytes": schema_path.stat().st_size, "rejected_preview_count": len(rejections),
        "pi_schema_rejected_tool_calls": session["schema_rejected_tool_calls"],
        "rejection_codes": [row.get("code") for row in rejections], "commits": 0,
        "gateway_tool_processing_ms": round(sum(row.get("elapsed_ms", 0) or 0 for row in timing_rows
            if row.get("method") in {"discover_functions", "inspect_program", "preview_semantic_edit", "commit_preview", "validate_mission"}), 3),
        "constructive_stream_bytes": 0, "visual_frame_count": len(frames["campaigns"][0]["frames"]),
        "visual_html": str(out / "visual-replay-generic.html"),
        "transcript_bytes": pi_path.stat().st_size, "history_bytes": history_path.stat().st_size,
        "automatic_retries": 0, "source_recording_unchanged": True}
    write_json(out / "summary.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign_directory", type=pathlib.Path)
    args = parser.parse_args()
    result = finalize(args.campaign_directory.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
