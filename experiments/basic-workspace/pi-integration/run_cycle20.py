#!/usr/bin/env python3
"""Run one bounded Pi/Sushi semantic maintenance mission for Cycle 20."""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import select
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from pi_lifecycle import run_pi_observed
from run_cycle16 import MODEL, gateway_call, isolated_config, rpc_preflight

TOOLS = ["workspace_discover_functions", "workspace_inspect_program",
    "workspace_preview_semantic_edit", "workspace_commit_preview", "workspace_validate_mission"]


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def summarize_cycle20_session(output, lifecycle):
    """Cycle 20 uses pi-session.jsonl (unlike Cycle 19's mission-prefixed name)."""
    path = output / "pi-session.jsonl"
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    messages = [row.get("message", {}) for row in rows
        if row.get("type") == "message_end" and row.get("message", {}).get("role") == "assistant"]
    usage = [message["usage"] for message in messages if isinstance(message.get("usage"), dict)]
    totals = {key: (sum(item.get(key, 0) or 0 for item in usage) if usage else None)
        for key in ("input", "output", "cacheRead", "cacheWrite", "totalTokens")}
    starts = [row for row in rows if row.get("type") == "tool_execution_start"]
    ends = [row for row in rows if row.get("type") == "tool_execution_end"]
    return {"model": MODEL, "event_count": len(rows),
        "completed_assistant_messages": len(messages),
        "turn_end_events": sum(row.get("type") == "turn_end" for row in rows),
        "tool_call_starts": len(starts), "tool_call_ends": len(ends),
        "tool_calls_by_name": {name: sum(row.get("toolName") == name for row in starts) for name in TOOLS},
        "usage_reported_by_pi": totals, "usage_counting": "one completed assistant message_end record per response; pending response excluded",
        "event_stream_bytes": path.stat().st_size, "timed_out": lifecycle["timed_out"],
        "exit_code": lifecycle["exit_code"], "elapsed_ms": lifecycle["elapsed_ms"],
        "observer": lifecycle["observer"], "pending_tool_ids": lifecycle.get("pending_tool_ids", [])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=pathlib.Path,
        default=HERE / "results/cycle20-semantic-evolution/real-agent-01")
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--open-browser", action="store_true")
    parser.add_argument("--preflight-only", action="store_true",
        help="verify exact active tool inventory/schema and baseline reconstruction without inference")
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"output directory already contains evidence: {out}")
    out.mkdir(parents=True, exist_ok=True)
    runtime = HERE / ".runtime" / "cycle20"
    config_dir = pathlib.Path(os.environ.get("PI_CODING_AGENT_DIR", pathlib.Path.home() / ".sushi/pi")).expanduser()
    _models_file, key_env = isolated_config(runtime, config_dir)
    env = os.environ.copy()
    env.update(key_env)
    env["PI_CODING_AGENT_DIR"] = str(runtime)
    env["PI_CODING_AGENT_SESSION_DIR"] = str(out / "pi-sessions")
    env["BASIC_WS_AUTHORING_MODE"] = "semantic_edit"

    with socket.socket() as reserve:
        reserve.bind(("127.0.0.1", 0))
        gateway_port = reserve.getsockname()[1]
    gateway_err = (out / "gateway-stderr.log").open("w", encoding="utf-8")
    gateway_proc = subprocess.Popen([sys.executable, str(HERE / "cycle20_gateway.py"),
        "--output", str(out), "--port", str(gateway_port)], stdout=subprocess.PIPE,
        stderr=gateway_err, text=True, env=env)
    viewer = None
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and gateway_proc.poll() is None:
            if select.select([gateway_proc.stdout], [], [], .1)[0]:
                break
        else:
            raise RuntimeError("baseline reconstruction gateway did not start")
        ready = json.loads(gateway_proc.stdout.readline())
        if not ready.get("ready") or ready.get("revision") != 3 or not ready.get("baseline_verified"):
            raise RuntimeError("Cycle 19B exact reconstruction/checkpoint verification failed; inference was not started")
        host, port = "127.0.0.1", ready["port"]
        env["BASIC_WS_PI_GATEWAY"] = f"{host}:{port}"

        viewer = subprocess.Popen([sys.executable, str(ROOT / "scripts/basic-visual.py"),
            "live", str(out), "--port", "0"], stdout=subprocess.PIPE,
            stderr=(out / "viewer-stderr.log").open("w", encoding="utf-8"), text=True)
        banner = viewer.stdout.readline().strip()
        viewer_url = banner.split(": ", 1)[-1]
        if not viewer_url.startswith("http://127.0.0.1:"):
            raise RuntimeError("read-only live viewer failed to start")
        (out / "viewer-url.txt").write_text(viewer_url + "\n", encoding="utf-8")
        with urllib.request.urlopen(viewer_url, timeout=5) as response:
            if response.status != 200:
                raise RuntimeError("live viewer health check failed")

        base = ["pi", "--provider", "sushi", "--model", MODEL, "--thinking", "low",
            "--extension", str(HERE / "extension.ts"), "--no-extensions", "--no-mcp",
            "--no-skills", "--no-context-files", "--no-prompt-templates", "--no-builtin-tools",
            "--no-tools", "--tools", ",".join(TOOLS)]
        rpc_preflight(env, base, out, TOOLS)
        schema_rows = json.loads((out / "tool-schemas.json").read_text(encoding="utf-8"))
        preview_schema = next((row for row in schema_rows if row.get("name") == "workspace_preview_semantic_edit"), None)
        properties = (preview_schema or {}).get("parameters", {}).get("properties", {})
        edits_schema = properties.get("edits", {})
        target_schema = edits_schema.get("items", {})
        if not properties or edits_schema.get("minItems") != 2 or edits_schema.get("maxItems") != 2 or not target_schema:
            raise RuntimeError("active Pi schema does not expose the required bounded two-edit request")
        schema_text = json.dumps(schema_rows, separators=(",", ":"), ensure_ascii=False)
        if '"items":{}' in schema_text:
            raise RuntimeError("active semantic edit schema contains an unconstrained item shape")
        write_json(out / "preflight-verification.json", {
            "model": MODEL, "pi_version": "1.5.0", "active_tools": TOOLS,
            "tool_schema_bytes": (out / "tool-schemas.json").stat().st_size,
            "bounded_atomic_edit_items": {"minimum": 2, "maximum": 2},
            "target_schema": target_schema,
            "baseline_reconstruction": "passed", "inference_started": False})
        if args.preflight_only:
            write_json(out / "preflight-complete.json", {"passed": True, "inference_started": False,
                "model": MODEL, "active_tools": TOOLS,
                "tool_schema_bytes": (out / "tool-schemas.json").stat().st_size})
            print(json.dumps({"preflight_passed": True, "inference_started": False,
                "output": str(out), "tool_schema_bytes": (out / "tool-schemas.json").stat().st_size}, indent=2))
            return 0
        if args.open_browser:
            webbrowser.open(viewer_url)

        prompt = ("Mission: Modify the existing CLAMP_SCORE function so its upper bound is 50, "
            "making its behavior min(50,max(0,X)). Preserve IS_PASSING unchanged, including its "
            "threshold and bound call. There are two related uses of the current upper bound; "
            "identify both through semantic discovery and include both in one preview. Do not "
            "edit BASIC source text. Start by discovering functions and inspecting the typed "
            "program and editable semantic locations. Use the discovered function and statement "
            "handles, submit one complete candidate, commit only an accepted preview, then request "
            "MIR interpreter/JIT validation at the current revision. The gateway rechecks the "
            "complete candidate and revision immediately before commit.")
        (out / "mission-prompt.txt").write_text(prompt + "\n", encoding="utf-8")
        command = base + ["--mode", "json", "--session-dir", str(out / "pi-sessions" / "mission-1"),
            "--name", "Cycle 20 CLAMP_SCORE semantic evolution", "--print", "--", prompt]
        pi_stderr = (out / "pi-stderr.log").open("w", encoding="utf-8")

        def publish(state, info):
            try:
                gateway_call(host, port, "record_agent_status", {"state": state, "info": info}, timeout=5)
            except Exception:
                pass

        lifecycle = run_pi_observed(command, env=env, timeout_seconds=args.timeout,
            raw_event_path=out / "pi-session.jsonl", lifecycle_path=out / "pi-lifecycle.jsonl",
            stderr_file=pi_stderr, on_status=publish, no_progress_seconds=15,
            shutdown_grace_seconds=3)
        pi_stderr.close()
        session = summarize_cycle20_session(out, lifecycle)
        write_json(out / "session-metrics.json", session)
        status = gateway_call(host, port, "get_status", {})
        validation = gateway_call(host, port, "host_validate", {"expected_revision": status["revision"]}) if status["committed"] else None
        if validation is None:
            write_json(out / "validation.json", {"mission_complete": False, "not_run": True,
                "revision": status["revision"], "expectation_source": "independent host-owned oracle"})
        completion = gateway_call(host, port, "finalize_session", {
            "timed_out": bool(lifecycle.get("timed_out")), "pi_exit_code": lifecycle.get("exit_code"),
            "validation": validation, "pi_lifecycle": lifecycle.get("observer", {})})
        write_json(out / "completion-states.json", completion)
        replay = subprocess.run([sys.executable, str(ROOT / "scripts/basic-visual.py"), "replay", str(out)],
            capture_output=True, text=True)
        if replay.returncode:
            (out / "visual-replay-error.txt").write_text(replay.stderr, encoding="utf-8")
        frames = json.loads((out / "visual-frames-generic.json").read_text()) if (out / "visual-frames-generic.json").exists() else None
        timing_rows = [json.loads(line) for line in (out / "gateway-tool-timings.jsonl").read_text().splitlines() if line.strip()]
        summary = {"schema": "basic-workspace.cycle20-summary", "version": 1,
            "campaign_kind": "genuine_pi_semantic_maintenance", "model": MODEL, "pi_version": "1.5.0",
            "baseline_reconstruction_passed": True, "workspace_revision": status["revision"],
            "committed": status["committed"], "host_validation": validation,
            "completion_states": completion.get("completion_states"), "session": session,
            "active_tool_count": len(TOOLS), "active_tools": TOOLS,
            "tool_schema_bytes": (out / "tool-schemas.json").stat().st_size,
            "gateway_tool_processing_ms": round(sum(x.get("elapsed_ms", 0) for x in timing_rows if x.get("agent_tool")), 3),
            "constructive_stream_bytes": (out / "constructive-operations.json").stat().st_size if (out / "constructive-operations.json").exists() else 0,
            "visual_frames": len(frames["campaigns"][0]["frames"]) if frames else None,
            "visual_html": str(out / "visual-replay.html") if replay.returncode == 0 else None,
            "viewer_url": viewer_url, "automatic_retries": 0, "timeout_seconds": args.timeout}
        write_json(out / "summary.json", summary)
        print(json.dumps({"summary": str(out / "summary.json"), "revision": status["revision"],
            "committed": status["committed"], "mission_complete": bool(validation and validation.get("mission_complete")),
            "completion_states": completion.get("completion_states"), "visual_html": summary["visual_html"]}, indent=2))
        return 0 if validation and validation.get("mission_complete") else 1
    finally:
        for process in (gateway_proc, viewer):
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        gateway_err.close()


if __name__ == "__main__":
    raise SystemExit(main())
