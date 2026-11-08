"""Bounded, content-free observations for Pi JSONL lifecycle streams."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
import signal
import subprocess
import threading
import time
from typing import Any

USAGE_KEYS = ("input", "output", "cacheRead", "cacheWrite", "totalTokens", "reasoning")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def completion_states(*, committed: bool, validation: dict[str, Any] | None,
                      timed_out: bool, exit_code: int | None,
                      agent_end_seen: bool, agent_settled_seen: bool,
                      pending_tool_count: int = 0,
                      authorization_status: str | None = None) -> dict[str, str]:
    """Keep code correctness, gateway/host result, and Pi lifecycle independent."""
    # Validation profiles have mission-specific oracle fields (for example
    # ``boundary_oracle`` in Cycle 19 and named predicate checks in Cycle 20).
    # The common, host-owned completion contract is the explicit mission result,
    # interpreter/JIT agreement, value matching when reported, and replay when
    # replay is part of the campaign. Do not require a field belonging to one
    # earlier mission schema.
    host_ok = bool(validation and validation.get("mission_complete") is True
        and validation.get("engines_agree") is True
        and validation.get("values_match", True) is True
        and (validation.get("replay") or {}).get("passed") is True)
    semantic = "passed" if host_ok else "failed" if validation is not None else "not_validated"
    host = "passed" if host_ok else "failed" if validation is not None else "not_run"
    agent_session = ("completed" if agent_settled_seen else
        "ended_not_settled" if agent_end_seen else "incomplete_or_unobserved")
    if timed_out:
        process = "timed_out"
    elif exit_code is not None and exit_code != 0:
        process = "exited_nonzero"
    elif exit_code == 0 and pending_tool_count:
        process = "exited_with_pending_tool"
    elif exit_code == 0:
        process = "exited_normally"
    else:
        process = "unknown"
    if authorization_status not in {"authorized", "denied", "not_attempted"}:
        authorization_status = "authorized" if committed else "not_attempted"
    return {"semantic_program": semantic,
            "mission_authorization": authorization_status,
            "program_commit": "committed" if committed else "not_committed",
            "host_validation": host,
            "pi_agent_session": agent_session,
            "launcher_process": process}


@dataclass
class PiEventObserver:
    """Summarize events without retaining prompts, deltas, arguments, or results."""
    sequence: int = 0
    counts: dict[str, int] = field(default_factory=dict)
    seen_tool_boundaries: set[tuple[str, str]] = field(default_factory=set)
    pending_tools: dict[str, str] = field(default_factory=dict)
    assistant_stream_open: bool = False
    agent_started: bool = False
    agent_end_seen: bool = False
    agent_settled_seen: bool = False
    last_event_type: str | None = None
    last_event_wall_utc: str | None = None
    last_event_monotonic_ns: int | None = None
    last_usage: dict[str, int | float] | None = None
    provider_stream_error_seen: bool = False

    def observe(self, row: dict[str, Any], *, wall_utc: str | None = None,
                monotonic_ns: int | None = None) -> dict[str, Any]:
        self.sequence += 1
        typ = str(row.get("type", "unknown"))
        self.counts[typ] = self.counts.get(typ, 0) + 1
        wall = wall_utc or utc_now()
        meta: dict[str, Any] = {"seq": self.sequence, "observed_at_utc": wall,
                                "event_type": typ}
        if monotonic_ns is not None:
            meta["observed_monotonic_ns"] = monotonic_ns
        self.last_event_type = typ
        self.last_event_wall_utc = wall
        self.last_event_monotonic_ns = monotonic_ns

        message = row.get("message") if isinstance(row.get("message"), dict) else {}
        if typ in {"message_start", "message_end"}:
            role = message.get("role")
            if role is not None:
                meta["role"] = role
            if isinstance(message.get("timestamp"), (int, float)):
                meta["pi_message_timestamp_ms"] = message["timestamp"]
            if message.get("stopReason") is not None:
                meta["stop_reason"] = message["stopReason"]
            if isinstance(message.get("provider"), str):
                meta["provider"] = message["provider"]
            if isinstance(message.get("model"), str):
                meta["model"] = message["model"]
            if role == "assistant":
                self.assistant_stream_open = typ == "message_start"
            usage = message.get("usage")
            if isinstance(usage, dict):
                selected = {k: usage[k] for k in USAGE_KEYS if isinstance(usage.get(k), (int, float))}
                if selected and any(selected.values()):
                    self.last_usage = selected
                    meta["usage"] = selected

        update = row.get("assistantMessageEvent") if isinstance(row.get("assistantMessageEvent"), dict) else {}
        if typ == "message_update":
            event_type = update.get("type")
            if event_type is not None:
                meta["assistant_event_type"] = event_type
            if isinstance(update.get("contentIndex"), int):
                meta["content_index"] = update["contentIndex"]
            delta = update.get("delta")
            if isinstance(delta, str):
                meta["delta_chars"] = len(delta)
            if event_type == "error":
                self.provider_stream_error_seen = True
            usage = row.get("usage")
            if isinstance(usage, dict):
                selected = {k: usage[k] for k in USAGE_KEYS if isinstance(usage.get(k), (int, float))}
                if selected and any(selected.values()):
                    self.last_usage = selected
                    meta["usage"] = selected

        if typ == "agent_start":
            self.agent_started = True
        elif typ == "agent_end":
            self.agent_end_seen = True
            if "willRetry" in row:
                meta["will_retry"] = bool(row["willRetry"])
        elif typ == "agent_settled":
            self.agent_settled_seen = True
            meta["aborted"] = bool(row.get("aborted", False))

        if typ in {"tool_execution_start", "tool_execution_end"}:
            call_id = row.get("toolCallId")
            tool_name = row.get("toolName")
            if isinstance(call_id, str):
                meta["tool_call_id"] = call_id
                key = (typ, call_id)
                duplicate = key in self.seen_tool_boundaries
                meta["duplicate_boundary"] = duplicate
                if not duplicate:
                    self.seen_tool_boundaries.add(key)
                    if typ == "tool_execution_start":
                        self.pending_tools[call_id] = str(tool_name or "unknown")
                    else:
                        self.pending_tools.pop(call_id, None)
            if isinstance(tool_name, str):
                meta["tool_name"] = tool_name
            if typ == "tool_execution_end":
                if isinstance(row.get("durationMs"), (int, float)):
                    meta["duration_ms"] = row["durationMs"]
                if isinstance(row.get("isError"), bool):
                    meta["is_error"] = row["isError"]
        return meta

    def state(self) -> dict[str, Any]:
        if self.agent_settled_seen:
            state = "settled"
        elif self.pending_tools:
            state = "tool_in_progress"
        elif self.assistant_stream_open:
            state = "assistant_stream_open"
        elif self.agent_started and not self.agent_end_seen:
            state = "agent_active_no_open_message"
        elif self.agent_end_seen:
            state = "agent_end_seen"
        else:
            state = "not_started"
        return {"state": state, "agent_started": self.agent_started,
                "agent_end_seen": self.agent_end_seen,
                "agent_settled_seen": self.agent_settled_seen,
                "assistant_stream_open": self.assistant_stream_open,
                "pending_tools": dict(self.pending_tools),
                "last_event_type": self.last_event_type,
                "last_event_wall_utc": self.last_event_wall_utc,
                "last_event_monotonic_ns": self.last_event_monotonic_ns,
                "last_provider_usage": self.last_usage,
                "provider_stream_error_seen": self.provider_stream_error_seen,
                "event_counts": dict(self.counts)}


def run_pi_observed(command: list[str], *, env: dict[str, str], timeout_seconds: float,
                    raw_event_path: Any, lifecycle_path: Any, stderr_file: Any,
                    on_status: Any = None, no_progress_seconds: float = 10.0,
                    shutdown_grace_seconds: float = 1.0,
                    max_transcript_bytes: int = 64 * 1024 * 1024,
                    max_line_bytes: int = 2 * 1024 * 1024,
                    max_lifecycle_rows: int = 100_000) -> dict[str, Any]:
    """Run Pi JSON mode while timestamping JSONL arrivals and bounded process lifecycle.

    Raw stdout is copied byte-for-byte to `raw_event_path`. The compact lifecycle
    file stores event types, counters, timestamps and token usage only; it does
    not duplicate prompts, tool arguments, message deltas, or tool results.
    """
    start_mono = time.monotonic_ns()
    start_wall = utc_now()
    observer = PiEventObserver()
    state_lock = threading.Lock()
    reader_done = threading.Event()
    stop_due_to_size = threading.Event()
    reader_error: list[str] = []
    stats = {"raw_bytes": 0, "lifecycle_rows": 0, "lifecycle_dropped": 0,
             "malformed_json_lines": 0, "overlong_lines": 0,
             "transcript_truncated": False, "last_arrival_monotonic_ns": start_mono}
    rows_lock = threading.Lock()

    with open(raw_event_path, "wb") as raw_file, open(lifecycle_path, "w", encoding="utf-8") as meta_file:
        def write_meta(event: str, **fields: Any) -> None:
            with rows_lock:
                if stats["lifecycle_rows"] >= max_lifecycle_rows:
                    stats["lifecycle_dropped"] += 1
                    return
                row = {"seq": stats["lifecycle_rows"] + 1, "observed_at_utc": utc_now(),
                       "observed_monotonic_ns": time.monotonic_ns(), "record_type": event, **fields}
                meta_file.write(json.dumps(row, separators=(",", ":"), ensure_ascii=False) + "\n")
                meta_file.flush()
                stats["lifecycle_rows"] += 1

        write_meta("launcher_process_start", command_name=os.path.basename(command[0]),
                   timeout_seconds=timeout_seconds, shutdown_grace_seconds=shutdown_grace_seconds)
        try:
            proc = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                    stderr=stderr_file, env=env, bufsize=0)
        except Exception as exc:
            write_meta("launcher_start_failed", error_type=type(exc).__name__)
            return {"timed_out": False, "exit_code": None, "process_started": False,
                    "start_wall_utc": start_wall, "elapsed_ms": round((time.monotonic_ns()-start_mono)/1e6, 3),
                    "observer": observer.state(), "stats": stats}
        assert proc.stdout is not None
        process_started_mono = time.monotonic_ns()
        write_meta("pi_process_started", pid=proc.pid)

        def read_events() -> None:
            try:
                while True:
                    line = proc.stdout.readline(max_line_bytes + 1)
                    if not line:
                        break
                    now_mono = time.monotonic_ns()
                    stats["last_arrival_monotonic_ns"] = now_mono
                    stats["raw_bytes"] += len(line)
                    if len(line) > max_line_bytes:
                        stats["overlong_lines"] += 1
                        stats["transcript_truncated"] = True
                        stop_due_to_size.set()
                        write_meta("pi_jsonl_line_too_large", line_bytes=len(line), max_line_bytes=max_line_bytes)
                        break
                    if stats["raw_bytes"] > max_transcript_bytes:
                        stats["transcript_truncated"] = True
                        stop_due_to_size.set()
                        write_meta("pi_transcript_size_limit", max_transcript_bytes=max_transcript_bytes)
                        break
                    raw_file.write(line)
                    raw_file.flush()
                    try:
                        row = json.loads(line)
                        if not isinstance(row, dict):
                            raise ValueError("JSONL row is not an object")
                    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
                        stats["malformed_json_lines"] += 1
                        write_meta("pi_non_json_line", line_bytes=len(line))
                        continue
                    with state_lock:
                        metadata = observer.observe(row, wall_utc=utc_now(), monotonic_ns=now_mono)
                    write_meta("pi_event_observed", **metadata)
            except Exception as exc:
                reader_error.append(type(exc).__name__)
                write_meta("pi_stdout_reader_error", error_type=type(exc).__name__)
            finally:
                reader_done.set()

        reader = threading.Thread(target=read_events, name="pi-jsonl-reader", daemon=True)
        reader.start()
        if on_status:
            try:
                on_status("working", {"observed_at_utc": start_wall, "description":"Pi process started; waiting for its event stream."})
            except Exception as exc:
                write_meta("status_delivery_failed", error_type=type(exc).__name__, status="working")

        timed_out = False
        idle_state: str | None = None
        reported_agent_status: str | None = None
        deadline = time.monotonic() + max(0.0, timeout_seconds)
        while proc.poll() is None:
            now_mono = time.monotonic_ns()
            if stop_due_to_size.is_set():
                write_meta("launcher_safety_limit_reached")
                break
            if time.monotonic() >= deadline:
                timed_out = True
                write_meta("launcher_timeout", timeout_seconds=timeout_seconds)
                break
            with state_lock:
                snapshot = observer.state()
                last = stats["last_arrival_monotonic_ns"]
            agent_status = ("agent_session_completed" if snapshot["agent_settled_seen"] else
                "agent_turn_ended" if snapshot["agent_end_seen"] else None)
            if agent_status and agent_status != reported_agent_status:
                write_meta("pi_agent_lifecycle", state=agent_status,
                           agent_end_seen=snapshot["agent_end_seen"],
                           agent_settled_seen=snapshot["agent_settled_seen"])
                if on_status:
                    try: on_status(agent_status, {"description":"Pi emitted its agent completion lifecycle event.",
                        "agent_end_seen":snapshot["agent_end_seen"],"agent_settled_seen":snapshot["agent_settled_seen"]})
                    except Exception as exc: write_meta("status_delivery_failed", error_type=type(exc).__name__, status=agent_status)
                reported_agent_status=agent_status
            idle_seconds = max(0.0, (now_mono - last) / 1e9)
            current_idle = ("waiting_for_tool" if snapshot["pending_tools"] else "no_observable_progress")
            if idle_seconds >= no_progress_seconds and snapshot["state"] not in {"settled", "not_started"} and idle_state != current_idle:
                info = {"idle_seconds":round(idle_seconds, 3), "last_event_type":snapshot["last_event_type"],
                        "last_event_wall_utc":snapshot["last_event_wall_utc"],
                        "assistant_stream_open":snapshot["assistant_stream_open"],
                        "pending_tool_names":list(snapshot["pending_tools"].values()),
                        "description":"No Pi JSON event has arrived within the observation interval; this does not identify whether the provider, model generation, or Pi is waiting."}
                write_meta("no_progress_interval", **info)
                if on_status:
                    try: on_status(current_idle, info)
                    except Exception as exc: write_meta("status_delivery_failed", error_type=type(exc).__name__, status=current_idle)
                idle_state = current_idle
            elif idle_state is not None and now_mono - last < int(no_progress_seconds * 1e9):
                write_meta("pi_activity_resumed", previous_status=idle_state, last_event_type=snapshot["last_event_type"])
                if on_status:
                    try: on_status("working", {"last_event_type":snapshot["last_event_type"],"description":"Pi JSON events resumed."})
                    except Exception as exc: write_meta("status_delivery_failed", error_type=type(exc).__name__, status="working")
                idle_state = None
            time.sleep(0.05)

        if timed_out or stop_due_to_size.is_set():
            try:
                proc.send_signal(signal.SIGTERM)
                write_meta("pi_graceful_shutdown_signal", signal="SIGTERM")
            except ProcessLookupError:
                pass
            try:
                proc.wait(timeout=max(0.0, shutdown_grace_seconds))
            except subprocess.TimeoutExpired:
                proc.kill()
                write_meta("pi_hard_kill_after_grace", shutdown_grace_seconds=shutdown_grace_seconds)
                proc.wait()
        else:
            proc.wait()
        reader.join(timeout=max(1.0, shutdown_grace_seconds + 0.5))
        if reader.is_alive():
            proc.stdout.close()
            reader.join(timeout=0.5)
            write_meta("pi_jsonl_reader_join_timeout")
        proc.stdout.close()
        with state_lock:
            final_observer = observer.state()
        elapsed = (time.monotonic_ns() - process_started_mono) / 1e6
        write_meta("pi_process_exit", exit_code=proc.returncode, timed_out=timed_out,
                   elapsed_ms=round(elapsed, 3), agent_end_seen=final_observer["agent_end_seen"],
                   agent_settled_seen=final_observer["agent_settled_seen"],
                   pending_tool_count=len(final_observer["pending_tools"]))
        if reader_error:
            stats["reader_errors"] = reader_error
        return {"timed_out":timed_out, "exit_code":proc.returncode, "process_started":True,
                "start_wall_utc":start_wall, "elapsed_ms":round(elapsed, 3),
                "agent_end_seen":final_observer["agent_end_seen"],
                "agent_settled_seen":final_observer["agent_settled_seen"],
                "pending_tool_ids":sorted(final_observer["pending_tools"]),
                "observer":final_observer,"stats":stats}
