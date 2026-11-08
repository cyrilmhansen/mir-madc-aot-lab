#!/usr/bin/env python3
"""Build code-first, offline visual replays from recorded semantic campaigns."""
from __future__ import annotations

import difflib
import html
import json
from pathlib import Path
from typing import Any
import sys

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


def adapt_cycle14_history() -> list[dict[str, Any]]:
    """Recover verified presentation events from the split longitudinal transcripts."""
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


def adapt_cycle13_history() -> list[dict[str, Any]]:
    """Recover the genuine function-composition interaction from its saved transcript."""
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



sys.path.insert(0, str(Path(__file__).resolve().parent))
from visualization import render, adapt_legacy_frames, VISUAL_EVENT_SCHEMA, VISUAL_FRAME_JSON_SCHEMA



def build_artifacts() -> dict[str, Any]:
    frames14 = adapt_cycle14_history()
    summary14 = read_json(OUT14 / "summary.json")
    deps14 = {
        2:[{"caller":"age_by_id.function","callee":"PERSON_ID[] · PERSON_AGE[]"}],
        3:[{"caller":"age_by_id.function","callee":"PERSON_ID[] · PERSON_AGE[]"},{"caller":"is_senior.function","callee":"age_by_id.function"}],
        4:[{"caller":"age_by_id.function","callee":"PERSON_ID[] · PERSON_AGE[]"},{"caller":"is_senior.function","callee":"age_by_id.function"}],
        5:[{"caller":"age_by_id.function","callee":"PERSON_ID[] · PERSON_AGE[]"},{"caller":"is_senior.function","callee":"age_by_id.function"},{"caller":"is_adult.function","callee":"age_by_id.function"}],
    }
    campaign14={"id":"longitudinal-14b","title":"Cycle 14B · Continued development","filename":"ADDRESS_BOOK.bas",
               "summary":"Function composition · entity update · context recovery"}
    data14 = adapt_legacy_frames(campaign14, frames14, deps14)
    events14=data14.pop("_presentation_events")
    source14=data14.pop("_presentation_source")
    frame_path14=OUT14/"visual-frames-generic.json"
    frame_path14.write_text(json.dumps(data14,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    html_path14=OUT14/"visual-replay-generic.html";render(data14,html_path14)
    (OUT14/"presentation-event.schema.json").write_text(json.dumps(VISUAL_EVENT_SCHEMA,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    (OUT14/"visual-frame.schema.json").write_text(json.dumps(VISUAL_FRAME_JSON_SCHEMA,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    (OUT14/"visual-source.json").write_text(json.dumps(source14,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    (OUT14/"visual-events.jsonl").write_text("".join(json.dumps(e,ensure_ascii=False,separators=(",",":"))+"\n" for e in events14),encoding="utf-8")

    frames13=adapt_cycle13_history()
    campaign13={"id":"cycle13-real-model","title":"Cycle 13 · Real-model composition","filename":"AGE_BY_ID.bas",
                "summary":"A genuine model adds a bound semantic caller"}
    deps13={2:[{"caller":"age_by_id.function","callee":"PERSON_ID[] · PERSON_AGE[]"}],
            3:[{"caller":"age_by_id.function","callee":"PERSON_ID[] · PERSON_AGE[]"},{"caller":"is_senior.function","callee":"age_by_id.function"}]}
    data13=adapt_legacy_frames(campaign13,frames13,deps13)
    events13=data13.pop("_presentation_events")
    source13=data13.pop("_presentation_source")
    frame_path13=C13/"visual-frames-generic.json";frame_path13.write_text(json.dumps(data13,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    html_path13=C13/"visual-replay-generic.html";render(data13,html_path13)
    (C13/"presentation-event.schema.json").write_text(json.dumps(VISUAL_EVENT_SCHEMA,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    (C13/"visual-frame.schema.json").write_text(json.dumps(VISUAL_FRAME_JSON_SCHEMA,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    (C13/"visual-source.json").write_text(json.dumps(source13,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    (C13/"visual-events.jsonl").write_text("".join(json.dumps(e,ensure_ascii=False,separators=(",",":"))+"\n" for e in events13),encoding="utf-8")
    return {"cycle14":{"frames":len(frames14),"frames_json_bytes":frame_path14.stat().st_size,
                       "html_bytes":html_path14.stat().st_size,"path":str(html_path14)},
            "cycle13":{"frames":len(frames13),"frames_json_bytes":frame_path13.stat().st_size,
                       "html_bytes":html_path13.stat().st_size,"path":str(html_path13)}}


if __name__ == "__main__":
    print(json.dumps(build_artifacts(),indent=2))
