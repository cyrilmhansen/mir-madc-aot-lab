#!/usr/bin/env python3
"""Operator entry point for offline replay, append-only live viewing, and recorded demos."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from visualization import (FRAME_SCHEMA, FRAME_VERSION, PresentationError, VisualFrameCompiler,
                           load_source_bundle, render, serve_recorded_demo)


def compile_campaign(campaign_dir: Path) -> dict:
    source, events, snapshots = load_source_bundle(campaign_dir)
    campaign = source["campaign"]
    compiler = VisualFrameCompiler(str(campaign["id"]), str(campaign["title"]),
                                   str(campaign.get("filename", "PROGRAM.bas")),
                                   int(source["initial"]["revision"]), str(source["initial"]["code"]),
                                   snapshots, list(source["initial"].get("dependencies", [])))
    for event in events:
        compiler.consume(event)
    return {"schema": FRAME_SCHEMA, "version": FRAME_VERSION,
            "campaigns": [{**campaign, "frames": compiler.frames}],
            "presentation_event_schema": {"id": "basic-workspace.presentation-event", "version": 1}}


def replay(campaign_dir: Path) -> Path:
    data = compile_campaign(campaign_dir)
    frames_path = campaign_dir / "visual-frames-generic.json"
    html_path = campaign_dir / "visual-replay-generic.html"
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
    args = parser.parse_args()
    try:
        directory = args.campaign_directory.resolve()
        if args.mode == "replay":
            path = replay(directory)
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
