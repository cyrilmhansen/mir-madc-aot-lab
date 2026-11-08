#!/usr/bin/env python3
"""Continue Cycle 19 Mission 2 from the genuine committed Mission 1 operation."""
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
from run_cycle16 import ATOMIC_TOOLS, MODEL, gateway_call, isolated_config, rpc_preflight
from run_cycle19 import model_checkpoint, summarize_session


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=pathlib.Path,
        default=HERE / "results/cycle19b-recovery/real-agent-02")
    parser.add_argument("--resume-from", type=pathlib.Path,
        default=HERE / "results/cycle19-empty-workspace/real-agent-01")
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--open-browser", action="store_true")
    args = parser.parse_args()
    out, source = args.output.resolve(), args.resume_from.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"output directory already contains evidence: {out}")
    out.mkdir(parents=True, exist_ok=True)
    runtime = HERE / ".runtime" / "cycle19b"
    config_dir = pathlib.Path(os.environ.get("PI_CODING_AGENT_DIR", pathlib.Path.home() / ".sushi/pi")).expanduser()
    _models_file, key_env = isolated_config(runtime, config_dir)
    env = os.environ.copy()
    env.update(key_env)
    env["PI_CODING_AGENT_DIR"] = str(runtime)
    env["PI_CODING_AGENT_SESSION_DIR"] = str(out / "pi-sessions")
    env["BASIC_WS_AUTHORING_MODE"] = "atomic"

    # Reserve a loopback port; the child gateway owns the only authoritative
    # reconstructed Workspace for this resumed mission.
    with socket.socket() as reserve:
        reserve.bind(("127.0.0.1", 0))
        gateway_port = reserve.getsockname()[1]
    gateway_err = (out / "gateway-stderr.log").open("w", encoding="utf-8")
    gateway_proc = subprocess.Popen([sys.executable, str(HERE / "cycle19_gateway.py"),
        "--output", str(out), "--port", str(gateway_port), "--resume-from", str(source)],
        stdout=subprocess.PIPE, stderr=gateway_err, text=True, env=env)
    viewer = None
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and gateway_proc.poll() is None:
            if select.select([gateway_proc.stdout], [], [], .1)[0]:
                break
        else:
            raise RuntimeError("reconstructing gateway did not start")
        ready = json.loads(gateway_proc.stdout.readline())
        verify = ready.get("resume_verification") or {}
        if not ready.get("ready") or ready.get("revision") != 2 or ready.get("phase") != 2 or not verify.get("passed"):
            raise RuntimeError("Mission 1 reconstruction/checkpoint verification failed; model inference was not started")
        host, port = "127.0.0.1", ready["port"]
        env["BASIC_WS_PI_GATEWAY"] = f"{host}:{port}"
        write_json(out / "gateway-ready.json", {k: v for k, v in ready.items() if k != "port"} | {"host": host, "port": port})

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
            "--no-tools", "--tools", ",".join(ATOMIC_TOOLS)]
        rpc_preflight(env, base, out, ATOMIC_TOOLS)
        schemas = json.loads((out / "tool-schemas.json").read_text(encoding="utf-8"))
        constructor = next((row for row in schemas if row.get("name") == "workspace_preview_function"), None)
        props = (constructor or {}).get("parameters", {}).get("properties", {})
        body_schema = props.get("body", {})
        if (body_schema.get("type") != "array" or body_schema.get("items") == {}
                or props.get("callee_handle", {}).get("type") not in (None, "string")):
            raise RuntimeError("active Pi constructor schema does not expose the corrected typed call contract")
        preflight = json.loads((out / "pi-rpc-preflight.json").read_text(encoding="utf-8"))
        write_json(out / "preflight-verification.json", {"model": MODEL, "pi_version": "1.5.0",
            "active_tools": preflight.get("active_tools"), "tool_schema_bytes": (out / "tool-schemas.json").stat().st_size,
            "constructor_typed_body": True, "redundant_callee_handle_optional": True,
            "inference_started": False, "reconstruction_verified_before_inference": verify})
        if args.open_browser:
            webbrowser.open(viewer_url)

        original_checkpoint = json.loads((source / "checkpoint.json").read_text(encoding="utf-8"))
        public_checkpoint = model_checkpoint(original_checkpoint)
        # The new conversation receives only semantic facts/checkpoint and this
        # mission. Earlier model messages and the failed-session transcript are
        # neither read here nor supplied to Pi.
        write_json(out / "mission-2-recovery-checkpoint.json", public_checkpoint)
        prompt = ("Mission: Create IS_PASSING(X), returning 1 when the result of "
            "CLAMP_SCORE(X) is at least 60 and 0 otherwise. Use a semantically bound call "
            "to the discovered CLAMP_SCORE function. Preserve CLAMP_SCORE unchanged. "
            "Start by discovering functions and inspecting the callable signature. Build "
            "the new function with the typed semantic constructor, preview, commit only an "
            "accepted proposal, then request MIR interpreter/JIT validation at the current "
            "revision. Do not provide BASIC source or change existing functions.\n\n"
            "Verified recovery checkpoint (semantic facts, not prior conversation):\n" +
            json.dumps(public_checkpoint, ensure_ascii=False, separators=(",", ":")) +
            "\nUse only the five active semantic tools. The function-call expression contains "
            "the discovered portable function_handle; the optional top-level callee_handle "
            "is normally omitted. The Python MissionGateway rechecks discovery, signature, "
            "authorization, revision, and preserved-program invariants.")
        (out / "mission-2-prompt.txt").write_text(prompt + "\n", encoding="utf-8")

        session_dir = out / "pi-sessions" / "mission-2"
        command = base + ["--mode", "json", "--session-dir", str(session_dir), "--name",
            "Cycle 19B recovered Mission 2 IS_PASSING", "--print", "--", prompt]
        pi_err = (out / "mission-2-pi-stderr.log").open("w", encoding="utf-8")

        def publish(state, info):
            try:
                gateway_call(host, port, "record_agent_status", {"state": state, "info": info}, timeout=5)
            except Exception:
                pass

        lifecycle = run_pi_observed(command, env=env, timeout_seconds=args.timeout,
            raw_event_path=out / "mission-2-pi-session.jsonl",
            lifecycle_path=out / "mission-2-pi-lifecycle.jsonl", stderr_file=pi_err,
            on_status=publish, no_progress_seconds=15, shutdown_grace_seconds=3)
        pi_err.close()
        session_metrics = summarize_session(out, 2, lifecycle)
        write_json(out / "mission-2-session-metrics.json", session_metrics)
        status = gateway_call(host, port, "get_status", {})
        validation = None
        if status["committed"]:
            validation = gateway_call(host, port, "host_validate", {"expected_revision": status["revision"]})
        else:
            write_json(out / "mission-2-host-validation.json", {"mission_complete": False,
                "not_run": True, "authoritative_revision": status["revision"]})
        if validation is not None:
            write_json(out / "mission-2-host-validation.json", validation)
        completion = gateway_call(host, port, "finalize_session", {
            "timed_out": bool(lifecycle.get("timed_out")), "pi_exit_code": lifecycle.get("exit_code"),
            "validation": validation, "pi_lifecycle": lifecycle.get("observer", {})})
        write_json(out / "mission-2-completion-states.json", completion)
        replay_result = subprocess.run([sys.executable, str(ROOT / "scripts/basic-visual.py"),
            "replay", str(out)], capture_output=True, text=True)
        if replay_result.returncode:
            (out / "visual-replay-error.txt").write_text(replay_result.stderr, encoding="utf-8")
        frames_path = out / "visual-frames-generic.json"
        frames = json.loads(frames_path.read_text()) if frames_path.exists() else None
        stream_path = out / "constructive-operations.json"
        schemas_path = out / "tool-schemas.json"
        timings = [json.loads(line) for line in (out / "gateway-tool-timings.jsonl").read_text().splitlines() if line.strip()]
        summary = {"schema": "basic-workspace.cycle19b-summary", "version": 1,
            "campaign_kind": "real_pi_recovery_and_continuation", "provider": "sushi", "model": MODEL,
            "pi_version": "1.5.0", "original_cycle19_evidence": str(source),
            "original_mission1_repeated_as_model": False, "reconstruction": verify,
            "mission2": {"status": "passed" if validation and validation.get("mission_complete") else "failed_or_incomplete",
                "workspace_revision": status["revision"], "committed": status["committed"],
                "host_validation": validation,"session": session_metrics},
            "completion_states": completion.get("completion_states"),
            "tool_schema_bytes": schemas_path.stat().st_size if schemas_path.exists() else None,
            "gateway_total_ms": round(sum(row.get("elapsed_ms", 0) for row in timings if row.get("agent_tool")), 3),
            "checkpoint_bytes": (out / "mission-2-recovery-checkpoint.json").stat().st_size,
            "constructive_stream_bytes": stream_path.stat().st_size if stream_path.exists() else 0,
            "constructive_stream_complete": stream_path.exists(),
            "visual_frames": len(frames["campaigns"][0]["frames"]) if frames else None,
            "visual_html": str(out / "visual-replay-generic.html") if replay_result.returncode == 0 else None,
            "viewer_url": viewer_url,"automatic_retries": 0,"timeout_seconds": args.timeout}
        write_json(out / "summary.json", summary)
        print(json.dumps({"summary": str(out / "summary.json"), "revision": status["revision"],
            "committed": status["committed"], "mission2_passed": bool(validation and validation.get("mission_complete")),
            "completion_states": completion.get("completion_states"), "visual_replay": summary["visual_html"]}, indent=2))
        return 0 if validation and validation.get("mission_complete") else 1
    finally:
        for proc in (gateway_proc, viewer):
            if proc is not None and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    proc.kill(); proc.wait()
        gateway_err.close()


if __name__ == "__main__":
    raise SystemExit(main())
