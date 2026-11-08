#!/usr/bin/env python3
"""Run Cycle 19's two bounded genuine Pi sessions from an empty Workspace."""
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
from run_cycle16 import (ATOMIC_TOOLS, MODEL, atomic_json, gateway_call,
                         isolated_config, rpc_preflight)


def write_json(path: pathlib.Path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def wait_http(url: str, timeout: float = 10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(.1)
    raise RuntimeError(f"loopback viewer did not become ready: {url}")


def run_session(*, phase, prompt, output, base, env, host, port, timeout):
    session_dir = output / "pi-sessions" / f"mission-{phase}"
    session_dir.mkdir(parents=True, exist_ok=True)
    command = base + ["--mode", "json", "--session-dir", str(session_dir), "--name",
                      f"Cycle 19 empty Workspace mission {phase}", "--print", "--", prompt]
    stderr = (output / f"mission-{phase}-pi-stderr.log").open("w", encoding="utf-8")

    def publish(state, info):
        try:
            gateway_call(host, port, "record_agent_status", {"state": state, "info": info}, timeout=5)
        except Exception:
            pass

    result = run_pi_observed(command, env=env, timeout_seconds=timeout,
        raw_event_path=output / f"mission-{phase}-pi-session.jsonl",
        lifecycle_path=output / f"mission-{phase}-pi-lifecycle.jsonl",
        stderr_file=stderr, on_status=publish, no_progress_seconds=15,
        shutdown_grace_seconds=3)
    stderr.close()
    return result


def summarize_session(output, phase, lifecycle):
    rows = []
    path = output / f"mission-{phase}-pi-session.jsonl"
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    usage = []
    for event in rows:
        message = event.get("message") or event.get("assistantMessageEvent", {}).get("message")
        if isinstance(message, dict) and isinstance(message.get("usage"), dict):
            usage.append(message["usage"])
    totals = {}
    for key in ("input", "output", "cacheRead", "cacheWrite", "totalTokens"):
        values = [row.get(key) for row in usage if isinstance(row.get(key), (int, float))]
        totals[key] = sum(values) if values else None
    starts = [row for row in rows if row.get("type") == "tool_execution_start"]
    ends = [row for row in rows if row.get("type") == "tool_execution_end"]
    return {"model": MODEL, "event_count": len(rows), "turn_end_events": sum(row.get("type") == "turn_end" for row in rows),
        "tool_call_starts": len(starts), "tool_call_ends": len(ends),
        "tool_calls_by_name": {name: sum(row.get("toolName") == name for row in starts)
                               for name in ATOMIC_TOOLS},
        "usage_reported_by_pi": totals, "event_stream_bytes": path.stat().st_size,
        "timed_out": lifecycle["timed_out"], "exit_code": lifecycle["exit_code"],
        "elapsed_ms": lifecycle["elapsed_ms"], "observer": lifecycle["observer"],
        "pending_tool_ids": lifecycle.get("pending_tool_ids", [])}


def model_checkpoint(checkpoint):
    """Return verified portable facts; omit host document IDs and transcript data."""
    return {key: checkpoint[key] for key in (
        "schema", "version", "revision", "execution_profile_id", "semantic_fingerprint",
        "workspace_facts", "completed_missions", "active_mission", "unsupported")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=pathlib.Path,
                        default=HERE / "results/cycle19-empty-workspace")
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--open-browser", action="store_true")
    parser.add_argument("--preflight-only", action="store_true",
                        help="verify the isolated provider model and exact Pi tool inventory without inference")
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"output directory already contains evidence: {out}")
    out.mkdir(parents=True, exist_ok=True)
    runtime = HERE / ".runtime" / "cycle19"
    source_config = pathlib.Path(os.environ.get("PI_CODING_AGENT_DIR", pathlib.Path.home() / ".sushi/pi")).expanduser()
    models_file, key_env = isolated_config(runtime, source_config)
    env = os.environ.copy()
    env.update(key_env)
    env["PI_CODING_AGENT_DIR"] = str(runtime)
    env["PI_CODING_AGENT_SESSION_DIR"] = str(out / "pi-sessions")
    env["BASIC_WS_AUTHORING_MODE"] = "atomic"

    # Select a loopback port before launching the long-lived authoritative
    # gateway process. It owns the only Workspace for the campaign.
    with socket.socket() as reserve:
        reserve.bind(("127.0.0.1", 0))
        gateway_port = reserve.getsockname()[1]
    gateway_proc = subprocess.Popen([sys.executable, str(HERE / "cycle19_gateway.py"),
        "--output", str(out), "--port", str(gateway_port)],
        stdout=subprocess.PIPE, stderr=(out / "gateway-stderr.log").open("w", encoding="utf-8"),
        text=True, env=env)
    viewer = None
    try:
        ready_timeout = time.monotonic() + 15
        while time.monotonic() < ready_timeout and gateway_proc.poll() is None:
            if select.select([gateway_proc.stdout], [], [], .1)[0]:
                break
        else:
            raise RuntimeError("Cycle 19 gateway startup timed out")
        ready_line = gateway_proc.stdout.readline()
        ready = json.loads(ready_line)
        if not ready.get("ready") or ready.get("host") != "127.0.0.1":
            raise RuntimeError("Cycle 19 gateway did not start on loopback")
        host, port = "127.0.0.1", ready["port"]
        env["BASIC_WS_PI_GATEWAY"] = f"{host}:{port}"
        viewer = subprocess.Popen([sys.executable, str(ROOT / "scripts/basic-visual.py"),
            "live", str(out), "--port", "0"], stdout=subprocess.PIPE,
            stderr=(out / "viewer-stderr.log").open("w", encoding="utf-8"), text=True)
        viewer_url = viewer.stdout.readline().strip().split(": ", 1)[-1]
        if not viewer_url.startswith("http://127.0.0.1:"):
            raise RuntimeError("Cycle 19 live viewer failed to bind to loopback")
        (out / "viewer-url.txt").write_text(viewer_url + "\n", encoding="utf-8")
        wait_http(viewer_url)

        base = ["pi", "--provider", "sushi", "--model", MODEL, "--thinking", "low",
            "--extension", str(HERE / "extension.ts"), "--no-extensions", "--no-mcp",
            "--no-skills", "--no-context-files", "--no-prompt-templates", "--no-builtin-tools",
            "--no-tools", "--tools", ",".join(ATOMIC_TOOLS)]
        # The preflight reports model inventory and the exact active tool list;
        # inference requests below are the only provider calls in this campaign.
        rpc_preflight(env, base, out, ATOMIC_TOOLS)
        schema_rows = json.loads((out / "tool-schemas.json").read_text(encoding="utf-8"))
        constructor = next((row for row in schema_rows if row.get("name") == "workspace_preview_function"), None)
        body_schema = ((constructor or {}).get("parameters") or {}).get("properties", {}).get("body", {})
        if body_schema.get("type") != "array" or body_schema.get("items") == {}:
            raise RuntimeError("Pi's active constructor schema is missing its typed body grammar")
        if args.preflight_only:
            summary = {"schema": "basic-workspace.cycle19-preflight", "version": 1,
                "model": MODEL, "pi_version": "1.5.0", "active_tools": ATOMIC_TOOLS,
                "active_tool_count": len(ATOMIC_TOOLS), "tool_schema_bytes": (out / "tool-schemas.json").stat().st_size,
                "constructor_body_schema": body_schema, "model_inventory_verified": True,
                "endpoint_inference_requested": False, "inference_started": False,
                "workspace_empty": True, "workspace_revision": ready["revision"]}
            write_json(out / "preflight-summary.json", summary)
            print(json.dumps({"preflight_passed": True, "model": MODEL,
                "tools": ATOMIC_TOOLS, "schema_bytes": summary["tool_schema_bytes"],
                "inference_started": False}, indent=2))
            viewer.terminate()
            viewer.wait(timeout=3)
            return 0
        if args.open_browser:
            webbrowser.open(viewer_url)
        setup = {"schema": "basic-workspace.cycle19-experiment-plan", "version": 1,
            "model": MODEL, "pi_version": "1.5.0", "workspace_start": "empty document, revision 1, zero tokens",
            "missions": [json.loads((out / "MISSION-1.json").read_text()),
                         json.loads((out / "MISSION-2.json").read_text())],
            "authoring_mode": "atomic whole-function constructor", "session_limit_per_mission": 1,
            "session_timeout_seconds": args.timeout, "automatic_retries": 0,
            "preflight": json.loads((out / "pi-rpc-preflight.json").read_text())}
        write_json(out / "campaign-plan.json", setup)
        instructions = ("Use only the semantic Workspace tools. Start by discovering functions and inspecting the "
            "current structure. The function body is typed JSON: assignments target {\"kind\":\"result\"}; expressions "
            "use numeric literals, local parameter references, or calls using a discovered portable handle; IF conditions "
            "compare two such expressions. THEN/ELSE arrays contain only result assignments; nested IF is unsupported, "
            "so use sequential IF statements when needed. Do not send "
            "BASIC source. Preview, commit only an accepted preview, then validate the explicit live revision through "
            "the MIR interpreter and JIT. The gateway enforces this mission; stop if a tool rejects your proposal.")

        prompt1 = ("Mission 1: Create CLAMP_SCORE(X). For X below 0 return 0; for X from 0 through 100 return X; "
            "for X above 100 return 100. The Workspace is genuinely empty. Construct a numeric function using typed "
            "semantic operations; do not assume existing symbols. The independent host will check values -100, -1, 0, "
            "1, 59, 60, 99, 100, 101 and 200. " + instructions)
        (out / "mission-1-prompt.txt").write_text(prompt1 + "\n", encoding="utf-8")
        lifecycle1 = run_session(phase=1, prompt=prompt1, output=out, base=base, env=env,
                                 host=host, port=port, timeout=args.timeout)
        sess1 = summarize_session(out, 1, lifecycle1)
        write_json(out / "mission-1-session-metrics.json", sess1)
        status1 = gateway_call(host, port, "get_status", {})
        validation1 = None
        checkpoint = None
        if status1["committed"]:
            validation1 = gateway_call(host, port, "host_validate", {"expected_revision": status1["revision"]})
        write_json(out / "mission-1-host-validation.json", validation1 or {"mission_complete": False, "not_run": True})
        mission1_completion = gateway_call(host, port, "finalize_session", {
            "timed_out": bool(lifecycle1.get("timed_out")), "pi_exit_code": lifecycle1.get("exit_code"),
            "validation": validation1, "pi_lifecycle": lifecycle1.get("observer", {})})
        write_json(out / "mission-1-completion-states.json", mission1_completion)
        if validation1 and validation1.get("mission_complete"):
            created = gateway_call(host, port, "create_checkpoint", {})
            if created.get("ok"):
                checkpoint = created["checkpoint"]
                # Verify again at the transition boundary before changing the
                # active mission contract or starting a fresh Pi conversation.
                transition = gateway_call(host, port, "advance_mission2", {"checkpoint": checkpoint})
            else:
                transition = created
        else:
            transition = {"ok": False, "code": "MISSION1_HOST_VALIDATION_FAILED", "workspace_changed": False}
        write_json(out / "mission-transition.json", transition)

        lifecycle2 = None
        validation2 = None
        status2 = gateway_call(host, port, "get_status", {})
        if transition.get("ok"):
            public_checkpoint = model_checkpoint(checkpoint)
            write_json(out / "mission-2-recovery-checkpoint.json", public_checkpoint)
            prompt2 = ("Mission 2: Create IS_PASSING(X), returning 1 if the result of CLAMP_SCORE(X) is at least 60, "
                "and 0 otherwise. Unknown or out-of-range inputs follow CLAMP_SCORE's behavior. Preserve CLAMP_SCORE "
                "unchanged and call it through its discovered semantic identity. This is a fresh conversation. "
                "Verified recovery checkpoint (portable semantic facts; not a transcript):\n" +
                json.dumps(public_checkpoint, ensure_ascii=False, separators=(",", ":")) + "\n" + instructions)
            (out / "mission-2-prompt.txt").write_text(prompt2 + "\n", encoding="utf-8")
            lifecycle2 = run_session(phase=2, prompt=prompt2, output=out, base=base, env=env,
                                     host=host, port=port, timeout=args.timeout)
            sess2 = summarize_session(out, 2, lifecycle2)
            write_json(out / "mission-2-session-metrics.json", sess2)
            status2 = gateway_call(host, port, "get_status", {})
            if status2["committed"]:
                validation2 = gateway_call(host, port, "host_validate", {"expected_revision": status2["revision"]})
            write_json(out / "mission-2-host-validation.json", validation2 or {"mission_complete": False, "not_run": True})
        final_validation = validation2 if transition.get("ok") else validation1
        final_lifecycle = lifecycle2 or lifecycle1
        final_status = status2 if lifecycle2 else status1
        completion = gateway_call(host, port, "finalize_session", {
            "timed_out": bool(final_lifecycle.get("timed_out")),
            "pi_exit_code": final_lifecycle.get("exit_code"),
            "validation": final_validation,
            "pi_lifecycle": final_lifecycle.get("observer", {})})
        write_json(out / "completion-states.json", completion)
        html = subprocess.run([sys.executable, str(ROOT / "scripts/basic-visual.py"), "replay", str(out)],
                              capture_output=True, text=True)
        if html.returncode:
            (out / "visual-replay-error.txt").write_text(html.stderr, encoding="utf-8")
        # Summarize the two independent mission outcomes. A Pi timeout does not
        # erase a commit or host validation, and does not count as session success.
        schemas = out / "tool-schemas.json"
        journal = out / "history.jsonl"
        frames = out / "visual-frames-generic.json"
        summary = {"schema": "basic-workspace.cycle19-campaign-summary", "version": 1,
            "campaign_kind": "genuine_pi_model", "provider": "sushi", "model": MODEL,
            "pi_version": "1.5.0", "initial_revision": 1, "initial_program_empty": True,
            "missions": {"mission_1": {"status": "passed" if validation1 and validation1.get("mission_complete") else "failed_or_incomplete",
                "revision": validation1.get("revision") if validation1 else 1,
                "session": sess1, "host_validation": validation1},
                "mission_2": {"status": "passed" if validation2 and validation2.get("mission_complete") else
                    "not_started" if not transition.get("ok") else "failed_or_incomplete",
                    "revision": validation2.get("revision") if validation2 else status2.get("revision"),
                    "session": summarize_session(out, 2, lifecycle2) if lifecycle2 else None,
                    "host_validation": validation2}},
            "mission_transition": transition, "final_status": final_status,
            "completion_states": completion.get("completion_states"),
            "tool_schema_bytes": schemas.stat().st_size if schemas.exists() else None,
            "checkpoint_bytes": (out / "mission-2-recovery-checkpoint.json").stat().st_size if (out / "mission-2-recovery-checkpoint.json").exists() else None,
            "constructive_stream_bytes": (out / "constructive-operations.json").stat().st_size if (out / "constructive-operations.json").exists() else 0,
            "historical_journal_bytes": journal.stat().st_size if journal.exists() else 0,
            "visual_frame_count": len(json.loads(frames.read_text())["campaigns"][0]["frames"]) if frames.exists() else None,
            "visual_html": str(out / "visual-replay-generic.html") if html.returncode == 0 else None,
            "viewer_url": viewer_url, "preflight_inference_started": False,
            "mission_session_limits": {"per_mission_seconds": args.timeout, "automatic_retries": 0}}
        write_json(out / "summary.json", summary)
        print(json.dumps({"summary": str(out / "summary.json"), "viewer": viewer_url,
            "revision": final_status.get("revision"), "mission1_passed": bool(validation1 and validation1.get("mission_complete")),
            "mission2_passed": bool(validation2 and validation2.get("mission_complete")),
            "mission2_started": bool(transition.get("ok")), "visual_replay": summary["visual_html"]}, indent=2))
        if html.returncode:
            return 1
        return 0 if validation2 and validation2.get("mission_complete") else 1
    finally:
        for proc in (gateway_proc, viewer):
            if proc is not None and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()


if __name__ == "__main__":
    raise SystemExit(main())
