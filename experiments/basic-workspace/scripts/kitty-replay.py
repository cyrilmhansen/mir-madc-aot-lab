#!/usr/bin/env python3
"""Play an observed semantic event trace in Kitty or another ANSI terminal."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from importlib.machinery import SourceFileLoader

_renderer = SourceFileLoader("semantic_replay_renderer", str(Path(__file__).with_name("render-semantic-replay.py"))).load_module()
LABELS = _renderer.LABELS

COLORS = {"green": "\x1b[32;1m", "red": "\x1b[31;1m", "amber": "\x1b[33;1m",
          "blue": "\x1b[36;1m", "muted": "\x1b[2m", "reset": "\x1b[0m"}
ENABLE_SHADERS = False


def state_at(events: list[dict[str, Any]], index: int) -> tuple[str, Any]:
    source, revision = "", "—"
    for event in events[:index + 1]:
        if "program_snapshot" in event and event.get("phase") in ("initial-construction", "agent", "scripted-demo"):
            source = event["program_snapshot"]
            revision = event.get("resulting_revision", event.get("revision", revision))
    return source, revision


def committed_structure_at(events: list[dict[str, Any]], index: int) -> dict[str, Any]:
    structure: dict[str, Any] = {}
    for event in events[:index + 1]:
        if event.get("event") == "transaction_committed" and event.get("phase") in ("initial-construction", "agent", "scripted-demo"):
            structure = event.get("semantic_snapshot", structure)
    return structure


def shader_event(name: str) -> None:
    if not ENABLE_SHADERS or not os.environ.get("KITTY_LISTEN_ON"):
        return
    result = subprocess.run(["kitty", "@", "action", "shader_event", name],
                            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=2, check=False)
    if result.returncode:
        print(f"{COLORS['muted']}Kitty shader event unavailable: {result.stderr.strip()}{COLORS['reset']}", file=sys.stderr)


def frame(events: list[dict[str, Any]], index: int, clear: bool) -> None:
    event = events[index]
    if clear:
        sys.stdout.write("\x1b[2J\x1b[H")
    kind = event["event"]
    status, color = ("COMMITTED", "green") if kind == "transaction_committed" else \
                    ("DENIED — STATE UNCHANGED", "red") if kind == "transaction_rejected" else \
                    ("PREVIEW — NOT COMMITTED", "amber") if kind == "preview_accepted" else \
                    ("OBSERVED", "blue")
    start = next((e for e in events if e["event"] == "session_started"), {})
    campaign = start.get("campaign", "semantic operation trace")
    campaign_kind = start.get("campaign_kind", "unknown")
    print(f"{COLORS['blue']}{campaign} · {campaign_kind}  {index + 1}/{len(events)}{COLORS['reset']}")
    print(f"{COLORS[color]}{status}{COLORS['reset']}  {LABELS.get(kind, kind)}")
    print(f"{COLORS['muted']}phase={event.get('phase', '—')}  seq={event.get('sequence')}  "
          f"base={event.get('base_revision', '—')}  result={event.get('resulting_revision', event.get('revision', '—'))}{COLORS['reset']}")
    print(f"{COLORS['muted']}provenance={event.get('actor', 'unspecified')}  mission={event.get('mission_id', '—')}{COLORS['reset']}")
    for key in ("operation", "tool", "target_handle", "target_statement_id", "statement_handle",
                "handle", "name", "new_age", "code", "message", "passed", "outputs",
                "expected", "engine_results", "structural_equivalence", "binding_equivalence",
                "behavioral_equivalence", "bound_call", "callee_handle", "function_call_edges",
                "identity_remappings", "mission_complete"):
        if key in event:
            print(f"{key}: {json.dumps(event[key], ensure_ascii=False) if isinstance(event[key], (dict, list)) else event[key]}")
    if event.get("statement"):
        statement = event["statement"]
        print(f"semantic statement: {statement.get('kind')} at {statement.get('nesting_path')} · "
              f"target={event.get('target_handle', statement.get('target_symbol_id'))} · "
              f"index={statement.get('target_index')} · value={statement.get('expression')}")
    result = event.get("result")
    if isinstance(result, dict):
        visible = {k: result[k] for k in ("ok", "committed", "code", "message", "revision",
                                           "target_handle", "new_age", "passed", "results", "expected") if k in result}
        if visible:
            print("tool result: " + json.dumps(visible, ensure_ascii=False))
    if event.get("preview_diff"):
        print(f"\n{COLORS['amber']}PROPOSED PREVIEW DIFF (not current state){COLORS['reset']}")
        print(event["preview_diff"])
    source, revision = state_at(events, index)
    structure = committed_structure_at(events, index)
    for function in structure.get("functions", []):
        arrays = ", ".join(f"{a.get('name')}[]" for a in function.get("arrays", [])) or "no arrays"
        print(f"{COLORS['blue']}semantic function: {function.get('name')}({', '.join(function.get('parameters', []))}) · {arrays}{COLORS['reset']}")
        for statement in function.get("statements", []):
            if statement.get("kind") == "if":
                print(f"  IF block · {statement.get('condition')}")
            elif statement.get("kind") == "for":
                print(f"  FOR block · {statement.get('variable_handle')} {statement.get('start')}..{statement.get('end')}")
        if function.get("handle") == "is_senior.function":
            print(f"  dependency: IS_SENIOR → AGE_BY_ID (call binding is shown on commit event)")
    print(f"\n{COLORS['blue']}CURRENT COMMITTED PROGRAM — revision {revision}{COLORS['reset']}")
    print(source if source else "(empty virtual document)")
    sys.stdout.flush()
    if kind == "symbol_discovered": shader_event("semantic-discovery")
    elif kind == "transaction_committed": shader_event("semantic-commit")
    elif kind in ("transaction_rejected", "preview_rejected"): shader_event("semantic-reject")
    elif kind == "program_executed": shader_event("semantic-result")
    elif kind == "replay_completed": shader_event("semantic-checkpoint")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", nargs="?", type=Path,
                        default=Path(__file__).resolve().parents[1] / "results/semantic-replay/history.jsonl")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--auto", type=float, metavar="SECONDS", help="timed playback interval")
    mode.add_argument("--step", action="store_true", help="wait for Enter between events (default in a TTY)")
    parser.add_argument("--no-clear", action="store_true", help="keep prior frames visible")
    parser.add_argument("--shader-events", action="store_true", help="send optional Kitty user shader events when KITTY_LISTEN_ON is set")
    args = parser.parse_args()
    global ENABLE_SHADERS
    ENABLE_SHADERS = args.shader_events
    events = _renderer.read_events(args.trace)
    interactive = args.step or (args.auto is None and sys.stdin.isatty())
    if args.auto is not None and args.auto <= 0:
        parser.error("--auto interval must be positive")
    if not interactive and args.auto is None:
        parser.error("use this command from a terminal, or provide --auto SECONDS")
    if args.shader_events and not os.environ.get("KITTY_LISTEN_ON"):
        print("KITTY_LISTEN_ON is unset; semantic ANSI playback continues without shaders.", file=sys.stderr)
    for index in range(len(events)):
        frame(events, index, clear=not args.no_clear and sys.stdout.isatty())
        if index == len(events) - 1:
            break
        if interactive:
            try:
                if input("[Enter] next · q quit ")[:1].lower() == "q":
                    break
            except EOFError:
                break
        else:
            time.sleep(args.auto)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
