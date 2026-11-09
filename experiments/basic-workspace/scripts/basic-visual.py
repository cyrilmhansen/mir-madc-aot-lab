#!/usr/bin/env python3
"""Operator entry point for offline replay, append-only live viewing, and recorded demos."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from visualization import (FRAME_SCHEMA, FRAME_VERSION, PresentationError, VisualFrameCompiler,
                           load_source_bundle, normalize_numeric_observation, render, serve_recorded_demo)


def compile_campaign(campaign_dir: Path, evidence_view_path: Path | None = None) -> dict:
    source, events, snapshots = load_source_bundle(campaign_dir)
    campaign = dict(source["campaign"])
    presentation_session_id = f"{campaign['id']}/{campaign_dir.name}"
    campaign["presentation_session_id"] = presentation_session_id
    oracle_path = campaign_dir / "validation.json"
    oracle = json.loads(oracle_path.read_text(encoding="utf-8")) if oracle_path.exists() else None
    display_path = evidence_view_path or (campaign_dir / "visual-evidence-view.json")
    display = json.loads(display_path.read_text(encoding="utf-8")) if display_path.exists() else None
    compiler = VisualFrameCompiler(str(campaign["id"]), str(campaign["title"]),
                                   str(campaign.get("filename", "PROGRAM.bas")),
                                   int(source["initial"]["revision"]), str(source["initial"]["code"]),
                                   snapshots, list(source["initial"].get("dependencies", [])),
                                   presentation_session_id)
    for event in events:
        if event.get("event_type") == "validation":
            normalized = normalize_numeric_observation(event, oracle, display)
            if normalized is not None:
                event = {**event, "observation": normalized}
        compiler.consume(event)
    return {"schema": FRAME_SCHEMA, "version": FRAME_VERSION,
            "campaigns": [{**campaign, "frames": compiler.frames}],
            "presentation_event_schema": {"id": "basic-workspace.presentation-event", "version": 1}}


def replay(campaign_dir: Path, output_dir: Path | None = None,
           evidence_view_path: Path | None = None) -> Path:
    data = compile_campaign(campaign_dir, evidence_view_path)
    output_dir = output_dir or campaign_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    frames_path = output_dir / "visual-frames-generic.json"
    html_path = output_dir / "visual-replay-generic.html"
    frames_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    render(data, html_path)
    return html_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    for mode in ("replay", "live", "demo"):
        p = sub.add_parser(mode)
        p.add_argument("campaign_directory", type=Path)
        if mode in ("live", "demo"):
            p.add_argument("--port", type=int, default=8765)
        if mode == "demo":
            p.add_argument("--interval", type=float, default=0.65,
                           help="seconds between recorded evidence frames")
        if mode == "replay":
            p.add_argument("--output-dir", type=Path,
                           help="write derived frames and HTML here; source evidence stays untouched")
            p.add_argument("--evidence-view", type=Path,
                           help="optional display selection for recorded validation rows")
    args = parser.parse_args()
    try:
        directory = args.campaign_directory.resolve()
        if args.mode == "replay":
            path = replay(directory, args.output_dir.resolve() if args.output_dir else None,
                          args.evidence_view.resolve() if args.evidence_view else None)
            print(path)
            return 0
        serve_recorded_demo(directory, port=args.port,
                            interval=getattr(args, "interval", 0.65),
                            follow=args.mode == "live")
        return 0
    except (OSError, ValueError, PresentationError) as exc:
        parser.exit(2, f"basic-visual: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
