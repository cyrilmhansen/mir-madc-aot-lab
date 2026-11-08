#!/usr/bin/env python3
"""Build a content-free diagnostic timeline from preserved Cycle 18 Pi evidence."""
from __future__ import annotations
import argparse, json
from datetime import datetime, timezone
from pathlib import Path

HERE=Path(__file__).resolve().parent
DEFAULT_SOURCE=HERE/"results/cycle18-composition"
DEFAULT_OUT=HERE/"results/cycle18b-diagnostics"

def iso_ms(value):
    if not isinstance(value,(int,float)): return None
    return datetime.fromtimestamp(value/1000,timezone.utc).isoformat(timespec="milliseconds").replace("+00:00","Z")

def inspect_arm(path:Path,arm:str):
    raw=[json.loads(line) for line in (path/"pi-session.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    summary=json.loads((path/"summary.json").read_text(encoding="utf-8"))
    gateway_rows=[json.loads(line) for line in (path/"gateway-tool-timings.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    rows=[]; open_assistant=0; tool_pending={}; last_usage=None; last_completed_tool=None
    event_counts={}
    last_assistant_start=None; last_assistant_end=None; updates_after_start=0
    for index,event in enumerate(raw):
        typ=event.get("type"); message=event.get("message") if isinstance(event.get("message"),dict) else {}
        event_counts[typ or "unknown"]=event_counts.get(typ or "unknown",0)+1
        role=message.get("role"); stamp=iso_ms(message.get("timestamp"))
        if typ in ("agent_start","turn_start"):
            rows.append({"order":index,"kind":typ,"time":None})
        elif typ=="message_start" and role in ("system","user"):
            rows.append({"order":index,"kind":f"{role}_prompt_message_start","time":stamp})
        elif typ=="message_start" and role=="assistant":
            open_assistant+=1; last_assistant_start=stamp; updates_after_start=0
            rows.append({"order":index,"kind":"assistant_message_start","time":stamp,"stop_reason":message.get("stopReason")})
        elif typ=="message_update" and open_assistant:
            updates_after_start+=1
        elif typ=="message_end" and role=="assistant":
            open_assistant=max(0,open_assistant-1); last_assistant_end=stamp
            usage=message.get("usage")
            if isinstance(usage,dict) and any(isinstance(v,(int,float)) and v for v in usage.values()):
                last_usage={"time":stamp,"usage":{k:usage.get(k) for k in ("input","output","cacheRead","cacheWrite","totalTokens") if k in usage}}
            rows.append({"order":index,"kind":"assistant_message_end","time":stamp,"stop_reason":message.get("stopReason"),"usage_recorded":isinstance(usage,dict)})
        elif typ in ("message_start","message_end") and role=="toolResult":
            texts=[]
            # Do not export tool result text; only record tool-result arrival time.
            if typ=="message_end":
                rows.append({"order":index,"kind":"tool_result_message_end","time":stamp})
        elif typ=="tool_execution_start":
            call=event.get("toolCallId"); name=event.get("toolName")
            if isinstance(call,str): tool_pending[call]=name
            rows.append({"order":index,"kind":"tool_start","time":None,"tool":name,"call_id":call})
        elif typ=="tool_execution_end":
            call=event.get("toolCallId"); name=event.get("toolName")
            if isinstance(call,str): tool_pending.pop(call,None)
            row={"order":index,"kind":"tool_end","time":None,"tool":name,"call_id":call,"is_error":event.get("isError"),"duration_ms":event.get("durationMs")}
            rows.append(row)
            if not event.get("isError"):
                last_completed_tool={"tool":name,"call_id":call,"duration_ms":event.get("durationMs"),"event_order":index}
        elif typ in ("agent_end","agent_settled","turn_end"):
            rows.append({"order":index,"kind":typ,"time":stamp,"stop_reason":message.get("stopReason")})
    timeout_path=path/"pi-timeout.json"
    timeout_record=json.loads(timeout_path.read_text()) if timeout_path.exists() else None
    timeout_time=datetime.fromtimestamp(timeout_path.stat().st_mtime,timezone.utc).isoformat(timespec="milliseconds").replace("+00:00","Z") if timeout_path.exists() else None
    # The final native stream's message_start timestamp records when the open assistant response began.
    if last_assistant_start and timeout_time:
        start=datetime.fromisoformat(last_assistant_start.replace("Z","+00:00")); end=datetime.fromisoformat(timeout_time.replace("Z","+00:00"))
        final_response_elapsed_s=round((end-start).total_seconds(),3)
    else: final_response_elapsed_s=None
    final_assistant_updates=0
    # Count only deltas after the final assistant message_start; preserve no text.
    last_start_i=max((i for i,e in enumerate(raw) if e.get("type")=="message_start" and (e.get("message") or {}).get("role")=="assistant"),default=-1)
    if last_start_i>=0:
        final_assistant_updates=sum(e.get("type")=="message_update" for e in raw[last_start_i+1:])
    end_count=sum(e.get("type")=="message_end" and (e.get("message") or {}).get("role")=="assistant" for e in raw[last_start_i+1:]) if last_start_i>=0 else 0
    turn_end_after=sum(e.get("type")=="turn_end" for e in raw[last_start_i+1:]) if last_start_i>=0 else 0
    agent_end=sum(e.get("type")=="agent_end" for e in raw); settled=sum(e.get("type")=="agent_settled" for e in raw)
    last_tool_result=next((r["time"] for r in reversed(rows) if r["kind"]=="tool_result_message_end" and r.get("time")),None)
    gap=None
    if last_tool_result and timeout_time:
        gap=round((datetime.fromisoformat(timeout_time.replace("Z","+00:00"))-datetime.fromisoformat(last_tool_result.replace("Z","+00:00"))).total_seconds(),3)
    validation=summary.get("validation")
    authorization=("authorized" if summary.get("accepted_previews",0)>0 else
        "denied" if summary.get("policy_rejections",0)>0 else "not_attempted")
    completion={"semantic_program":"passed" if validation and validation.get("mission_complete") else ("failed" if validation else "not_validated"),
        "mission_authorization":authorization,"program_commit":"committed" if summary.get("committed") else "not_committed",
        "host_validation":"passed" if validation and validation.get("mission_complete") else ("failed" if validation else "not_run"),
        "pi_agent_session":"completed" if settled else "ended_not_settled" if agent_end else "incomplete_or_unobserved",
        "launcher_process":"timed_out" if summary.get("timed_out") else "exited_normally" if summary.get("pi_exit_code")==0 else "unknown"}
    return {"arm":arm,"campaign_path":str(path.relative_to(HERE.parents[1])),"provider":summary.get("provider"),"model":summary.get("model"),
      "recorded_events":len(raw),"session_event_first_time":next((iso_ms((e.get("message") or {}).get("timestamp")) for e in raw if e.get("type")=="message_start"),None),
      "event_counts":event_counts,"message_start_count":event_counts.get("message_start",0),"message_end_count":event_counts.get("message_end",0),
      "assistant_message_start_count":sum(e.get("type")=="message_start" and (e.get("message") or {}).get("role")=="assistant" for e in raw),
      "assistant_message_end_count":sum(e.get("type")=="message_end" and (e.get("message") or {}).get("role")=="assistant" for e in raw),
      "turn_start_count":event_counts.get("turn_start",0),"turn_end_count":event_counts.get("turn_end",0),
      "model_prompt_message_time":next((iso_ms((e.get("message") or {}).get("timestamp")) for e in raw if e.get("type")=="message_start" and (e.get("message") or {}).get("role")=="user"),None),
      "timeout_recorded_at_file_mtime":timeout_time,"timeout_seconds":summary.get("session_timeout_seconds"),"process_wall_ms":summary.get("inference_and_process_wall_ms"),
      "last_successful_tool":last_completed_tool,"last_tool_result_message_time":last_tool_result,"elapsed_last_tool_result_to_timeout_seconds":gap,
      "final_assistant_message_started_at":last_assistant_start,"final_assistant_message_ended":bool(end_count),"final_assistant_turn_ended":bool(turn_end_after),
      "final_assistant_update_event_count_after_start":final_assistant_updates,"assistant_stream_open_at_cutoff":open_assistant>0,
      "pending_tool_calls_at_cutoff":tool_pending,"agent_end_events":agent_end,"agent_settled_events":settled,
      "last_completed_provider_usage":last_usage,"usage_for_open_final_generation":None,
      "gateway_operations_by_tool_call_id":[{"tool_call_id":r.get("tool_call_id"),"method":r.get("method"),"elapsed_ms":r.get("elapsed_ms"),"observed_at":None} for r in gateway_rows if r.get("agent_tool")],
      "unavailable_timestamp_boundaries":["Pi process start","individual Pi tool start/end receipt","gateway request/response receipt","message_update delta arrival in historical trace","native process termination"],
      "gateway_processing_ms":summary.get("gateway_tool_processing_ms"),"workspace_revision":summary.get("workspace_revision"),
      "committed":summary.get("committed"),"host_mission_validation":bool((summary.get("validation") or {}).get("mission_complete")),
      "completion_states":completion,
      "pi_exit_code":summary.get("pi_exit_code"),"timed_out":summary.get("timed_out"),"timeline":rows}

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--source",type=Path,default=DEFAULT_SOURCE);ap.add_argument("--output",type=Path,default=DEFAULT_OUT);args=ap.parse_args()
    arms=[inspect_arm(args.source/"arm-a-atomic","atomic"),inspect_arm(args.source/"arm-b-incremental","incremental")]
    args.output.mkdir(parents=True,exist_ok=True)
    data={"schema":"basic-workspace.pi-stall-diagnostic","version":1,"evidence_kind":"offline analysis of preserved genuine Cycle 18 Pi sessions","arms":arms,
      "limitations":["Historical native Pi JSON events do not timestamp each message_update delta or tool_execution_start/end event.","The open final assistant message has no message_end/turn_end/agent_end; final provider usage is therefore unavailable.","These records cannot distinguish slow token generation from an upstream/provider wait or Pi stream handling delay.","The timeout JSON file mtime is the host's timeout-record write time, not a native Pi process-exit timestamp."]}
    (args.output/"timelines.json").write_text(json.dumps(data,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"output":str(args.output/"timelines.json"),"arms":[{k:a[k] for k in ("arm","last_successful_tool","elapsed_last_tool_result_to_timeout_seconds","assistant_stream_open_at_cutoff","pending_tool_calls_at_cutoff","agent_end_events","last_completed_provider_usage","host_mission_validation")} for a in arms]},indent=2))
if __name__=="__main__":main()
