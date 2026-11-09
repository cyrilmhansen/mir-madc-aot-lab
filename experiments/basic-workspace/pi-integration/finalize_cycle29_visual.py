#!/usr/bin/env python3
"""Add host-derived Pi settlement summaries to a completed Cycle 29 replay."""
from __future__ import annotations
import argparse,json,pathlib
import sys
HERE=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from pi_lifecycle import completion_states

def read_rows(path):return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument("campaign",type=pathlib.Path);args=ap.parse_args()
    root=args.campaign.resolve();visual=root/"visual-events.jsonl"
    rows=read_rows(visual);ids={row.get("event_id") for row in rows}
    inserts=[]
    history=read_rows(root/"history.jsonl")
    for phase,session_id,mission_id,revision,anchor in (
        ("A","cycle29-mission-a-create-helper","Mission A · create BASE_SCORE_CLASS",12,"cycle29-mission-boundary"),
        ("B","cycle29-mission-b-replace-block","Mission B · replace SCORE_CLASS block",13,"cycle29-validation-2-13-host")):
        session=root/f"mission-{phase.lower()}";summary=json.loads((session/"session-summary.json").read_text())
        life=summary["lifecycle"];observer=life["observer"]
        event_id=f"cycle29-host-session-outcome-{phase.lower()}"
        process=next(row for row in reversed(read_rows(session/"pi-lifecycle.jsonl")) if row.get("record_type")=="pi_process_exit")
        settled=bool(observer.get("agent_settled_seen"));exit_code=process.get("exit_code");timed_out=bool(process.get("timed_out"))
        validation=json.loads((root/f"mission-{phase.lower()}-host-validation.json").read_text())
        committed=bool(validation.get("mission_complete"))
        denied=any(row.get("event")=="transaction_rejected" and row.get("mission_id")==
            ("cycle29.replace-score-classification-block.v1" if phase=="B" else "cycle29.create-base-score-class.v1") for row in history)
        states=completion_states(committed=committed,validation=validation,timed_out=timed_out,exit_code=exit_code,
            agent_end_seen=bool(observer.get("agent_end_seen")),agent_settled_seen=settled,
            pending_tool_count=process.get("pending_tool_count",0),
            authorization_status="authorized" if committed else "denied" if denied else "not_attempted")
        (root/f"mission-{phase.lower()}-completion-states.json").write_text(json.dumps(states,indent=2)+"\n",encoding="utf-8")
        summary["completion_states"]=states
        (session/"session-summary.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        if event_id in ids:continue
        status="settled" if settled else "timed_out" if timed_out else "exited_without_settlement"
        title=(f"Pi session settled · process exit {exit_code}" if settled and exit_code==0 else
            "Pi session timed out" if timed_out else f"Pi process exited · settlement {status}")
        inserts.append((anchor,{"event_id":event_id,"event_type":"mission_status","revision":revision,
            "session_id":session_id,"mission_id":mission_id,
            "provenance":"Host lifecycle classification from preserved Pi event stream and process-exit record",
            "title":title,"description":f"Pi agent_settled={settled}; process exit={exit_code}; timed_out={timed_out}; pending tools={process.get('pending_tool_count')}.",
            "mission_status":title,"lifecycle":{"state":status,"agent_end_seen":observer.get("agent_end_seen"),
                "agent_settled_seen":settled,"exit_code":exit_code,"timed_out":timed_out,
                "pending_tool_count":process.get("pending_tool_count"),"observed_at_utc":process.get("observed_at_utc")},
            "dependencies":rows[-1].get("dependencies",[]),"source_event_ref":"pi_process_exit"}))
    # Insert the end-state summary before the next checkpoint/validation chapter,
    # preserving the actual mission boundary ordering in the visual-only file.
    for anchor,event in inserts:
        index=next((i for i,row in enumerate(rows) if row.get("event_id")==anchor),len(rows))
        rows.insert(index,event)
    for index,row in enumerate(rows,1):row["presentation_sequence"]=index
    visual.write_text("".join(json.dumps(row,ensure_ascii=False,separators=(",",":"))+"\n" for row in rows),encoding="utf-8")
    campaign_summary=root/"summary.json"
    if campaign_summary.exists():
        summary=json.loads(campaign_summary.read_text())
        for phase in ("a","b"):
            path=root/f"mission-{phase}-completion-states.json"
            if path.exists():summary[f"mission_{phase}_completion_states"]=json.loads(path.read_text())
        campaign_summary.write_text(json.dumps(summary,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    result={"schema":"basic-workspace.cycle29.visual-session-settlement","version":1,
        "source":"preserved Pi lifecycle event streams and process-exit records","inference_performed":False,
        "added_frames":[event for _,event in inserts],"raw_model_transcripts_modified":False}
    (root/"visual-session-settlement.json").write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"added":len(inserts),"events":len(rows)},indent=2))
if __name__=="__main__":main()
