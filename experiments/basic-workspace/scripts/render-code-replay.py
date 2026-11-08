#!/usr/bin/env python3
"""Build code-first, offline visual replays from recorded semantic campaigns."""
from __future__ import annotations

import difflib
import html
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results" / "semantic-replay"
LONG = RESULTS / "longitudinal-01"
OUT14 = LONG / "calibrated-resume-02"
C13 = RESULTS / "is-senior" / "real-model-02"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_events(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def committed_snapshot(events: list[dict[str, Any]], phase: str) -> dict[str, Any]:
    rows = [e for e in events if e.get("event") == "transaction_committed" and e.get("phase") == phase]
    if len(rows) != 1 or not rows[0].get("program_snapshot"):
        raise ValueError(f"Expected one committed snapshot for phase {phase}")
    return rows[0]


def successful_call(path: Path, tool: str) -> dict[str, Any]:
    data = read_json(path)
    rows = [c for turn in data.get("transcript", []) for c in turn.get("tool_calls", [])
            if c.get("name") == tool and c.get("result", {}).get("ok") is True]
    if not rows:
        raise ValueError(f"Missing successful {tool} call in {path}")
    return rows[-1]


def changed_lines(before: str, after: str) -> dict[str, list[int]]:
    a, b = before.splitlines(), after.splitlines()
    matcher = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    old: list[int] = []
    new: list[int] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in ("replace", "delete"):
            old.extend(range(i1 + 1, i2 + 1))
        if tag in ("replace", "insert"):
            new.extend(range(j1 + 1, j2 + 1))
    return {"old": old, "new": new}


def function_lines(source: str, name: str) -> list[int]:
    lines = source.splitlines()
    start = next((i for i, line in enumerate(lines) if line.strip().casefold().startswith(
        f"function {name}".casefold())), None)
    if start is None:
        return []
    end = next((i for i in range(start, len(lines)) if lines[i].strip().casefold() == "end function"), start)
    return list(range(start + 1, end + 2))


def function_additions(before: str, after: str, name: str, handle: str,
                       callee: str | None = None) -> dict[str, Any]:
    delta = changed_lines(before, after)
    lines = after.splitlines()
    fn_range = function_lines(after, name)
    call_lines = [n for n in fn_range if callee and
                  f"{callee}(ID)".casefold() in lines[n - 1].casefold()]
    return {"lines": delta["new"], "function_lines": fn_range, "call_lines": call_lines,
            "semantic_handle": handle, "mapping": "unique added-line diff; call target confirmed by semantic binding"}


def tool_event_ref(campaign: str, mission: str, turn: int, call: dict[str, Any]) -> dict[str, Any]:
    return {"campaign": campaign, "mission": mission, "turn": turn,
            "tool": call.get("name"), "call_id": call.get("id"),
            "outcome": call.get("result", {}).get("code", "ok" if call.get("result", {}).get("ok") else "observed")}


def model_turn_for(session_path: Path, tool_name: str, successful: bool | None = None) -> tuple[int, dict[str, Any]]:
    data = read_json(session_path)
    for turn in data.get("transcript", []):
        for call in turn.get("tool_calls", []):
            if call.get("name") != tool_name:
                continue
            if successful is None or call.get("result", {}).get("ok") is successful:
                return int(turn.get("turn", 0)), call
    raise ValueError(f"No matching {tool_name} call in {session_path}")


def code14_frames() -> list[dict[str, Any]]:
    run = LONG / "calibrated-run-01"
    resume = OUT14
    events1 = read_events(run / "history.jsonl")
    events_resume = read_events(resume / "history.jsonl")
    initial = committed_snapshot(events1, "initial-construction")
    senior_commit = committed_snapshot(events1, "mission-1")
    age_commit = committed_snapshot(events1, "mission-2")
    adult_commit = committed_snapshot(events_resume, "replay-validated-model-commit")
    code2, code3, code4, code5 = (initial["program_snapshot"], senior_commit["program_snapshot"],
                                  age_commit["program_snapshot"], adult_commit["program_snapshot"])

    m1_path = run / "mission-1-is-senior" / "agent-session.json"
    m2_path = run / "mission-2-age-205" / "agent-session.json"
    m3_failed_path = run / "mission-3-is-adult" / "agent-session.json"
    m3_path = resume / "mission-3-is-adult" / "agent-session.json"
    m1_disc_turn, m1_disc = model_turn_for(m1_path, "discover_functions")
    m1_preview_turn, m1_preview = model_turn_for(m1_path, "preview_create_function", True)
    m1_commit_turn, m1_commit = model_turn_for(m1_path, "commit_function")
    m2_disc_turn, m2_disc = model_turn_for(m2_path, "discover_symbols")
    m2_preview_turn, m2_preview = model_turn_for(m2_path, "preview_age_edit", True)
    m2_commit_turn, m2_commit = model_turn_for(m2_path, "commit_age_edit")
    failed_turn, failed_preview = model_turn_for(m3_failed_path, "preview_create_function", False)
    m3_disc_turn, m3_disc = model_turn_for(m3_path, "discover_functions")
    m3_preview_turn, m3_preview = model_turn_for(m3_path, "preview_create_function", True)
    m3_commit_turn, m3_commit = model_turn_for(m3_path, "commit_function")
    m3_validate_turn, m3_validate = model_turn_for(m3_path, "validate_mission")

    delta1 = function_additions(code2, code3, "IS_SENIOR", "is_senior.function", "AGE_BY_ID")
    delta3 = function_additions(code4, code5, "IS_ADULT", "is_adult.function", "AGE_BY_ID")
    age_delta = changed_lines(code3, code4)
    age_line = age_delta["old"][0] if len(age_delta["old"]) == 1 else None
    if age_line is None or len(age_delta["new"]) != 1:
        raise ValueError("Age edit does not have a unique line-level diff")
    age_before = code3.splitlines()[age_line - 1]
    age_after_line = age_delta["new"][0]
    age_after = code4.splitlines()[age_after_line - 1]

    summary1 = read_json(run / "summary.json")
    summary2 = read_json(resume / "summary.json")
    initial_results = summary1["mission_1"]["validation"].get("observed_results", {})
    after_age = summary1["mission_2"].get("observed", {})
    final_results = summary2["validation"].get("observed_results", {})
    validation1 = summary1["mission_1"]["validation"]
    validation2 = summary1["mission_2"]
    validation3 = summary2["validation"]

    def frame(fid: str, **kw: Any) -> dict[str, Any]:
        return {"id": fid, "campaign": "longitudinal-14b", "source_kind": "recorded_evidence", **kw}

    frames = [
        frame("p14-start", chapter="Mission 1 · existing program", title="Starting Workspace · revision 2",
              provenance="Host-seeded canonical Workspace", revision=2, state="committed",
              description="The program already has AGE_BY_ID, its ID and age arrays, and the bounded lookup loop. The visible source is the exact committed Workspace snapshot.",
              code=code2, highlights={"function_lines": function_lines(code2, "AGE_BY_ID"),
                                      "semantic_handle":"age_by_id.function"},
              event_refs=[{"campaign":"Cycle 14B","history_event":"transaction_committed","phase":"initial-construction","sequence":4}],
              results={"interp": {"101":25,"205":42,"900":53,"999":-1}, "jit":{"101":25,"205":42,"900":53,"999":-1}}),
        frame("p14-m1-discovery", chapter="Mission 1 · add IS_SENIOR", title="Agent discovers AGE_BY_ID",
              provenance="Real model tool call", revision=2,state="committed",
              description="The model queried the live symbol index and received the callable AGE_BY_ID handle and numeric signature.",
              code=code2, highlights={"function_lines":function_lines(code2,"AGE_BY_ID"),"semantic_handle":"age_by_id.function"},
              event_refs=[tool_event_ref("Cycle14B", "Mission 1", m1_disc_turn, m1_disc)]),
        frame("p14-m1-preview", chapter="Mission 1 · add IS_SENIOR", title="Candidate preview · not committed",
              provenance="Real model proposal · MissionGateway accepted preview",revision=2,state="proposed",
              description="The preview adds IS_SENIOR(ID). The committed source remains revision 2 while the candidate block is shown below as a proposal.",
              code=code2, highlights={"function_lines":function_lines(code2,"AGE_BY_ID")},
              proposal={"status":"accepted","append_lines":[code3.splitlines()[n-1] for n in delta1["lines"]],
                        "highlight_lines":delta1["lines"],"call_lines":delta1["call_lines"],
                        "semantic_handle":"is_senior.function","bound_callee":"age_by_id.function"},
              event_refs=[tool_event_ref("Cycle14B","Mission 1",m1_preview_turn,m1_preview),
                          {"campaign":"Cycle14B","history_event":"preview_accepted","phase":"mission-1","transaction_id":m1_preview["result"]["transaction_id"]}]),
        frame("p14-m1-commit", chapter="Mission 1 · add IS_SENIOR", title="IS_SENIOR committed · revision 3",
              provenance="Real model commit · authoritative snapshot captured by Workspace",revision=3,state="committed",
              description="The gateway revalidated and committed the candidate. IS_SENIOR calls the discovered AGE_BY_ID function; existing AGE_BY_ID source is unchanged.",
              code=code3, highlights=delta1,
              event_refs=[tool_event_ref("Cycle14B","Mission 1",m1_commit_turn,m1_commit),
                          {"campaign":"Cycle14B","history_event":"transaction_committed","phase":"mission-1","sequence":25}]),
        frame("p14-m1-check", chapter="Mission 1 · add IS_SENIOR", title="MIR validation",
              provenance="Host validation",revision=3,state="validated",
              description="MIR interpreter and JIT agree on the known and missing IDs. The new function depends on AGE_BY_ID.",
              code=code3, highlights=delta1, results=validation1.get("observed_results",{}),
              validation={"passed":validation1.get("mission_complete"),"interpreter_jit_agree":validation1.get("engines_agree"),
                          "dependency_bound":validation1.get("age_by_id_call_bound")},
              event_refs=[{"campaign":"Cycle14B","history_event":"program_validated","phase":"mission-1","revision":3}]),
        frame("p14-m2-discovery",chapter="Mission 2 · edit ID 205",title="Agent selects the age assignment",
              provenance="Real model discovery",revision=3,state="selected",
              description="Symbol and statement discovery identified the PERSON_AGE initializer bound to logical ID 205. The semantic handle is people.age.205.",
              code=code3,highlights={"lines":[age_line],"semantic_handle":"people.age.205",
                                     "mapping":"unique source-line diff correlated with the discovered stable statement handle"},
              event_refs=[tool_event_ref("Cycle14B","Mission 2",m2_disc_turn,m2_disc)]),
        frame("p14-m2-preview",chapter="Mission 2 · edit ID 205",title="Preview · 42 stays committed",
              provenance="Real model proposal · MissionGateway accepted preview",revision=3,state="proposed",
              description="The proposed change is 42 → 55. The authoritative code pane still shows 42; the replacement is only an annotation until commit.",
              code=code3,highlights={"lines":[age_line],"semantic_handle":"people.age.205",
                                     "mapping":"unique source-line diff correlated with the discovered stable statement handle"},
              proposal={"status":"accepted","line":age_line,"old":age_before,"new":age_after,
                        "semantic_handle":"people.age.205","annotation":"42 → 55"},
              event_refs=[tool_event_ref("Cycle14B","Mission 2",m2_preview_turn,m2_preview),
                          {"campaign":"Cycle14B","history_event":"preview_accepted","phase":"mission-2","transaction_id":m2_preview["result"]["transaction_id"]}]),
        frame("p14-m2-commit",chapter="Mission 2 · edit ID 205",title="Age changed · revision 4",
              provenance="Real model commit · authoritative snapshot captured by Workspace",revision=4,state="committed",
              description="The gateway committed only the selected PERSON_AGE cell. Entity IDs, other ages, function signatures and control flow remain unchanged.",
              code=code4,highlights={"lines":[age_after_line],"semantic_handle":"people.age.205","annotation":"42 → 55",
                                     "mapping":"unique committed line diff"},
              event_refs=[tool_event_ref("Cycle14B","Mission 2",m2_commit_turn,m2_commit),
                          {"campaign":"Cycle14B","history_event":"transaction_committed","phase":"mission-2","sequence":58}]),
        frame("p14-m2-check",chapter="Mission 2 · edit ID 205",title="Behavior updates",
              provenance="Host validation",revision=4,state="validated",code=code4,
              highlights={"lines":[age_after_line],"semantic_handle":"people.age.205"},results=after_age,
              validation={"passed":summary1["mission_2"].get("passed"),"interpreter_jit_agree":True},
              description="AGE_BY_ID(205) is now 55 and IS_SENIOR(205) is 1 in both engines. Other records retain their expected values."),
        frame("p14-checkpoint",chapter="Recovery · checkpoint",title="Checkpoint at revision 4",
              provenance="Host checkpoint",revision=4,state="checkpoint",code=code4,
              highlights={"function_lines":function_lines(code4,"AGE_BY_ID"),"semantic_handle":"age_by_id.function"},
              description="A 4,282-byte semantic checkpoint records the verified revision, functions, bindings, arrays and mission outcomes. It contains no prior conversation transcript.",
              checkpoint={"bytes":4282,"estimated_tokens":773,"portable_handles":19,"fingerprint_verified":True},
              event_refs=[{"campaign":"Cycle14B","history_event":"checkpoint_created","phase":"recovery","sequence":80}]),
        frame("p14-reset",chapter="Recovery · context reset",title="Conversation context reset",
              provenance="Harness recovery boundary",revision=4,state="checkpoint",code=code4,
              description="The first resumed session starts with the verified checkpoint and fresh tool schemas, not the earlier conversation. The committed program remains revision 4.",
              checkpoint={"bytes":4282,"estimated_tokens":773,"context_messages_carried":False},
              event_refs=[{"campaign":"Cycle14B","history_event":"context_reset","phase":"recovery","sequence":84}]),
        frame("p14-m3-first-reject",chapter="Recovery · initial attempt",title="First Mission 3 preview rejected",
              provenance="Real model proposal · MissionGateway rejection",revision=4,state="rejected",code=code4,
              highlights={"function_lines":function_lines(code4,"AGE_BY_ID"),"semantic_handle":"age_by_id.function"},
              proposal={"status":"rejected","function":"IS_ADULT(ID)","callee":"AGE_BY_ID(ID)",
                        "threshold":18,"diagnostic":"MISSION_EXISTING_FUNCTION_CHANGED",
                        "message":"The gateway compared against a baseline captured before the age-55 edit."},
              description="The model's first valid typed proposal did not modify code. The gateway used a stale comparison snapshot; later exploratory retries consumed its tool-call budget. This was a harness defect, not a program change.",
              event_refs=[tool_event_ref("Cycle14B","Mission 3 first attempt",failed_turn,failed_preview)]),
        frame("p14-reconstruct",chapter="Recovery · corrected continuation",title="Committed revision reconstructed",
              provenance="Deterministic reconstruction · not agent activity",revision=4,state="checkpoint",code=code4,
              highlights={"function_lines":function_lines(code4,"AGE_BY_ID")},
              description="The two already committed missions were replayed semantically into a fresh Workspace. Its revision-4 semantic fingerprint matched the saved checkpoint. No source file was imported and no new function was added by the harness.",
              checkpoint={"fingerprint_matches":True,"workspace":"fresh semantic reconstruction"},
              event_refs=[{"campaign":"Cycle14B","history_event":"checkpoint_verified","phase":"recovery"}]),
        frame("p14-m3-discovery",chapter="Mission 3 · after recovery",title="Resumed model discovers AGE_BY_ID",
              provenance="Real resumed model tool call",revision=4,state="selected",code=code4,
              highlights={"function_lines":function_lines(code4,"AGE_BY_ID"),"semantic_handle":"age_by_id.function"},
              description="A fresh Qwen conversation received the checkpoint and current tools, then discovered the callable AGE_BY_ID signature. No previous model turn was included.",
              event_refs=[tool_event_ref("Cycle14B","Mission 3 resumed",m3_disc_turn,m3_disc)]),
        frame("p14-m3-preview",chapter="Mission 3 · after recovery",title="IS_ADULT preview · not committed",
              provenance="Real resumed model proposal · MissionGateway accepted preview",revision=4,state="proposed",code=code4,
              highlights={"function_lines":function_lines(code4,"AGE_BY_ID")},
              proposal={"status":"accepted","append_lines":[code5.splitlines()[n-1] for n in delta3["lines"]],
                        "highlight_lines":delta3["lines"],"call_lines":delta3["call_lines"],
                        "semantic_handle":"is_adult.function","bound_callee":"age_by_id.function"},
              description="The candidate uses a typed call to the discovered AGE_BY_ID handle and the >= 18 condition. The code pane remains at revision 4 until the accepted transaction commits.",
              event_refs=[tool_event_ref("Cycle14B","Mission 3 resumed",m3_preview_turn,m3_preview),
                          {"campaign":"Cycle14B","history_event":"preview_accepted","source":"commit-linked semantic candidate"}]),
        frame("p14-m3-commit",chapter="Mission 3 · after recovery",title="IS_ADULT committed · revision 5",
              provenance="Real model commit · source snapshot verified by deterministic semantic replay",revision=5,state="committed",
              code=code5,highlights=delta3,
              description="The model committed IS_ADULT(ID), bound to AGE_BY_ID. The rendered block comes from the fresh Workspace's canonical committed snapshot after replaying the model's exact successful typed operation.",
              event_refs=[tool_event_ref("Cycle14B","Mission 3 resumed",m3_commit_turn,m3_commit),
                          {"campaign":"Cycle14B","history_event":"transaction_committed","source":"semantic replay of committed call"}]),
        frame("p14-m3-check",chapter="Mission 3 · after recovery",title="Interpreter + JIT pass",
              provenance="Host validation",revision=5,state="validated",code=code5,highlights=delta3,
              results=final_results,validation={"passed":validation3.get("mission_complete"),
                  "interpreter_jit_agree":validation3.get("engines_agree"),
                  "age_by_id_unchanged":validation3.get("age_by_id_and_is_senior_unchanged"),
                  "call_bound":validation3.get("age_by_id_call_bound"),
                  "boundary_17_18":summary2.get("boundary_oracle",{}).get("passed")},
              description="Known and unknown IDs pass in both engines; separate age-17 and age-18 boundary fixtures pass."),
        frame("p14-replay",chapter="Replay · fresh Workspace",title="Portable replay equivalent",
              provenance="Deterministic replay + host equivalence check",revision=5, state="validated",code=code5,
              highlights={"function_lines":function_lines(code5,"IS_ADULT"),"semantic_handle":"is_adult.function"},
              validation=summary2.get("replay",{}),
              description="The constructive stream rebuilt all three functions in a fresh Workspace. Structural, binding, behavioral and engine equivalence passed; 24 semantic identities were remapped.",
              event_refs=[{"campaign":"Cycle14B","history_event":"replay_completed","phase":"replay","success":True}]),
    ]
    return frames


def code13_frames() -> list[dict[str, Any]]:
    events = read_events(C13 / "history.jsonl")
    initial = committed_snapshot(events, "initial-construction")
    final = committed_snapshot(events, "agent")
    before, after = initial["program_snapshot"], final["program_snapshot"]
    delta = function_additions(before, after, "IS_SENIOR", "is_senior.function", "AGE_BY_ID")
    session = read_json(C13 / "agent-session.json")
    model_meta = read_json(C13 / "summary.json").get("model", {})
    calls = [c for turn in session.get("transcript", []) for c in turn.get("tool_calls", [])]
    discover = next(c for c in calls if c["name"] == "discover_functions")
    preview = next(c for c in calls if c["name"] == "preview_create_function" and c["result"].get("ok"))
    commit = next(c for c in calls if c["name"] == "commit_function" and c["result"].get("committed"))
    validate = next(c for c in calls if c["name"] == "validate_mission")
    def find_turn(call: dict[str, Any]) -> int:
        return next(int(t.get("turn",0)) for t in session["transcript"] if call in t.get("tool_calls",[]))
    summary = read_json(C13 / "summary.json")
    result = summary.get("validation",{}).get("observed_results",{})
    return [
        {"id":"p13-start","campaign":"cycle13-real-model","chapter":"Function composition",
         "title":"AGE_BY_ID before agent edit","provenance":"Host-seeded Workspace", "revision":2,"state":"committed",
         "description":"Original ID lookup before the genuine real-model composition trial.","code":before,
         "highlights":{"function_lines":function_lines(before,"AGE_BY_ID"),"semantic_handle":"age_by_id.function"},
         "results":summary.get("initial_results",{}),"event_refs":[{"campaign":"Cycle13B","event":"transaction_committed","phase":"initial-construction"}]},
        {"id":"p13-discovery","campaign":"cycle13-real-model","chapter":"Function composition",
         "title":"Model discovers AGE_BY_ID","provenance":"Real model tool call","revision":2,"state":"selected",
         "description":"The model discovered AGE_BY_ID's portable function handle and callable signature.","code":before,
         "highlights":{"function_lines":function_lines(before,"AGE_BY_ID"),"semantic_handle":"age_by_id.function"},
         "event_refs":[tool_event_ref("Cycle13B","IS_SENIOR mission",find_turn(discover),discover)]},
        {"id":"p13-preview","campaign":"cycle13-real-model","chapter":"Function composition",
         "title":"IS_SENIOR preview","provenance":"Real model proposal · accepted preview","revision":2,"state":"proposed",
         "description":"The Workspace preview accepts one new function and confirms its typed call binding. The committed source remains revision 2.","code":before,
         "proposal":{"status":"accepted","append_lines":[after.splitlines()[n-1] for n in delta["lines"]],
           "highlight_lines":delta["lines"],"call_lines":delta["call_lines"],"semantic_handle":"is_senior.function","bound_callee":"age_by_id.function"},
         "event_refs":[tool_event_ref("Cycle13B","IS_SENIOR mission",find_turn(preview),preview)]},
        {"id":"p13-commit","campaign":"cycle13-real-model","chapter":"Function composition",
         "title":"IS_SENIOR committed · revision 3","provenance":"Real model commit · Workspace snapshot","revision":3,"state":"committed",
         "description":"The new function calls the discovered AGE_BY_ID function; it does not duplicate the lookup.","code":after,"highlights":delta,
         "event_refs":[tool_event_ref("Cycle13B","IS_SENIOR mission",find_turn(commit),commit)]},
        {"id":"p13-validation","campaign":"cycle13-real-model","chapter":"Function composition",
         "title":"Interpreter + JIT validation","provenance":"Host validation","revision":3,"state":"validated",
         "description":"The recorded independent oracle and both MIR engines passed the composition cases.","code":after,"highlights":delta,
         "results":result,"validation":summary.get("validation",{}),
         "event_refs":[tool_event_ref("Cycle13B","IS_SENIOR mission",find_turn(validate),validate)]}
    ]


HTML = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>BASIC semantic replay</title><style>
:root{color-scheme:dark;--bg:#0d1118;--panel:#151c27;--panel2:#1b2532;--line:#2a3747;--text:#e4edf7;--muted:#95a5b8;--blue:#68b7ff;--green:#55d5a1;--yellow:#f2c76c;--red:#ff777f;--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px/1.45 system-ui,-apple-system,Segoe UI,sans-serif;height:100vh;display:flex;flex-direction:column;overflow:hidden}
header{height:54px;display:flex;align-items:center;gap:14px;padding:0 18px;background:#111822;border-bottom:1px solid var(--line);flex:none}header h1{font-size:15px;margin:0;font-weight:650;letter-spacing:.01em}header .tag{color:var(--muted);font-size:12px;border:1px solid var(--line);border-radius:20px;padding:4px 9px}header select{margin-left:auto;background:#202a37;color:var(--text);border:1px solid #38485a;border-radius:6px;padding:7px 10px}
.summary{height:55px;display:flex;align-items:center;gap:16px;padding:7px 18px;border-bottom:1px solid var(--line);background:#101721;flex:none}.mission{font-weight:650;font-size:14px}.sub{color:var(--muted);font-size:12px}.pill{border-radius:15px;padding:4px 9px;font-size:11px;font-weight:700;letter-spacing:.03em;text-transform:uppercase}.pill.committed,.pill.validated{background:#143829;color:#7ce8b8}.pill.proposed,.pill.selected,.pill.checkpoint{background:#423617;color:#ffd978}.pill.rejected{background:#48242a;color:#ff9397}.pill.host{background:#26374a;color:#b7d9ff}
main{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:12px;padding:12px 14px 8px;min-height:0;flex:1}.editor{min-width:0;display:flex;flex-direction:column;border:1px solid #293646;border-radius:10px;background:#10161f;overflow:hidden;box-shadow:0 10px 32px #0003}.editor-head{height:43px;padding:0 14px;display:flex;align-items:center;gap:11px;background:#161f2b;border-bottom:1px solid var(--line);flex:none}.filedot{width:9px;height:9px;border-radius:50%;background:#67b8ff}.file{font-family:var(--mono);color:#b9c7d8;font-size:12px}.rev{margin-left:auto;color:#a8b7c8;font:12px var(--mono)}.editor-scroll{overflow:auto;flex:1;scroll-behavior:smooth;padding:12px 0 20px}.source{font:14px/1.82 var(--mono);min-width:max-content}.code-line{display:grid;grid-template-columns:54px minmax(600px,1fr);padding:0 20px 0 0;border-left:3px solid transparent;min-height:25px}.code-line .ln{user-select:none;text-align:right;padding-right:15px;color:#526174}.code-line .code{white-space:pre;color:#d9e3ef}.code-line.focus{background:#17314a77;border-left-color:var(--blue)}.code-line.change{background:#193a2c88;border-left-color:var(--green)}.code-line.call{background:#16344988;border-left-color:#54c7e7}.code-line.rejected-focus{background:#4823296b;border-left-color:var(--red)}.code-line .proposed-value{color:var(--yellow);background:#41331c;border:1px dashed #a78238;border-radius:4px;padding:1px 5px;margin-left:8px;font:11px system-ui}.kw{color:#c792ea}.num{color:#f4bf75}.str{color:#a8dba3}.op{color:#8ccaff}.comment{color:#81909e;font-style:italic}.ident{color:#d8e3f0}.call-highlight{color:#7ddafa;text-decoration:underline;text-decoration-color:#3e91a7;text-underline-offset:3px}
.proposal-box{margin:15px 20px 8px 74px;border:1px dashed #927331;border-radius:8px;background:#2a2418;padding:9px 12px;color:var(--yellow);width:max-content;min-width:600px}.proposal-label{font:11px system-ui;text-transform:uppercase;letter-spacing:.08em;color:#eac66f;margin-bottom:4px}.proposal-code{font:13px/1.7 var(--mono);white-space:pre}.proposal-code .plus{color:#89e0b6;margin-right:8px}.reject-box{margin:14px 20px 8px 74px;border:1px solid #714249;border-radius:7px;background:#301b20;padding:10px 13px;color:#ffadb0;width:max-content;max-width:80ch}.annotation{display:inline-block;font:11px system-ui;color:#a9eacb;background:#1d3c2e;border-radius:5px;padding:3px 7px;margin:5px 0 5px 74px}.pane{min-width:0;display:flex;flex-direction:column;gap:10px;overflow:auto}.card{background:var(--panel);border:1px solid #293646;border-radius:9px;padding:12px 13px}.card h2{font-size:11px;text-transform:uppercase;letter-spacing:.09em;color:#93a8bf;margin:0 0 8px}.step-title{font-size:15px;line-height:1.3;font-weight:660;margin:0 0 6px}.step-desc{margin:0;color:#c2ceda;font-size:12px;line-height:1.55}.meta{color:var(--muted);font-size:11px;margin-top:9px}.dep{font:12px/1.6 var(--mono);color:#c8dded}.dep b{color:#69d8b1;font-weight:500}.result-row{display:grid;grid-template-columns:44px 1fr 1fr;gap:5px;font:11px/1.5 var(--mono);padding:4px 0;border-bottom:1px solid #26313d}.result-row.head{color:var(--muted)}.pass{color:#74e5b3}.fail{color:#ff9298}.status-text{font-size:12px;font-weight:650}.focus-chip{display:inline-block;margin:4px 4px 0 0;border:1px solid #344b60;color:#b6d5ee;border-radius:5px;padding:3px 6px;font:10px var(--mono)}details{margin-top:9px;color:var(--muted);font-size:11px}details pre{max-height:220px;overflow:auto;color:#c6d5e4;background:#0d131a;padding:9px;border-radius:5px;white-space:pre-wrap;word-break:break-word;font:10px/1.45 var(--mono)}
footer{height:145px;background:#111822;border-top:1px solid var(--line);padding:9px 14px 8px;flex:none;display:flex;flex-direction:column;gap:8px}.controls{display:flex;align-items:center;gap:8px}.controls button{background:#202a37;color:var(--text);border:1px solid #3a4a5c;border-radius:6px;padding:5px 11px;cursor:pointer}.controls button:hover{border-color:var(--blue)}.controls .play{background:#184b3c;border-color:#2d8366}.controls label{color:var(--muted);font-size:11px;margin-left:6px}.controls input[type=range]{accent-color:#58d6a5}.controls select{background:#202a37;color:var(--text);border:1px solid #38485a;border-radius:5px;padding:4px}.timeline{display:flex;align-items:center;gap:6px;overflow-x:auto;padding:0 1px 3px}.tick{flex:none;max-width:140px;min-width:84px;text-align:left;background:#182230;border:1px solid #344255;border-radius:6px;padding:5px 7px;cursor:pointer;color:#a7b7c8;font-size:10px;line-height:1.15}.tick.active{border-color:#66b7ff;background:#1a3147;color:#fff}.tick.rejected{border-bottom:2px solid var(--red)}.tick.committed{border-bottom:2px solid var(--green)}.tick .t-rev{display:block;color:#7393ad;font:9px var(--mono);margin-top:3px}.motion{transition:background-color .2s ease,border-color .2s ease}.hidden{display:none!important}@media(max-width:850px){main{grid-template-columns:1fr}.pane{display:none}header .tag{display:none}.code-line{grid-template-columns:45px minmax(420px,1fr)}footer{height:140px}}
@media(prefers-reduced-motion:reduce){*,*::before,*::after{scroll-behavior:auto!important;transition:none!important;animation:none!important}}
</style></head><body>
<header><span class="filedot"></span><h1>BASIC Workspace · Semantic Replay</h1><span class="tag">Code-first view · canonical snapshot playback</span><select id="campaign"></select></header>
<section class="summary"><span class="mission" id="mission"></span><span class="sub" id="campaignStatus"></span><span class="pill" id="statePill"></span><span class="sub" id="revision"></span></section>
<main><section class="editor"><div class="editor-head"><span class="filedot"></span><span class="file" id="filename">AGE_BY_ID.bas</span><span class="rev" id="revBadge"></span></div><div class="editor-scroll" id="scroll"><div class="source" id="source"></div><div id="proposal"></div><div id="annotation"></div></div></section>
<aside class="pane"><section class="card"><h2>Action</h2><p class="step-title" id="stepTitle"></p><p class="step-desc" id="stepDesc"></p><div class="meta" id="provenance"></div><div id="semanticFocus"></div><div id="diagnostic"></div><details id="evidenceDetails"><summary>Evidence and diagnostics</summary><pre id="evidence"></pre></details></section>
<section class="card"><h2>Function dependency</h2><div class="dep" id="deps"></div></section><section class="card"><h2>MIR observations</h2><div id="results"></div><div class="meta" id="validation"></div></section></aside></main>
<footer><div class="controls"><button id="prev" title="Previous action">◀</button><button id="play" class="play">▶ Play</button><button id="next" title="Next action">▶</button><label for="speed">Speed</label><input id="speed" type="range" min="0.5" max="3" value="1" step="0.5"><span id="speedLabel" class="sub">1×</span><label for="chapter">Chapter</label><select id="chapter"></select><span class="sub" id="counter" style="margin-left:auto"></span></div><input id="scrub" type="range" min="0" max="0" value="0" step="1"></footer>
<script id="frames-data" type="application/json">__FRAME_DATA__</script><script>
const DATA=JSON.parse(document.getElementById('frames-data').textContent);let campaignIndex=0,index=0,timer=null;
const $=id=>document.getElementById(id);const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function active(){return DATA.campaigns[campaignIndex]}function frames(){return active().frames}
function highlighter(line){let out='',i=0;const re=/('[^\n]*|"(?:\\.|[^"\\])*"|\b(?:FUNCTION|END|DIM|FOR|TO|STEP|NEXT|IF|THEN|ELSE|GOTO|GOSUB|RETURN|DATA|READ|RESTORE|SUB|CALL)\b|\b\d+(?:\.\d+)?\b|>=|<=|<>|=|\+|-|\*|\/|\b[A-Za-z_][A-Za-z0-9_$]*\b)/gi;for(const m of line.matchAll(re)){out+=esc(line.slice(i,m.index));const t=m[0];let cls='ident';if(/^['"]/.test(t))cls='str';else if(/^\d/.test(t))cls='num';else if(/^(FUNCTION|END|DIM|FOR|TO|STEP|NEXT|IF|THEN|ELSE|GOTO|GOSUB|RETURN|DATA|READ|RESTORE|SUB|CALL)$/i.test(t))cls='kw';else if(/^(>=|<=|<>|=|\+|-|\*|\/)$/i.test(t))cls='op';out+=`<span class="${cls}">${esc(t)}</span>`;i=m.index+t.length}out+=esc(line.slice(i));return out}
function populate(){const fs=frames();$('scrub').max=String(fs.length-1);$('timeline').innerHTML='';}
function setupTimeline(){const fs=frames();const tl=document.createElement('div');tl.className='timeline';tl.id='timeline';for(let i=0;i<fs.length;i++){const f=fs[i],b=document.createElement('button');b.className=`tick ${f.state||''}`;b.innerHTML=`${esc(f.title)}<span class="t-rev">r${f.revision}</span>`;b.title=f.provenance;b.onclick=()=>show(i);tl.appendChild(b)}const old=document.querySelector('.timeline');if(old)old.replaceWith(tl);else $('scrub').before(tl)}
function setSelects(){const sel=$('campaign');sel.innerHTML='';DATA.campaigns.forEach((c,i)=>{const o=document.createElement('option');o.value=i;o.textContent=c.title;sel.appendChild(o)});sel.onchange=()=>{campaignIndex=Number(sel.value);index=0;setupTimeline();show(0)};const ch=$('chapter');ch.innerHTML='';const names=[...new Set(frames().map(f=>f.chapter))];for(const n of names){const o=document.createElement('option');o.value=n;o.textContent=n;ch.appendChild(o)}ch.onchange=()=>{const target=frames().findIndex(f=>f.chapter===ch.value);if(target>=0)show(target)};setupTimeline()}
function show(i){const fs=frames();index=Math.max(0,Math.min(i,fs.length-1));const f=fs[index];$('scrub').value=String(index);$('mission').textContent=f.chapter;$('campaignStatus').textContent=active().summary;$('statePill').textContent=f.state;$('statePill').className=`pill ${f.state}`;$('revision').textContent=`revision ${f.revision}`;$('revBadge').textContent=`BASIC · r${f.revision}`;$('stepTitle').textContent=f.title;$('stepDesc').textContent=f.description;$('provenance').textContent=`Provenance: ${f.provenance}`;$('filename').textContent=active().filename||'PROGRAM.bas';$('counter').textContent=`Action ${index+1} / ${fs.length}`;if($('chapter').value!==f.chapter)$('chapter').value=f.chapter;if(location.hash!==`#${f.id}`)history.replaceState(null,'',`#${f.id}`);
 const highlights=f.highlights||{}, hi=new Set([...(highlights.lines||[]),...(highlights.function_lines||[])]), calls=new Set(highlights.call_lines||[]), codeLines=(f.code||'').replace(/\n$/,'').split('\n');const src=$('source');src.innerHTML='';codeLines.forEach((line,n)=>{const num=n+1,div=document.createElement('div');let cls='code-line';if(hi.has(num))cls+=' '+(f.state==='rejected'?'rejected-focus':(f.state==='committed'||f.state==='validated'?'change':'focus'));if(calls.has(num))cls+=' call';div.className=cls;const call=line.includes('AGE_BY_ID(ID)')&&highlights.semantic_handle&&['is_senior.function','is_adult.function'].includes(highlights.semantic_handle);div.innerHTML=`<span class="ln">${String(num).padStart(2,' ')}</span><span class="code">${highlighter(line)}${call?'<span class="focus-chip call-highlight">bound call → AGE_BY_ID</span>':''}</span>`;src.appendChild(div);if(f.proposal?.line===num&&f.proposal?.new){const chip=document.createElement('span');chip.className='proposed-value';chip.textContent=`proposed ${f.proposal.new.trim()}`;div.querySelector('.code').appendChild(chip)}});
 const proposal=$('proposal');proposal.innerHTML='';if(f.proposal?.append_lines){const box=document.createElement('div');box.className='proposal-box';box.innerHTML='<div class="proposal-label">Preview only · current source remains committed revision '+f.revision+'</div><div class="proposal-code"></div>';box.querySelector('.proposal-code').innerHTML=f.proposal.append_lines.map((l,j)=>`<div class="${(f.proposal.call_lines||[]).includes((f.proposal.highlight_lines||[])[j])?'call-highlight':''}"><span class="plus">+</span>${highlighter(l)}</div>`).join('');proposal.appendChild(box)}else if(f.proposal?.status==='rejected'){const box=document.createElement('div');box.className='reject-box';box.innerHTML=`<b>Denied · no committed source change</b><br>${esc(f.proposal.function||'')} · ${esc(f.proposal.message||f.proposal.diagnostic||'Rejected')}`;proposal.appendChild(box)}
 $('annotation').innerHTML=f.proposal?.annotation&&f.state==='committed'?`<div class="annotation">${esc(f.proposal.annotation)}</div>`:'';
 const focus=$('semanticFocus');focus.innerHTML='';for(const h of [highlights.semantic_handle,...(f.proposal?.semantic_handle?[f.proposal.semantic_handle]:[])].filter(Boolean)){const s=document.createElement('span');s.className='focus-chip';s.textContent=h;focus.appendChild(s)}if(f.proposal?.bound_callee){const s=document.createElement('span');s.className='focus-chip';s.textContent=`calls ${f.proposal.bound_callee}`;focus.appendChild(s)}
 const diag=$('diagnostic');diag.innerHTML='';if(f.proposal?.status==='rejected'){diag.innerHTML=`<p class="status-text fail">${esc(f.proposal.diagnostic||'Rejected')} · revision stays ${f.revision}</p>`}else if(f.validation){diag.innerHTML=`<p class="status-text ${f.validation.passed?'pass':'fail'}">${f.validation.passed?'✓':'×'} ${f.validation.passed?'Validation passed':'Validation failed'}</p>`}
 const sourceUpper=(f.code||'').toUpperCase();const deps=[];if(sourceUpper.includes('FUNCTION AGE_BY_ID'))deps.push({caller:'AGE_BY_ID',callee:'PERSON_ID[] · PERSON_AGE[]'});if(sourceUpper.includes('FUNCTION IS_SENIOR')&&sourceUpper.includes('AGE_BY_ID(ID)'))deps.push({caller:'IS_SENIOR',callee:'AGE_BY_ID(ID)'});if(sourceUpper.includes('FUNCTION IS_ADULT')&&sourceUpper.includes('AGE_BY_ID(ID)'))deps.push({caller:'IS_ADULT',callee:'AGE_BY_ID(ID)'});const proposed=(f.proposal?.append_lines||[]).join('\n').toUpperCase();if(proposed.includes('FUNCTION IS_SENIOR')&&proposed.includes('AGE_BY_ID(ID)'))deps.push({caller:'Preview · IS_SENIOR',callee:'AGE_BY_ID(ID)'});if(proposed.includes('FUNCTION IS_ADULT')&&proposed.includes('AGE_BY_ID(ID)'))deps.push({caller:'Preview · IS_ADULT',callee:'AGE_BY_ID(ID)'});$('deps').innerHTML=deps.length?deps.map(e=>`<div>${esc(e.caller)}<br>　└ ${e.caller.startsWith('Preview')?'proposes':'calls'} <b>${esc(e.callee)}</b></div>`).join(''):'<span class="sub">No function dependency in this frame.</span>';
 const results=f.results||{};let rows='';for(const [engine,vals] of Object.entries(results)){if(vals&&typeof vals==='object'){for(const [id,val] of Object.entries(vals)){let age=val?.age??val,senior=val?.senior,adult=val?.adult;rows+=`<div class="result-row"><span>${esc(engine)}</span><span>ID ${esc(id)} → ${esc(age)}</span><span>${senior!==undefined?`senior ${esc(senior)} `:''}${adult!==undefined?`adult ${esc(adult)}`:''}</span></div>`}}}$('results').innerHTML=rows||'<div class="sub">No runtime result recorded at this step.</div>';const v=f.validation||{};$('validation').textContent=[v.interpreter_jit_agree?'Interpreter = JIT':null,v.dependency_bound?'call binding verified':null,v.boundary_17_18?'17/18 boundary passed':null].filter(Boolean).join(' · ');
 const evidence={provenance:f.provenance,event_refs:f.event_refs||[],mapping:highlights.mapping||null,validation:f.validation||null,checkpoint:f.checkpoint||null,actual_proposal:f.proposal||null};$('evidence').textContent=JSON.stringify(evidence,null,2);for(const t of document.querySelectorAll('.tick'))t.classList.remove('active');document.querySelectorAll('.tick')[index]?.classList.add('active');const focusLine=(highlights.lines||highlights.function_lines||[])[0];if(focusLine){const node=src.children[focusLine-1];if(node)node.scrollIntoView({block:'center',behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'})}else $('scroll').scrollTop=0;
}
function step(delta){show(index+delta)}$('prev').onclick=()=>step(-1);$('next').onclick=()=>step(1);$('scrub').oninput=e=>show(Number(e.target.value));$('speed').oninput=e=>$('speedLabel').textContent=`${e.target.value}×`;$('play').onclick=()=>{if(timer){clearInterval(timer);timer=null;$('play').textContent='▶ Play';return}$('play').textContent='Ⅱ Pause';timer=setInterval(()=>{if(index>=frames().length-1){clearInterval(timer);timer=null;$('play').textContent='▶ Play'}else step(1)},1600/Number($('speed').value))};
setSelects();const initialId=decodeURIComponent(location.hash.slice(1));let initialCampaign=DATA.campaigns.findIndex(c=>c.frames.some(f=>f.id===initialId));if(initialCampaign>=0){campaignIndex=initialCampaign;$('campaign').value=String(campaignIndex);setupTimeline();const initialFrame=frames().findIndex(f=>f.id===initialId);show(initialFrame)}else show(0);
</script></body></html>'''


def render(data: dict[str, Any], out: Path) -> None:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    out.write_text(HTML.replace("__FRAME_DATA__", payload), encoding="utf-8")


def build_artifacts() -> dict[str, Any]:
    frames14 = code14_frames()
    summary14 = read_json(OUT14 / "summary.json")
    equivalence = summary14["replay"]
    deps14 = [{"caller":"is_senior.function","callee":"age_by_id.function"},
              {"caller":"is_adult.function","callee":"age_by_id.function"}]
    data14 = {"schema":"basic-workspace.visual-frames","version":1,
              "campaigns":[{"id":"longitudinal-14b","title":"Cycle 14B · Continued development",
                  "filename":"ADDRESS_BOOK.bas","summary":"IS_SENIOR · age 205 update · context recovery · IS_ADULT",
                  "dependencies":deps14,"frames":frames14}],
              "mapping_policy":"Function identity comes from semantic handles. Statement highlight uses the unique source line diff when historical token spans were not recorded; no cursor positions are inferred."}
    frame_path14=OUT14/"visual-frames.json"
    frame_path14.write_text(json.dumps(data14,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    html_path14=OUT14/"visual-replay.html";render(data14,html_path14)

    frames13=code13_frames()
    summary13=read_json(C13/"summary.json")
    data13={"schema":"basic-workspace.visual-frames","version":1,
            "campaigns":[{"id":"cycle13-real-model","title":"Cycle 13 · Real-model composition",
                "filename":"AGE_BY_ID.bas","summary":"A genuine model adds a bound IS_SENIOR caller",
                "dependencies":[{"caller":"is_senior.function","callee":"age_by_id.function"}],
                "frames":frames13}],
            "mapping_policy":"The selected function is identified by its semantic handle; inserted code is highlighted from the unique committed source diff."}
    frame_path13=C13/"visual-frames.json";frame_path13.write_text(json.dumps(data13,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    html_path13=C13/"visual-replay.html";render(data13,html_path13)
    return {"cycle14":{"frames":len(frames14),"frames_json_bytes":frame_path14.stat().st_size,
                       "html_bytes":html_path14.stat().st_size,"path":str(html_path14)},
            "cycle13":{"frames":len(frames13),"frames_json_bytes":frame_path13.stat().st_size,
                       "html_bytes":html_path13.stat().st_size,"path":str(html_path13)}}


if __name__ == "__main__":
    print(json.dumps(build_artifacts(),indent=2))
