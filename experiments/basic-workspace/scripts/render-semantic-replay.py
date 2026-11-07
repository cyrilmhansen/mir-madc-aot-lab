#!/usr/bin/env python3
"""Render an operator report from recorded semantic replay events only."""
from __future__ import annotations

import argparse
import html
import json
import time
from pathlib import Path
from typing import Any


LABELS = {
    "session_started": "Session started",
    "agent_session_started": "Real model session started",
    "model_request": "Model request",
    "model_response": "Model response",
    "model_tool_call": "Model selected a tool",
    "tool_result": "Tool result",
    "model_request_failed": "Model request failed",
    "model_final_answer": "Model final answer",
    "host_correctness_judgment": "Host correctness judgment",
    "agent_observation": "Agent inspected a semantic entity",
    "checkpoint_created": "Checkpoint",
    "operation_proposed": "Proposed operation",
    "symbol_discovered": "Semantic target discovered",
    "preview_accepted": "Preview accepted (not committed)",
    "preview_rejected": "Preview rejected",
    "transaction_committed": "Transaction committed",
    "transaction_rejected": "Operation denied; state unchanged",
    "program_validated": "Program validated",
    "program_executed": "MIR execution",
    "replay_started": "Replay started in fresh workspace",
    "replay_completed": "Replay equivalence result",
    "replay_failed": "Replay failed",
    "session_completed": "Session completed",
}


def read_events(path: Path) -> list[dict[str, Any]]:
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    for expected, event in enumerate(events, 1):
        if event.get("sequence") != expected:
            raise ValueError(f"trace sequence gap at row {expected}")
        if "event" not in event:
            raise ValueError(f"event name missing at row {expected}")
    return events


def overview_svg(events: list[dict[str, Any]]) -> str:
    important = [e for e in events if e["event"] in (
        "session_started", "checkpoint_created", "program_executed", "preview_accepted",
        "transaction_committed", "transaction_rejected", "replay_started", "replay_completed",
        "session_completed")]
    width, row_h, top = 960, 68, 30
    height = top + max(1, len(important)) * row_h + 26
    start = next((e for e in events if e["event"] == "session_started"), {})
    completed = next((e for e in reversed(events) if e["event"] == "session_completed"), {})
    title = str(start.get("campaign", "Semantic replay — observed event trace"))
    objective = str(start.get("objective", ""))[:120]
    campaign_kind = str(start.get("campaign_kind", "unknown"))
    outcome = str(completed.get("status", "incomplete")).upper()
    chunks = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height+300}" viewBox="0 0 {width} {height+300}">',
              '<rect width="100%" height="100%" fill="#101827"/>',
              f'<text x="32" y="26" fill="#dce8f7" font-family="sans-serif" font-size="18" font-weight="bold">{html.escape(title)} · {html.escape(campaign_kind)} · {html.escape(outcome)}</text>',
              f'<text x="32" y="47" fill="#a7b6ca" font-family="sans-serif" font-size="12">{html.escape(objective)}</text>']
    for index, event in enumerate(important):
        y = top + 56 + index * row_h
        kind = event["event"]
        denied = kind == "transaction_rejected"
        committed = kind == "transaction_committed"
        color = "#5c2431" if denied else "#183f36" if committed else "#1d2c43"
        label = LABELS.get(kind, kind)
        phase = event.get("phase", "")
        rev = event.get("resulting_revision", event.get("revision", ""))
        detail = event.get("target_handle", event.get("checkpoint", event.get("operation", event.get("function_handle", event.get("mission_id", "")))))
        status = "DENIED" if denied else "COMMITTED" if committed else "OBSERVED"
        chunks.append(f'<rect x="34" y="{y}" width="892" height="52" rx="8" fill="{color}" stroke="#34445d"/>')
        chunks.append(f'<text x="50" y="{y+21}" fill="#ffffff" font-family="sans-serif" font-size="14" font-weight="bold">{html.escape(label)} — {html.escape(status)}</text>')
        meta = " · ".join(str(x) for x in (phase, detail, f"revision {rev}" if rev != "" else "") if x)
        chunks.append(f'<text x="50" y="{y+40}" fill="#c5d2e4" font-family="monospace" font-size="12">{html.escape(meta[:115])}</text>')
        if index != len(important) - 1:
            chunks.append(f'<path d="M480 {y+52} v16" stroke="#71829b" stroke-width="2"/>')
    snapshot_event = next((e for e in reversed(events)
                           if e.get("event") == "transaction_committed" and e.get("semantic_snapshot")
                           and e.get("phase") in ("agent", "scripted-demo")), None)
    snapshot = snapshot_event.get("semantic_snapshot", {}) if snapshot_event else {}
    functions = snapshot.get("functions", [])
    if functions:
        panel_y = height + 12
        chunks.extend([f'<rect x="24" y="{panel_y}" width="912" height="190" rx="10" fill="#182437" stroke="#34445d"/>',
                       f'<text x="42" y="{panel_y+25}" fill="#dce8f7" font-family="sans-serif" font-size="16" font-weight="bold">Function dependencies from committed semantic state</text>'])
        function_positions: dict[str, tuple[int, int]] = {}
        for index, function in enumerate(functions):
            x, y = (105 if index == 0 else 485), panel_y + 55
            function_positions[function.get("handle", "")] = (x, y)
            params = [str(p).split(".")[-1].upper() for p in function.get("parameters", [])]
            name = f"{function.get('name')}({', '.join(params)})"
            chunks.append(f'<rect x="{x}" y="{y}" width="300" height="44" rx="7" fill="#213c5b" stroke="#6483a8"/>')
            chunks.append(f'<text x="{x+14}" y="{y+27}" fill="#fff" font-family="monospace" font-size="14">{html.escape(name)}</text>')
        def calls_in(value: Any) -> list[str]:
            found: list[str] = []
            if isinstance(value, dict):
                if value.get("kind") == "call" and isinstance(value.get("value"), str):
                    found.append(value["value"])
                for child in value.values(): found.extend(calls_in(child))
            elif isinstance(value, list):
                for child in value: found.extend(calls_in(child))
            return found
        for function in functions:
            source = function_positions.get(function.get("handle"))
            for callee in calls_in(function.get("statements", [])):
                target = function_positions.get(callee)
                if source and target:
                    x1, y1 = source[0], source[1] + 22
                    x2, y2 = target[0] + 300, target[1] + 22
                    chunks.append(f'<path d="M{x1} {y1} C {x1-45} {panel_y+135}, {x2+45} {panel_y+135}, {x2} {y2}" fill="none" stroke="#45d6a1" stroke-width="2" marker-end="url(#arrow)"/>')
                    chunks.append(f'<text x="{(x1+x2)//2-15}" y="{panel_y+131}" fill="#8de2bd" font-family="sans-serif" font-size="11">calls</text>')
        chunks.append('<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L0,6 L8,3 z" fill="#45d6a1"/></marker></defs>')
        age = next((f for f in functions if f.get("handle") == "age_by_id.function"), None)
        if age and age.get("arrays"):
            ax, ay = 105, panel_y + 123
            for index, array in enumerate(age["arrays"]):
                x = ax + index * 205
                chunks.append(f'<rect x="{x}" y="{ay}" width="185" height="32" rx="6" fill="#3a3045" stroke="#8d78a6"/>')
                chunks.append(f'<text x="{x+10}" y="{ay+21}" fill="#eadfff" font-family="monospace" font-size="12">reads {html.escape(array.get("name", "array"))}[]</text>')
                if "age_by_id.function" in function_positions:
                    fx, fy = function_positions["age_by_id.function"]
                    chunks.append(f'<path d="M{fx+145} {fy+44} v12 H{x+92} v{ay-(fy+56)}" fill="none" stroke="#a88fc2" stroke-width="1.5"/>')
        height += 220
    chunks.append('</svg>')
    return "\n".join(chunks) + "\n"


def build_html(events: list[dict[str, Any]], profile: dict[str, Any], mission: dict[str, Any]) -> str:
    committed = next((e for e in reversed(events) if e.get("event") == "transaction_committed"
                      and e.get("phase") in ("agent", "scripted-demo")), {})
    snapshot = committed.get("semantic_snapshot", {})
    functions = snapshot.get("functions", [])
    senior = next((f for f in functions if f.get("handle") == "is_senior.function"), None)
    age = next((f for f in functions if f.get("handle") == "age_by_id.function"), None)
    def walk_calls(value: Any) -> list[str]:
        if isinstance(value, dict):
            own = [str(value.get("value"))] if value.get("kind") == "call" else []
            return own + sum((walk_calls(x) for x in value.values()), [])
        if isinstance(value, list):
            return sum((walk_calls(x) for x in value), [])
        return []
    dependencies = walk_calls(senior.get("statements", [])) if senior else []
    model_events = [e for e in events if e.get("actor") in ("real_llm", "llm_tool") or e.get("event") in ("model_tool_call", "model_response")]
    scripted_denials = sum(e.get("event") == "transaction_rejected" and e.get("phase") == "controls" for e in events)
    validation = next((e.get("validation", {}) for e in reversed(events)
                       if e.get("event") == "program_validated" and e.get("phase") == "host-post-model"), {})
    replay = next((e for e in reversed(events) if e.get("event") in ("replay_completed", "replay_failed")), {})
    completion = next((e.get("summary", {}) for e in reversed(events) if e.get("event") == "session_completed"), {})
    final_status = completion.get("final_status")
    status_text = "PASS" if validation.get("mission_complete") and replay.get("success") else \
        "PENDING MODEL" if final_status == "pending_model" else "INCOMPLETE / FAILED"
    provenance = "real model actions recorded" if model_events else "scripted mechanics; no model actions"
    function_text = f"{senior.get('name')} → {', '.join(dependencies)}" if senior else "IS_SENIOR not committed"
    base_text = f"{age.get('name')} reads {', '.join(a.get('name', '') + '[]' for a in age.get('arrays', []))}" if age else "AGE_BY_ID structure unavailable"
    summary_html = f'''<section class="campaign-summary"><h2>Campaign outcome: {html.escape(status_text)}</h2>
<div class="summary-grid"><div><strong>Mission</strong><br>{html.escape(str(mission.get('objective', '')))}</div>
<div><strong>Created dependency</strong><br><code>{html.escape(function_text)}</code><br><span class="muted">{html.escape(base_text)}</span></div>
<div><strong>Evidence</strong><br>{html.escape(provenance)}<br>Scripted policy denials: {scripted_denials} · Revision: {html.escape(str(committed.get('resulting_revision', '—')))}</div></div></section>'''
    payload = json.dumps({"events": events, "profile": profile, "mission": mission}, ensure_ascii=False)
    payload = payload.replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    title = "Semantic Replay — BASIC Workspace"
    return f'''<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
:root{{--bg:#101827;--panel:#182437;--line:#34445d;--text:#e5edf7;--muted:#a7b6ca;--green:#45d6a1;--red:#ff7284;--amber:#ffc76b;--blue:#8fc6ff}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--text);font:15px/1.45 system-ui,sans-serif}}
header{{padding:22px 28px;border-bottom:1px solid var(--line)}} h1{{font-size:22px;margin:0 0 8px}} .muted{{color:var(--muted)}}
main{{max-width:1400px;margin:auto;padding:20px;display:grid;grid-template-columns:310px 1fr;gap:18px}}
section,.timeline{{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px}}
.timeline{{max-height:78vh;overflow:auto}} button{{background:#21344f;color:var(--text);border:1px solid #46617f;padding:8px 12px;border-radius:6px;cursor:pointer}}
button:hover{{background:#2a4568}} .controls{{display:flex;align-items:center;gap:9px;margin-bottom:13px}}
.event{{display:block;width:100%;text-align:left;margin:5px 0;background:#141e2e;border-color:transparent}}
.event.active{{border-color:var(--blue);background:#203654}} .badge{{display:inline-block;padding:2px 7px;border-radius:10px;font-size:12px;background:#35445a}}
.badge.commit{{color:var(--green)}} .badge.denied{{color:var(--red)}} .badge.preview{{color:var(--amber)}}
.columns{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px}} pre{{background:#0d1420;padding:13px;border-radius:7px;overflow:auto;white-space:pre-wrap;min-height:110px}}
pre.code{{font:14px/1.5 ui-monospace,monospace}} .denial{{border-left:4px solid var(--red);padding:9px;background:#351d29}}
.pass{{color:var(--green)}} .fail{{color:var(--red)}} summary{{cursor:pointer}} a{{color:var(--blue)}}
.campaign-summary{{max-width:1400px;margin:16px auto 0;background:#182437;border:1px solid #34445d;border-radius:10px;padding:15px 20px}}
.summary-grid{{display:grid;grid-template-columns:1.5fr 1fr 1fr;gap:16px}} .summary-grid>div{{padding:8px;border-left:2px solid #45d6a1}}
@media(max-width:1000px){{main{{grid-template-columns:1fr}}.timeline{{max-height:36vh}}.columns{{grid-template-columns:1fr}}}}
</style>
<header><h1>Semantic operation replay</h1><div id="subtitle" class="muted"></div></header>
{summary_html}
<main><nav class="timeline"><div class="controls"><button id="prev">← Previous</button><button id="next">Next →</button><span id="counter" class="muted"></span></div><div id="events"></div><p class="muted">Proposal events do not change the displayed committed program. A preview diff is shown separately.</p></nav>
<div><section><h2 id="eventTitle"></h2><div id="eventStatus"></div><p id="eventMeta" class="muted"></p><div id="eventDetails"></div></section>
<div class="columns"><section><h3>Current committed program</h3><div id="currentRevision" class="muted"></div><pre id="currentProgram" class="code"></pre></section>
<section><h3>Function and nested control-flow structure</h3><pre id="currentStructure" class="code"></pre></section>
<section><h3>Proposed preview (not current state)</h3><pre id="previewDiff" class="code"></pre></section></div>
<section><h3>Mission and profile</h3><details><summary>Show contract and execution profile</summary><div class="columns"><pre id="mission"></pre><pre id="profile"></pre></div></details></section></div></main>
<script>
const DATA={payload}; const E=DATA.events; let pos=0;
const $=id=>document.getElementById(id);
const esc=s=>String(s??'');
const safe=s=>esc(s).replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
const badge=(e)=>e==='transaction_committed'?['COMMITTED','commit']:e==='transaction_rejected'?['DENIED · state unchanged','denied']:e==='preview_accepted'?['PREVIEW · not committed','preview']:e==='preview_rejected'?['PREVIEW REJECTED','denied']:e==='model_tool_call'?['MODEL TOOL CALL','preview']:['OBSERVED',''];
function currentAt(i){{let src='',rev='—',structure={{functions:[],arrays:[],diagnostics:[]}};for(let n=0;n<=i;n++){{const e=E[n];if(e.program_snapshot!==undefined&&['initial-construction','agent','scripted-demo'].includes(e.phase)){{src=e.program_snapshot;rev=e.resulting_revision??e.revision??rev;structure=e.semantic_snapshot??structure;}}}}return [src,rev,structure]}}
function exprText(x){{if(!x)return '';if(x.kind==='number')return String(x.value);if(x.kind==='variable'||x.kind==='array_element'||x.kind==='call')return `${{x.value}}${{x.children?.length?'('+x.children.map(exprText).join(',')+')':''}}`;if(x.kind==='unary_minus')return '-'+exprText(x.children[0]);if(['+','-','*','/','=','<>','<','<=','>','>='].includes(x.kind))return `${{exprText(x.children[0])}} ${{x.kind}} ${{exprText(x.children[1])}}`;return x.kind}}
function treeText(snap){{if(!snap?.functions?.length)return '(no compiled structure recorded yet)';let lines=[];function block(rows,depth){{for(const s of rows){{let pad='  '.repeat(depth);if(s.kind==='assignment'||s.kind==='array_assignment')lines.push(`${{pad}}[${{s.statement_handle}}] ${{s.target_handle}}${{s.target_index?'['+exprText(s.target_index)+']':''}} = ${{exprText(s.expression)}}`);else if(s.kind==='for'){{lines.push(`${{pad}}FOR ${{s.variable_handle}} = ${{s.start}} TO ${{s.end}} STEP ${{s.step}} (limit ${{s.iteration_limit}})`);block(s.body,depth+1)}}else if(s.kind==='if'){{lines.push(`${{pad}}IF ${{exprText(s.condition)}} THEN`);block(s.then,depth+1);if(s.else.length){{lines.push(`${{pad}}ELSE`);block(s.else,depth+1)}}lines.push(`${{pad}}END IF`)}}}}}}for(const f of snap.functions){{lines.push(`FUNCTION ${{f.name}}(${{f.parameters.join(', ')}}) → ${{f.return_type}} [${{f.handle}}]`);for(const a of f.arrays)lines.push(`  DIM ${{a.name}}(${{a.lower_bound}}..${{a.upper_bound}}) : ${{a.element_type}} [${{a.handle}}]`);block(f.statements,1)}}return lines.join('\\n')}}
function render(){{const e=E[pos], [src,rev,structure]=currentAt(pos), [st,cl]=badge(e.event);$('counter').textContent=`${{pos+1}} / ${{E.length}}`; $('eventTitle').textContent=({json.dumps(LABELS)}[e.event]||e.event);$('eventStatus').innerHTML=`<span class="badge ${{cl}}">${{st}}</span>`;$('eventMeta').textContent=`#${{e.sequence}} · ${{e.phase||''}} · rev ${{e.base_revision??e.revision??'—'}} → ${{e.resulting_revision??'—'}} · ${{e.timestamp_utc||''}}`;
let details={{}};for(const [k,v] of Object.entries(e))if(!['sequence','event','timestamp_utc','program_snapshot','preview_diff'].includes(k))details[k]=v;
if(e.event==='transaction_rejected')$('eventDetails').innerHTML=`<div class="denial"><strong>Denied: ${{esc(e.code)}}</strong><br>${{esc(e.message)}}<br>Authoritative state unchanged: ${{String(e.authoritative_state_unchanged)}}</div>`;else $('eventDetails').innerHTML='';
$('eventDetails').append(Object.assign(document.createElement('pre'),{{textContent:JSON.stringify(details,null,2)}}));$('currentProgram').textContent=src||'(empty virtual document)';$('currentRevision').textContent=`Committed revision ${{rev}}`;$('currentStructure').textContent=treeText(structure);$('previewDiff').textContent=e.proposed_diff||e.preview_diff||'(no preview for this event)';
document.querySelectorAll('.event').forEach((b,n)=>b.classList.toggle('active',n===pos));}}
function init(){{const session=E.find(e=>e.event==='session_started')||{{}};$('subtitle').textContent=`${{session.campaign_kind||'unknown'}} · ${{DATA.profile.name}} · Mission: ${{DATA.mission.objective}}`;$('mission').textContent=JSON.stringify(DATA.mission,null,2);$('profile').textContent=JSON.stringify(DATA.profile,null,2);$('events').innerHTML=E.map((e,i)=>`<button class="event" data-i="${{i}}"><span class="badge ${{badge(e.event)[1]}}">${{badge(e.event)[0]}}</span> &nbsp;${{i+1}}. ${{safe(({json.dumps(LABELS)}[e.event]||e.event))}}<br><small class="muted">${{safe(e.phase||'')}} · rev ${{safe(e.resulting_revision??e.revision??e.base_revision??'—')}}</small></button>`).join('');document.querySelectorAll('.event').forEach(b=>b.onclick=()=>{{pos=Number(b.dataset.i);render()}});$('prev').onclick=()=>{{pos=Math.max(0,pos-1);render()}};$('next').onclick=()=>{{pos=Math.min(E.length-1,pos+1);render()}};document.addEventListener('keydown',e=>{{if(e.key==='ArrowRight')$('next').click();if(e.key==='ArrowLeft')$('prev').click()}});render()}} init();
</script></html>'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", type=Path, default=Path(__file__).resolve().parents[1] / "results/semantic-replay/history.jsonl")
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parents[1] / "results/semantic-replay")
    args = parser.parse_args()
    started = time.perf_counter()
    events = read_events(args.trace)
    profile = json.loads((args.output_dir / "execution-profile.json").read_text(encoding="utf-8"))
    mission = json.loads((args.output_dir / "mission.json").read_text(encoding="utf-8"))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "replay.html").write_text(build_html(events, profile, mission), encoding="utf-8")
    (args.output_dir / "overview.svg").write_text(overview_svg(events), encoding="utf-8")
    elapsed = (time.perf_counter() - started) * 1000
    metrics_path = args.output_dir / "metrics.json"
    metrics = json.loads(metrics_path.read_text(encoding="utf-8")) if metrics_path.exists() else {"schema": "basic-workspace.semantic-replay-metrics", "version": 1}
    metrics["visualization_generation_ms"] = round(elapsed, 4)
    metrics_path.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"events": len(events), "html_bytes": (args.output_dir / "replay.html").stat().st_size,
                      "svg_bytes": (args.output_dir / "overview.svg").stat().st_size,
                      "generation_ms": round(elapsed, 4)}, indent=2))


if __name__ == "__main__":
    main()
