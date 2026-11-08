#!/usr/bin/env python3
"""Run three dependent semantic missions with a deliberate context reset."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from basic_workspace.mir_execution import MirExecutionService
from basic_workspace.model import Workspace, WorkspaceError
from basic_workspace.projection import build_projection, projection_semantics
from experiment.provider_config import make_chat_endpoint, resolve_config, safe_metadata


def load_script(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


age = load_script("cycle12_age_campaign", "age-by-id-campaign.py")
senior = load_script("cycle13_senior_campaign", "is-senior-campaign.py")
renderer = load_script("semantic_replay_renderer", "render-semantic-replay.py")

PROFILE_ID = senior.PROFILE_ID
OUT_DEFAULT = ROOT / "results" / "semantic-replay" / "longitudinal-01" / "calibrated-run-01"
EXPECTED_AGE_55 = {"101": 25.0, "205": 55.0, "900": 53.0, "999": -1.0, "2": -1.0}


def value_expectations() -> dict[str, dict[str, float]]:
    return {"101": {"age": 25.0, "senior": 0.0, "adult": 1.0},
            "205": {"age": 55.0, "senior": 1.0, "adult": 1.0},
            "900": {"age": 53.0, "senior": 1.0, "adult": 1.0},
            "999": {"age": -1.0, "senior": 0.0, "adult": 0.0},
            "2": {"age": -1.0, "senior": 0.0, "adult": 0.0}}


def execute_all(workspace: Workspace, doc: str, revision: int,
                aliases: dict[str, str]) -> dict[str, dict[str, dict[str, float]]]:
    executor = MirExecutionService(timeout=12)
    funcs = {"age": "age_by_id.function", "senior": "is_senior.function", "adult": "is_adult.function"}
    result: dict[str, dict[str, dict[str, float]]] = {}
    for engine in ("interp", "jit"):
        result[engine] = {}
        for entity_id in (101, 205, 900, 999, 2):
            result[engine][str(entity_id)] = {
                kind: executor.execute_function(workspace, doc, revision,
                    aliases[handle], [entity_id], engine)["result"]
                for kind, handle in funcs.items()}
    return result


def semantic_fingerprint(normalized: dict[str, Any]) -> str:
    payload = json.dumps(normalized, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def make_checkpoint(workspace: Workspace, doc: str, aliases: dict[str, str],
                    completed: list[dict[str, Any]], behavior: dict[str, Any],
                    active_mission: dict[str, Any]) -> dict[str, Any]:
    revision = workspace.get_revision(doc)
    raw = projection_semantics(build_projection(workspace, doc, revision))
    normalized = senior.normalized_state(raw, aliases)
    funcs = []
    for row in normalized["functions"]:
        funcs.append({"handle": row["handle"], "name": row["name"],
                      "parameters": row["parameters"], "return_type": row["return_type"]})
    age_fn = next(x for x in normalized["functions"] if x["handle"] == "age_by_id.function")
    arrays = [{"handle": array["handle"], "name": array["name"],
               "element_type": array["element_type"], "lower_bound": array["lower_bound"],
               "upper_bound": array["upper_bound"], "lifetime": "function invocation"}
              for array in age_fn["arrays"]]
    dependencies = senior.candidate_call_edges(normalized)
    return {"schema": "basic-workspace.recovery-checkpoint", "version": 1,
            "document": {"document_id": doc, "revision": revision},
            "execution_profile_id": PROFILE_ID,
            "verified_facts": {"source": "live committed Workspace projection",
                "functions": funcs, "semantic_handles": sorted(aliases),
                "dependencies": dependencies, "arrays": arrays,
                "last_validated_behavior": behavior,
                "completed_missions": completed},
            "agent_authored_notes": [],
            "active_mission": active_mission,
            "known_unsupported": ["strings", "module-level mutable state", "file/network I/O", "unbounded loops"],
            "unresolved_work": [],
            "semantic_fingerprint": semantic_fingerprint(normalized)}


def validate_checkpoint(checkpoint: dict[str, Any], workspace: Workspace, doc: str,
                        expected_profile: str, aliases: dict[str, str],
                        mission_present: bool = True) -> dict[str, Any]:
    revision = workspace.get_revision(doc)
    if checkpoint.get("document", {}).get("document_id") != doc:
        return {"ok": False, "code": "CHECKPOINT_DOCUMENT_MISMATCH"}
    if checkpoint.get("document", {}).get("revision") != revision:
        return {"ok": False, "code": "STALE_CHECKPOINT_REVISION"}
    if checkpoint.get("execution_profile_id") != expected_profile:
        return {"ok": False, "code": "CHECKPOINT_PROFILE_MISMATCH"}
    if not mission_present or not isinstance(checkpoint.get("active_mission"), dict):
        return {"ok": False, "code": "CHECKPOINT_MISSION_MISSING"}
    facts = checkpoint.get("verified_facts", {})
    handles = set(facts.get("semantic_handles", []))
    function_handles = {x.get("handle") for x in facts.get("functions", [])}
    if "age_by_id.function" not in handles or "age_by_id.function" not in function_handles:
        return {"ok": False, "code": "CHECKPOINT_FUNCTION_MISSING"}
    for edge in facts.get("dependencies", []):
        if edge.get("caller") not in handles or edge.get("callee") not in handles:
            return {"ok": False, "code": "CHECKPOINT_PORTABLE_HANDLE_UNKNOWN"}
    current = projection_semantics(build_projection(workspace, doc, revision))
    normalized = senior.normalized_state(current, aliases)
    if semantic_fingerprint(normalized) != checkpoint.get("semantic_fingerprint"):
        return {"ok": False, "code": "CHECKPOINT_FINGERPRINT_MISMATCH"}
    return {"ok": True, "code": "CHECKPOINT_VERIFIED", "revision": revision}


def _call_edges(normalized: dict[str, Any]) -> list[dict[str, str]]:
    return senior.candidate_call_edges(normalized)


def make_adult_mission() -> dict[str, Any]:
    return {"schema": "basic-workspace.mission-contract", "version": 1,
            "mission_id": "mission.compose-age-by-id.is-adult.v1",
            "objective": "Add IS_ADULT(ID), returning 1 when AGE_BY_ID(ID) is at least 18 and 0 otherwise, including unknown IDs. Preserve AGE_BY_ID and IS_SENIOR.",
            "execution_profile": PROFILE_ID,
            "enforcement": {"allowed_operations": ["create_numeric_function"],
                "allowed_function": {"name": "IS_ADULT", "parameter_count": 1, "parameter_type": "numeric"},
                "required_dependency_handle": "age_by_id.function",
                "candidate_invariants": ["existing function projections unchanged", "one function added",
                    "typed call bound to discovered AGE_BY_ID", "no unrelated symbols or arrays"]},
            "functional_goal": {"threshold": 18, "unknown_result": 0.0}}


def adult_validator(workspace: Workspace, doc: str, gateway: Any,
                    requested_revision: int) -> dict[str, Any]:
    revision = workspace.get_revision(doc)
    if requested_revision != revision:
        return {"reliable": False, "code": "STALE_VALIDATION_REVISION", "mission_complete": False,
                "requested_revision": requested_revision, "workspace_revision": revision,
                "executed_revision": None}
    if not gateway.committed:
        return {"reliable": True, "phase": "pre-create", "mission_complete": False,
                "revision": revision, "diagnostics": ["IS_ADULT not committed"]}
    try:
        observed = execute_all(workspace, doc, revision, gateway.aliases)
        raw = projection_semantics(build_projection(workspace, doc, revision))
        normalized = senior.normalized_state(raw, gateway.aliases)
    except (WorkspaceError, KeyError) as exc:
        return {"reliable": False, "code": getattr(exc, "code", "PROJECTION_INVALID"),
                "message": str(exc), "mission_complete": False, "executed_revision": revision}
    expected = value_expectations()
    engines_agree = observed["interp"] == observed["jit"]
    values_match = all(observed[engine] == expected for engine in observed)
    edges = _call_edges(normalized)
    dependency = {"caller": "is_adult.function", "callee": "age_by_id.function"} in edges
    base_unchanged = all(senior.find_function(normalized, row["handle"]) == row
                         for row in gateway.base_snapshot["functions"])
    complete = bool(values_match and engines_agree and dependency and base_unchanged)
    return {"reliable": True, "phase": "post-create", "revision": revision,
            "requested_revision": requested_revision, "workspace_revision": revision,
            "executed_revision": revision, "observed_results": observed,
            "expected_results": expected, "expectation_source": "independent host-owned mission oracle",
            "engines_agree": engines_agree, "values_match": values_match,
            "age_by_id_and_is_senior_unchanged": base_unchanged,
            "age_by_id_call_bound": dependency, "mission_complete": complete,
            "diagnostics": [] if complete else ["Adult mission oracle or invariant check failed"]}


def boundary_oracle(config: dict[str, Any], senior_request: dict[str, Any],
                    adult_request: dict[str, Any]) -> dict[str, Any]:
    cases = {}
    for boundary_age in (17.0, 18.0):
        ws = Workspace()
        doc, aliases, seed = age.create_seed(ws, age.Trace(), f"adult-boundary-{int(boundary_age)}")
        edit = ws.edit_assignment_expression(doc, aliases["people.age.205"],
                                             {"kind": "number", "value": boundary_age}, seed["revision"])
        senior_op = {"operation": "create_numeric_function", **senior.resolve_function_handles(
            senior_request, aliases, {"age_by_id.function"})}
        created1 = ws.apply_transaction(doc, edit["revision"], [senior_op])
        raw1 = projection_semantics(build_projection(ws, doc, created1["revision"]))
        aliases1 = senior.aliases_for_new_function(raw1, aliases, "IS_SENIOR", "is_senior.function")
        adult_op = {"operation": "create_numeric_function", **senior.resolve_function_handles(
            adult_request, aliases1, {"age_by_id.function"})}
        created2 = ws.apply_transaction(doc, created1["revision"], [adult_op])
        raw2 = projection_semantics(build_projection(ws, doc, created2["revision"]))
        aliases2 = senior.aliases_for_new_function(raw2, aliases1, "IS_ADULT", "is_adult.function")
        executor = MirExecutionService(timeout=12)
        results = {engine: {"age": executor.execute_function(ws, doc, created2["revision"],
                          aliases2["age_by_id.function"], [205], engine)["result"],
                            "adult": executor.execute_function(ws, doc, created2["revision"],
                          aliases2["is_adult.function"], [205], engine)["result"],
                            "adult_unknown": executor.execute_function(ws, doc, created2["revision"],
                          aliases2["is_adult.function"], [999], engine)["result"]}
                   for engine in ("interp", "jit")}
        expected = {"age": boundary_age, "adult": 1.0 if boundary_age == 18 else 0.0,
                    "adult_unknown": 0.0}
        cases[str(int(boundary_age))] = {"observed": results, "expected": expected,
            "matches": all(v == expected for v in results.values()),
            "engines_agree": results["interp"] == results["jit"]}
    return {"cases": cases, "passed": all(x["matches"] and x["engines_agree"] for x in cases.values()),
            "isolated_workspaces": True}


def build_stream(seed_operation: dict[str, Any], senior_request: dict[str, Any],
                 adult_request: dict[str, Any], handles: list[str]) -> dict[str, Any]:
    return {"schema": "basic-workspace.constructive-metafile", "version": 1,
            "execution_profile_id": PROFILE_ID, "portable_handles": handles,
            "operations": [
                {"operation": "create_numeric_function", "portable_handle": "age_by_id.function",
                 "arguments": copy.deepcopy(seed_operation)},
                {"operation": "create_numeric_function", "portable_handle": "is_senior.function",
                 "callee_handle": "age_by_id.function", "arguments": copy.deepcopy(senior_request)},
                {"operation": "edit_assignment_expression", "target_handle": "people.age.205",
                 "expression": {"kind": "number", "value": 55.0}},
                {"operation": "create_numeric_function", "portable_handle": "is_adult.function",
                 "callee_handle": "age_by_id.function", "arguments": copy.deepcopy(adult_request)}]}


def replay_stream(stream: dict[str, Any], trace: Any):
    if stream.get("schema") != "basic-workspace.constructive-metafile" or stream.get("version") != 1:
        raise WorkspaceError("REPLAY_SCHEMA", "Unknown constructive stream version")
    ws = Workspace()
    doc, aliases, seed = age.create_seed(ws, trace, "replay")
    operations = stream.get("operations", [])
    if len(operations) != 4 or operations[0].get("arguments") != seed["operation"]:
        raise WorkspaceError("REPLAY_OPERATION_SEQUENCE", "Replay stream does not contain the recorded initial constructor")
    for expected, actual in (("age_by_id.function", operations[0].get("portable_handle")),
                             ("is_senior.function", operations[1].get("portable_handle")),
                             ("is_adult.function", operations[3].get("portable_handle"))):
        if expected != actual:
            raise WorkspaceError("REPLAY_HANDLE_MISSING", f"Expected portable handle {expected}")
    for index, operation in enumerate(operations[1:], 1):
        revision = ws.get_revision(doc)
        if operation["operation"] == "create_numeric_function":
            callee = operation.get("callee_handle")
            if callee != "age_by_id.function" or callee not in aliases:
                raise WorkspaceError("REPLAY_HANDLE_MISSING", f"Cannot resolve call handle {callee}")
            new_name = "IS_SENIOR" if index == 1 else "IS_ADULT"
            function_handle = "is_senior.function" if index == 1 else "is_adult.function"
            resolved = senior.resolve_function_handles(operation["arguments"], aliases, {callee})
            applied = ws.apply_transaction(doc, revision, [{"operation": "create_numeric_function", **resolved}])
            raw = projection_semantics(build_projection(ws, doc, applied["revision"]))
            aliases = senior.aliases_for_new_function(raw, aliases, new_name, function_handle)
        elif operation["operation"] == "edit_assignment_expression":
            target = operation.get("target_handle")
            if target != "people.age.205" or target not in aliases:
                raise WorkspaceError("REPLAY_HANDLE_MISSING", "Age edit target handle is unresolved")
            ws.apply_transaction(doc, revision, [{"operation": "edit_assignment_expression",
                "statement_id": aliases[target], "expression": operation["expression"]}])
        else:
            raise WorkspaceError("REPLAY_OPERATION_UNSUPPORTED", "Unsupported replay operation")
    normalized = senior.normalized_state(projection_semantics(build_projection(ws, doc, ws.get_revision(doc))), aliases)
    return ws, doc, aliases, normalized


def final_html(events: list[dict[str, Any]], summary: dict[str, Any], checkpoint: dict[str, Any] | None,
               normalized: dict[str, Any] | None) -> str:
    safe_events = [{k: v for k, v in event.items() if k not in ("program_snapshot", "request_messages")}
                   for event in events]
    payload = json.dumps({"events": safe_events, "summary": summary,
                          "checkpoint": checkpoint, "structure": normalized}, ensure_ascii=False)
    payload = payload.replace("<", "\\u003c")
    cards = []
    for event in safe_events:
        actor = event.get("actor", "harness")
        label = event.get("event", "event").replace("_", " ")
        detail = event.get("mission_id", event.get("operation", event.get("status", "")))
        cards.append(f"<li><b>{label}</b> <small>{actor}</small><br>{detail}</li>")
    dependencies = "<br>".join(f"{e['caller']} → {e['callee']}" for e in (summary.get("dependencies") or [])) or "No committed dependency edges"
    outcome = summary.get("final_status", "incomplete")
    return f'''<!doctype html><meta charset="utf-8"><title>BASIC Workspace longitudinal campaign</title>
<style>body{{font:16px system-ui;max-width:1100px;margin:2em auto;background:#101827;color:#e5edf7}}section,li{{background:#182437;border:1px solid #34445d;border-radius:8px;padding:1em;margin:.6em 0}}small{{color:#9bb0ca}}.ok{{color:#56dfac}}.bad{{color:#ff8292}}pre{{white-space:pre-wrap;background:#0c1420;padding:1em}}</style>
<h1>Cycle 14B · Longitudinal semantic development</h1><section><h2>Outcome: {outcome}</h2>
<p>Three dependent missions; real model actions, scripted controls, host validation, and replay are labeled separately.</p>
<p><b>Model:</b> {summary.get('model','not run')} · <b>Missions committed:</b> {summary.get('missions_committed',0)}/3</p>
<p><b>Context reset:</b> {summary.get('context_reset','not reached')} · <b>Checkpoint:</b> {summary.get('checkpoint_status','not created')}</p>
<p><b>Dependencies from committed projection:</b><br>{dependencies}</p></section>
<section><h2>Current semantic state</h2><pre id="structure"></pre></section>
<section><h2>Mission history</h2><ol>{''.join(cards)}</ol></section>
<script>const D={payload};document.getElementById('structure').textContent=JSON.stringify(D.structure,null,2)</script>'''


def overview_svg(summary: dict[str, Any]) -> str:
    funcs = summary.get("functions", [])
    deps = summary.get("dependencies", [])
    w, h = 1050, 290
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
             '<rect width="100%" height="100%" fill="#101827"/>',
             f'<text x="30" y="32" fill="#fff" font-family="sans-serif" font-size="21">Cycle 14B · {summary.get("final_status", "incomplete")}</text>',
             f'<text x="30" y="56" fill="#adc0d8" font-family="sans-serif" font-size="13">Missions committed {summary.get("missions_committed",0)}/3 · reset {summary.get("context_reset","not reached")}</text>']
    positions = {"age_by_id.function": (65, 120), "is_senior.function": (395, 120), "is_adult.function": (725, 120)}
    names = {"age_by_id.function": "AGE_BY_ID(ID)", "is_senior.function": "IS_SENIOR(ID)", "is_adult.function": "IS_ADULT(ID)"}
    for handle, (x,y) in positions.items():
        if any(f.get("handle")==handle for f in funcs):
            parts.append(f'<rect x="{x}" y="{y}" width="250" height="58" rx="9" fill="#213c5b" stroke="#61a7db"/>')
            parts.append(f'<text x="{x+16}" y="{y+35}" fill="#fff" font-family="monospace" font-size="17">{names[handle]}</text>')
    for edge in deps:
        src=positions.get(edge.get("caller")); dst=positions.get(edge.get("callee"))
        if src and dst:
            x1,y1=src[0],src[1]+29;x2,y2=dst[0]+250,dst[1]+29
            parts.append(f'<path d="M{x1} {y1} C{x1-55} 220,{x2+55} 220,{x2} {y2}" fill="none" stroke="#57d6a8" stroke-width="3" marker-end="url(#arrow)"/>')
    parts.extend(['<defs><marker id="arrow" markerWidth="9" markerHeight="9" refX="8" refY="4" orient="auto"><path d="M0,0 L0,8 L9,4 z" fill="#57d6a8"/></marker></defs>',
                  f'<text x="30" y="265" fill="#d6e3f3" font-family="sans-serif" font-size="14">AGE_BY_ID reads PERSON_ID[] and PERSON_AGE[]; age 205 is {summary.get("age_205", "unverified")}</text>',
                  '</svg>'])
    return "\n".join(parts)


def campaign(output_dir: Path) -> dict[str, Any]:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise RuntimeError(f"Refusing to overwrite campaign evidence directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    for name in ("mission-1-is-senior", "mission-2-age-205", "mission-3-is-adult"):
        (output_dir / name).mkdir()
    config = resolve_config()
    endpoint = make_chat_endpoint(config)
    trace = age.Trace()
    started = time.perf_counter()
    summary: dict[str, Any] = {"schema": "basic-workspace.longitudinal-campaign-summary", "version": 1,
        "campaign_kind": "real_llm", "model": config["model"], "missions_committed": 0,
        "context_reset": "not reached", "checkpoint_status": "not created", "dependencies": [], "functions": []}
    trace.emit("session_started", campaign="Cycle 14 longitudinal missions",
               campaign_kind="real_llm", actor="harness", model=config["model"],
               endpoint_metadata=safe_metadata(config), execution_profile=PROFILE_ID,
               objective="Compose IS_SENIOR, modify entity 205 age, then resume from a verified checkpoint to compose IS_ADULT.")
    workspace = Workspace()
    seed_start = time.perf_counter()
    doc, aliases, seed = age.create_seed(workspace, trace, "initial-construction")
    seed_ms = round((time.perf_counter()-seed_start)*1000,3)
    revision = workspace.get_revision(doc)
    base_expected = {str(k): float(v) for k,v in age.EXPECTED.items()}
    base_results = age.execute_values(workspace, doc, aliases, revision)
    base_ok = all(x == base_expected for x in base_results.values())
    trace.emit("program_executed", phase="initial", actor="host_validation", revision=revision,
               engine_results=base_results, expected=base_expected, passed=base_ok)
    if not base_ok:
        raise RuntimeError("Initial AGE_BY_ID host oracle did not pass")

    # Mission 1: genuine model composition; no function identity is placed in its prompt.
    m1 = senior.make_mission()
    (output_dir/"mission-1-is-senior"/"mission.json").write_text(json.dumps(m1,indent=2)+"\n")
    base1 = senior.normalized_state(projection_semantics(build_projection(workspace, doc, revision)), aliases)
    senior.OUT = output_dir / "mission-1-is-senior"
    gateway1 = senior.SeniorMissionGateway(workspace, doc, aliases, base1, m1, trace, "mission-1")
    session1 = senior.run_model_session(endpoint, workspace, doc, gateway1, trace, 7, 12,
                                         "IS_SENIOR", 50.0)
    rev1 = workspace.get_revision(doc)
    validation1 = senior.validate_mission(workspace, doc, gateway1, rev1) if gateway1.committed else {
        "mission_complete": False, "executed_revision": None, "diagnostics": ["No model commit"]}
    trace.emit("program_validated", phase="mission-1", actor="host_validation", revision=rev1,
               result=validation1, passed=validation1.get("mission_complete",False))
    summary["mission_1"]={"model_session":session1,"committed":gateway1.committed,"validation":validation1}
    if not (gateway1.committed and validation1.get("mission_complete")):
        summary.update(final_status="mission_1_failed",missions_committed=0,
                       stop_reason="Mission 1 did not commit and pass the independent host oracle.")
        return finish_campaign(output_dir,trace,summary,started,seed_ms,None,None,None,config)
    aliases1 = gateway1.aliases
    summary["missions_committed"] = 1

    # Mission 2: same authoritative Workspace; edit policy resolves logical ID 205 to slot 1.
    m2 = age.make_mission(55.0)
    m2["mission_id"]="mission.age-by-logical-id.205.to-55.v1"
    (output_dir/"mission-2-age-205"/"mission.json").write_text(json.dumps(m2,indent=2)+"\n")
    rev = workspace.get_revision(doc)
    base2 = age.normalize_projection(projection_semantics(build_projection(workspace,doc,rev)), aliases1)
    old_mission_id = age.MISSION_ID
    age.MISSION_ID = m2["mission_id"]
    try:
        gateway2 = age.MissionGateway(workspace,doc,aliases1,base2,m2,trace,"mission-2")
        age.OUT = output_dir/"mission-2-age-205"
        session2 = age.run_model_session(endpoint,workspace,doc,aliases1,gateway2,trace)
    finally:
        age.MISSION_ID = old_mission_id
    rev2=workspace.get_revision(doc)
    aliases2=gateway2.aliases
    base3=senior.normalized_state(projection_semantics(build_projection(workspace,doc,rev2)),aliases2)
    observed2=senior.execute_program(workspace,doc,rev2,aliases2) if gateway2.committed else None
    expected2={e:{"age":a,"senior":1.0 if a>=50 else 0.0} for e,a in EXPECTED_AGE_55.items()}
    m2_ok=bool(gateway2.committed and observed2 and all(observed2[engine]==expected2 for engine in observed2))
    trace.emit("program_validated",phase="mission-2",actor="host_validation",revision=rev2,
               observed=observed2,expected=expected2,passed=m2_ok,
               invariant="AGE_BY_ID and IS_SENIOR remain correctly composed")
    summary["mission_2"]={"model_session":session2,"committed":gateway2.committed,
                           "observed":observed2,"expected":expected2,"passed":m2_ok}
    if not m2_ok:
        summary.update(final_status="mission_2_failed",missions_committed=1,
                       stop_reason="Mission 2 did not commit and preserve established behavior.")
        return finish_campaign(output_dir,trace,summary,started,seed_ms,None,None,None,config)
    summary["missions_committed"] = 2
    summary["dependencies"]=_call_edges(base3)
    summary["functions"]=[{"handle":f["handle"],"name":f["name"]} for f in base3["functions"]]
    summary["age_205"]=55

    # Build a semantic checkpoint, verify it against the same live definition, and inject no IDs.
    m3=make_adult_mission()
    (output_dir/"mission-3-is-adult"/"mission.json").write_text(json.dumps(m3,indent=2)+"\n")
    observed_current=senior.execute_program(workspace,doc,rev2,aliases2)
    checkpoint=make_checkpoint(workspace,doc,aliases2,[
        {"mission_id":m1["mission_id"],"status":"committed_and_validated","revision":rev1,"result":validation1.get("mission_complete")},
        {"mission_id":m2["mission_id"],"status":"committed_and_validated","revision":rev2,"result":m2_ok}],
        observed_current,m3)
    checkpoint_check=validate_checkpoint(checkpoint,workspace,doc,PROFILE_ID,aliases2)
    (output_dir/"recovery-checkpoint.json").write_text(json.dumps(checkpoint,indent=2,ensure_ascii=False)+"\n")
    trace.emit("checkpoint_created",phase="recovery",actor="host_checkpoint",checkpoint_schema=checkpoint["schema"],
               revision=rev2,semantic_fingerprint=checkpoint["semantic_fingerprint"],
               checkpoint_bytes=(output_dir/"recovery-checkpoint.json").stat().st_size,
               contains_transcript=False,verified=checkpoint_check)
    controls=[]
    def check_control(label:str, mutate:Any, mission_present:bool=True, profile:str=PROFILE_ID):
        candidate=copy.deepcopy(checkpoint); mutate(candidate)
        before_revision=workspace.get_revision(doc)
        before_text=workspace.render_document(doc)
        row=validate_checkpoint(candidate,workspace,doc,profile,aliases2,mission_present)
        unchanged=(workspace.get_revision(doc)==before_revision and workspace.render_document(doc)==before_text)
        controls.append({"case":label,"result":row,"rejected":not row.get("ok",False),"state_unchanged":unchanged})
    check_control("stale revision",lambda c:c["document"].update(revision=rev2-1))
    check_control("missing AGE_BY_ID",lambda c:c["verified_facts"].update(functions=[f for f in c["verified_facts"]["functions"] if f["handle"]!="age_by_id.function"]))
    check_control("unknown portable handle",lambda c:c["verified_facts"].update(dependencies=[{"caller":"is_senior.function","callee":"ghost.function"}]))
    check_control("changed execution profile",lambda c:c.update(execution_profile_id="different.profile"))
    check_control("missing mission contract",lambda c:c.update(active_mission=None),mission_present=False)
    check_control("fingerprint mismatch",lambda c:c.update(semantic_fingerprint="0"*64))
    gateway3=senior.SeniorMissionGateway(workspace,doc,aliases2,base3,m3,trace,"mission-3",
                                       function_name="IS_ADULT",function_handle="is_adult.function")
    before_revision=workspace.get_revision(doc); before_text=workspace.render_document(doc)
    rejection=gateway3.reject_operation({"operation":"rename_symbol","target":"age_by_id.function"},rev2)
    controls.append({"case":"unauthorized operation during resumed mission","result":rejection,
                     "rejected":not rejection.get("ok",False),
                     "state_unchanged":workspace.get_revision(doc)==before_revision and workspace.render_document(doc)==before_text})
    checkpoint_controls_passed=checkpoint_check.get("ok") and all(x["rejected"] and x["state_unchanged"] for x in controls) and workspace.get_revision(doc)==rev2
    (output_dir/"checkpoint-controls.json").write_text(json.dumps({"passed":checkpoint_controls_passed,"controls":controls},indent=2)+"\n")
    trace.emit("checkpoint_verified",phase="recovery",actor="host_checkpoint",result=checkpoint_check,
               negative_controls=controls,passed=checkpoint_controls_passed)
    if not checkpoint_controls_passed:
        raise RuntimeError("Recovery checkpoint or negative controls did not validate")
    summary["checkpoint_status"]="verified; no opaque IDs supplied to resumed conversation"

    # Mission 3: new ChatCompletion context. The run function constructs a new two-message
    # conversation; only the checkpoint is added to the user task, never transcript history.
    checkpoint_for_agent={k:v for k,v in checkpoint.items() if k!="document"}
    checkpoint_for_agent["document"]={"revision":rev2}
    trace.emit("context_reset",phase="recovery",actor="harness",previous_session_ids=["mission-1","mission-2"],
               included_prior_messages=False,included_recovery_checkpoint=True,
               included_tool_schemas="fresh current schema")
    adult_validator_fn=lambda requested: adult_validator(workspace,doc,gateway3,requested)
    senior.OUT=output_dir/"mission-3-is-adult"
    session3=senior.run_model_session(endpoint,workspace,doc,gateway3,trace,7,12,
        "IS_ADULT",18.0,adult_validator_fn,checkpoint_for_agent)
    rev3=workspace.get_revision(doc)
    validation3=adult_validator(workspace,doc,gateway3,rev3) if gateway3.committed else {
        "mission_complete":False,"executed_revision":None,"diagnostics":["No model commit"]}
    boundary=boundary_oracle(config,gateway1.committed_request,gateway3.committed_request) if gateway3.committed else {
        "passed":False,"reason":"IS_ADULT was not committed"}
    passed3=bool(validation3.get("mission_complete") and boundary.get("passed"))
    trace.emit("program_validated",phase="mission-3",actor="host_validation",revision=rev3,
               result=validation3,boundary_oracle=boundary,passed=passed3)
    summary["mission_3"]={"model_session":session3,"committed":gateway3.committed,
                           "validation":validation3,"boundary_oracle":boundary,"passed":passed3}
    if gateway3.committed:
        aliases3=gateway3.aliases
        raw3=projection_semantics(build_projection(workspace,doc,rev3))
        original_normalized=senior.normalized_state(raw3,aliases3)
        stream=build_stream(seed["operation"],gateway1.committed_request,gateway3.committed_request,sorted(aliases3))
        (output_dir/"constructive-operations.json").write_text(json.dumps(stream,indent=2,ensure_ascii=False)+"\n")
        replay_trace=age.Trace()
        replay_ws,replay_doc,replay_aliases,replay_normalized=replay_stream(stream,replay_trace)
        replay_revision=replay_ws.get_revision(replay_doc)
        remappings={h:{"original":aliases3[h],"replayed":replay_aliases[h],"remapped":aliases3[h]!=replay_aliases[h]}
                    for h in aliases3 if h in replay_aliases}
        replay_results=execute_all(replay_ws,replay_doc,replay_revision,replay_aliases)
        original_results=execute_all(workspace,doc,rev3,aliases3)
        replay_ok=(original_normalized==replay_normalized and replay_results==original_results and
                   all(x==value_expectations() for x in replay_results.values()))
        equivalence={"structural_equivalence":original_normalized==replay_normalized,
                     "binding_equivalence":_call_edges(original_normalized)==_call_edges(replay_normalized),
                     "behavioral_equivalence":replay_results==original_results,
                     "interpreter_jit_agreement":replay_results["interp"]==replay_results["jit"],
                     "expected_behavior":all(x==value_expectations() for x in replay_results.values()),
                     "identity_remappings":sum(x["remapped"] for x in remappings.values()),
                     "identity_map":remappings,"original_revision":rev3,"replay_revision":replay_revision,
                     "passed":replay_ok}
        (output_dir/"equivalence.json").write_text(json.dumps(equivalence,indent=2,ensure_ascii=False)+"\n")
        replay_trace.emit("replay_completed",phase="replay",actor="replay_engine",revision=replay_revision,
            structural=equivalence["structural_equivalence"],bindings=equivalence["binding_equivalence"],
            behavior=equivalence["behavioral_equivalence"],remappings=equivalence["identity_remappings"],success=replay_ok)
        replay_trace.write(output_dir/"replay-events.jsonl")
        summary["replay"]=equivalence
        summary["final_results"]=original_results
        summary["dependencies"]=_call_edges(original_normalized)
        summary["functions"]=[{"handle":f["handle"],"name":f["name"]} for f in original_normalized["functions"]]
        summary["age_205"]=55
    complete=bool(gateway3.committed and passed3 and summary.get("replay",{}).get("passed"))
    summary.update(final_status="passed" if complete else "mission_3_or_replay_failed",
                   missions_committed=3 if gateway3.committed else 2,
                   context_reset="completed; fresh model conversation used checkpoint only",
                   checkpoint_status="verified before resume")
    return finish_campaign(output_dir,trace,summary,started,seed_ms,checkpoint,
                           original_normalized if gateway3.committed else None,
                           m3,config)


def _call_edges(normalized: dict[str, Any]) -> list[dict[str, str]]:
    return senior.candidate_call_edges(normalized)


def finish_campaign(output_dir: Path, trace: Any, summary: dict[str, Any], started: float,
                    seed_ms: float, checkpoint: dict[str, Any] | None,
                    normalized: dict[str, Any] | None, mission: dict[str, Any] | None,
                    config: dict[str, Any] | None) -> dict[str, Any]:
    summary["elapsed_ms"]=round((time.perf_counter()-started)*1000,3)
    summary["seed_construction_ms"]=seed_ms
    summary["checkpoint_bytes"]=(output_dir/"recovery-checkpoint.json").stat().st_size if (output_dir/"recovery-checkpoint.json").exists() else 0
    if checkpoint:
        summary["checkpoint_estimated_tokens"]=(len(json.dumps(checkpoint,ensure_ascii=False).encode())+3)//4
    for row in trace.events:
        row.setdefault("campaign_kind","real_llm")
    trace.emit("session_completed",phase="campaign",actor="host",status=summary.get("final_status","incomplete"),summary=summary)
    trace.write(output_dir/"history.jsonl")
    (output_dir/"summary.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False)+"\n")
    if config:
        (output_dir/"provider-metadata.json").write_text(json.dumps({"provider":safe_metadata(config),
            "timeout_seconds":config["request_timeout_seconds"],"max_output_tokens":config["max_output_tokens"],
            "temperature":config["temperature"],"top_p":config["top_p"],"seed":config.get("seed")},indent=2)+"\n")
    profile=senior.make_profile()
    profile["profile_id"]=PROFILE_ID
    profile["campaign_requirements"]={"functions":["AGE_BY_ID(ID)","IS_SENIOR(ID)","IS_ADULT(ID)"],
        "state_revision_bound":True,"execution_engines":["interp","jit"]}
    if mission:
        mission_view={"objective":"Three dependent missions: compose, edit entity 205, recover context, compose adult test.",
                      "missions":[mission]}
    else: mission_view={"objective":"Three dependent missions; campaign stopped before completion."}
    events=trace.events
    (output_dir/"replay.html").write_text(final_html(events,summary,checkpoint,normalized),encoding="utf-8")
    (output_dir/"overview.svg").write_text(overview_svg(summary),encoding="utf-8")
    (output_dir/"execution-profile.json").write_text(json.dumps(profile,indent=2,ensure_ascii=False)+"\n")
    report=f'''# Cycle 14B — Longitudinal agent session

Status: **{summary.get('final_status','incomplete')}**

- Model: `{summary.get('model','not run')}`.
- Missions committed: {summary.get('missions_committed',0)}/3.
- Context reset: {summary.get('context_reset','not reached')}.
- Checkpoint: {summary.get('checkpoint_status','not created')}.
- Full replay: {summary.get('replay',{}).get('passed','not completed')}.

See `summary.json`, `history.jsonl`, per-mission `agent-session.json`, `recovery-checkpoint.json`,
`constructive-operations.json`, `equivalence.json`, `replay.html`, and `overview.svg`.
Provider endpoint values and credentials are excluded. Each mission has a new model
conversation; Mission 3 receives only current tools, its objective, and the verified
checkpoint. Seed creation is harness activity, never model activity.

## Reproduction

```sh
python3 experiments/basic-workspace/scripts/provider-preflight.py --probe-timeout 90
python3 experiments/basic-workspace/scripts/longitudinal-campaign.py --output-dir experiments/basic-workspace/results/semantic-replay/longitudinal-01/another-run
```
'''
    (output_dir/"REPORT.md").write_text(report,encoding="utf-8")
    return summary


def main() -> int:
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir",type=Path,default=OUT_DEFAULT)
    args=parser.parse_args()
    result=campaign(args.output_dir.resolve())
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result.get("final_status")=="passed" else 1


if __name__=="__main__":
    raise SystemExit(main())
