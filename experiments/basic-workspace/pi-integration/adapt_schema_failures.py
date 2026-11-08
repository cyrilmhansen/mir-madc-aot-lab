#!/usr/bin/env python3
"""Adapt genuine Pi schema-validation failures into code-viewer presentation events.

Pi can reject tool arguments before the Python MissionGateway receives the
constructor call. This adapter uses only recorded Pi tool_execution_end events;
the raw Pi and gateway journals remain unchanged.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path

PREVIEW_TOOLS={"workspace_preview_function","workspace_preview_function_draft"}

def adapt(directory:Path)->int:
    pi_path=directory/"pi-session.jsonl"; frames_path=directory/"visual-events.jsonl"
    pi=[json.loads(line) for line in pi_path.read_text().splitlines() if line.strip()]
    frames=[json.loads(line) for line in frames_path.read_text().splitlines() if line.strip()]
    existing={row.get("event_id") for row in frames}
    failures=[]
    for row in pi:
        if row.get("type")!="tool_execution_end" or row.get("toolName") not in PREVIEW_TOOLS or not row.get("isError"):
            continue
        call_id=row.get("toolCallId")
        event_id=f"pi-schema-rejection-{call_id}"
        if event_id in existing:continue
        result=row.get("result") or {}
        parts=result.get("content",[]) if isinstance(result,dict) else []
        diagnostic="\n".join(part.get("text","") for part in parts if isinstance(part,dict) and isinstance(part.get("text"),str))
        start=next((item for item in pi if item.get("type")=="tool_execution_start" and item.get("toolCallId")==call_id),{})
        args=start.get("args") or {}
        revision=min((int(x["revision"]) for x in frames if isinstance(x.get("revision"),int)),default=0)
        failures.append({"event_id":event_id,"event_type":"rejection","revision":revision,
            "session_id":"pi-observed-session","mission_id":"Cycle 18 semantic composition",
            "provenance":"Genuine Pi tool_execution_end schema/argument rejection, normalized for presentation",
            "source_event_ref":call_id,"title":"Pi constructor proposal rejected by tool schema",
            "description":diagnostic or "Pi reported a constructor tool validation error.",
            "preview":{"status":"rejected","function":args.get("name"),"diagnostic":diagnostic,
                "submitted_arguments":args},
            "outcome":{"committed":False,"authoritative_workspace_changed":False,
                "source":"recorded_pi_tool_execution_end"}})
    if not failures:return 0
    # All failed preview calls in this runner precede the accepted preview in
    # the observed Pi chronology. Insert before it; never alter committed
    # snapshots or the original raw event/session records.
    position=next((i for i,row in enumerate(frames) if row.get("event_type")=="preview"),len(frames))
    frames[position:position]=failures
    for seq,row in enumerate(frames,1):row["presentation_sequence"]=seq
    frames_path.write_text("".join(json.dumps(row,ensure_ascii=False,separators=(",",":"))+"\n" for row in frames))
    return len(failures)

def main()->int:
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("campaign_directory",type=Path)
    args=parser.parse_args();print(json.dumps({"derived_schema_rejection_frames":adapt(args.campaign_directory.resolve())}));return 0

if __name__=="__main__":raise SystemExit(main())
