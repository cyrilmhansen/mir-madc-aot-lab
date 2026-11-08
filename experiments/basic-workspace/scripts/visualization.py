#!/usr/bin/env python3
"""Generic compiler and offline/live renderer for semantic presentation events."""
from __future__ import annotations
import json
import os
import time
import threading
from dataclasses import dataclass
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Iterable, Mapping

FRAME_SCHEMA = "basic-workspace.visual-frames"
FRAME_VERSION = 2
PRESENTATION_EVENT_SCHEMA = "basic-workspace.presentation-event"
PRESENTATION_EVENT_VERSION = 1
DISPLAY_STATES = {"selection", "preview", "rejection", "commit", "validation", "checkpoint", "context_reset", "reconstruction", "observation", "mission_status"}
MAPPINGS = {"exact_semantic_span", "verified_unique_line_difference", "verified_function_boundary", "unknown"}

class PresentationError(ValueError):
    pass


def validate_presentation_event(event: Mapping[str, Any]) -> None:
    if any(not event.get(k) for k in ("event_id", "event_type", "provenance")):
        raise PresentationError("presentation event requires event_id, event_type, and provenance")
    if event["event_type"] not in DISPLAY_STATES | {"initial"}:
        raise PresentationError(f"unsupported event type {event['event_type']}")
    if event.get("revision") is not None and not isinstance(event["revision"], int):
        raise PresentationError("revision must be an integer or null")
    if event.get("focus", {}).get("mapping", "unknown") not in MAPPINGS:
        raise PresentationError("invalid semantic span mapping")


def _freshness(observation: Mapping[str, Any] | None, revision: int) -> str:
    if observation is None or observation.get("revision") is None:
        return "unknown"
    return "current" if observation["revision"] == revision else "historical"


@dataclass
class VisualFrameCompiler:
    campaign_id: str
    campaign_title: str
    filename: str
    initial_revision: int
    initial_code: str
    snapshots: Mapping[int, str]
    initial_dependencies: list[dict[str, Any]] | None = None

    def __post_init__(self) -> None:
        self.snapshots=dict(self.snapshots)
        self.revision = self.initial_revision
        self.code = self.initial_code
        self.dependencies = list(self.initial_dependencies or [])
        self.latest_observation = None
        self.mission_status = None
        self.frames: list[dict[str, Any]] = []
        self.seen: set[str] = set()
        self.next_sequence = 1

    def consume(self, event: Mapping[str, Any]) -> dict[str, Any] | None:
        validate_presentation_event(event)
        event_id = str(event["event_id"])
        if event_id in self.seen:
            return None
        sequence = event.get("presentation_sequence")
        if sequence is not None and sequence != self.next_sequence:
            raise PresentationError(f"presentation stream gap: expected {self.next_sequence}, got {sequence}")
        self.next_sequence += 1
        self.seen.add(event_id)
        kind, revision = event["event_type"], event.get("revision")
        if kind == "commit":
            if not isinstance(revision, int) or revision <= self.revision:
                raise PresentationError("commit must advance the committed revision")
            supplied_snapshot=event.get("snapshot")
            if supplied_snapshot is not None and revision in self.snapshots and supplied_snapshot!=self.snapshots[revision]:
                raise PresentationError(f"event snapshot disagrees with authoritative snapshot for revision {revision}")
            if supplied_snapshot is not None:
                self.snapshots[revision]=str(supplied_snapshot)
            if revision not in self.snapshots:
                raise PresentationError(f"missing authoritative snapshot for revision {revision}")
            self.revision, self.code = revision, self.snapshots[revision]
            self.dependencies = list(event.get("dependencies", []))
        elif kind in {"preview", "rejection"} and revision != self.revision:
            raise PresentationError(f"{kind} base revision {revision} differs from committed revision {self.revision}")
        elif kind != "initial" and isinstance(revision, int) and revision > self.revision:
            raise PresentationError(f"missing commit before event revision {revision}")
        if event.get("observation") is not None:
            self.latest_observation = dict(event["observation"])
            self.latest_observation.setdefault("revision", revision)
        if event.get("mission_status") is not None:
            self.mission_status = str(event["mission_status"])
        focus = dict(event.get("focus", {}))
        state = {"initial":"baseline" if event.get("mission_status") else "committed", "selection":"selected", "preview":"proposed", "rejection":"rejected", "commit":"committed", "validation":"validated", "checkpoint":"checkpoint", "context_reset":"checkpoint", "reconstruction":"checkpoint", "observation":"validated", "mission_status":"status"}[kind]
        frame = {"id":event.get("frame_id",event_id), "source_event_ref":event.get("source_event_ref",event_id),
                 "session_id":event.get("session_id"), "mission_id":event.get("mission_id"),
                 "provenance":event["provenance"], "revision":self.revision, "event_revision":revision,
                 "state":state, "event_type":kind, "code":self.code, "filename":self.filename,
                 "title":event.get("title",kind.replace("_"," ").title()), "chapter":event.get("chapter",event.get("mission_id","Session")),
                 "description":event.get("description",""), "focus":focus,
                 "highlights":{**focus.get("spans",{}), "semantic_handles":focus.get("handles",[]), "mapping":focus.get("mapping","unknown")},
                 "proposal":event.get("preview"), "outcome":event.get("outcome"), "validation":event.get("validation"),
                 "dependencies":list(event.get("dependencies",self.dependencies)), "observation":self.latest_observation,
                 "observation_freshness":_freshness(self.latest_observation,self.revision), "event_refs":event.get("source_event_ref",event_id)}
        if self.mission_status is not None:frame["mission_status"]=self.mission_status
        if event.get("lifecycle") is not None:frame["lifecycle"]=event["lifecycle"]
        self.frames.append(frame)
        return frame


def compile_visual_frames(campaign: Mapping[str, Any], initial: Mapping[str, Any], events: Iterable[Mapping[str, Any]], snapshots: Mapping[int, str]) -> dict[str, Any]:
    compiler=VisualFrameCompiler(str(campaign["id"]),str(campaign["title"]),str(campaign.get("filename","PROGRAM.bas")),int(initial["revision"]),str(initial["code"]),snapshots,list(initial.get("dependencies",[])))
    for event in events: compiler.consume(event)
    return {"schema":FRAME_SCHEMA,"version":FRAME_VERSION,"campaigns":[{**dict(campaign),"frames":compiler.frames}],"presentation_event_schema":{"id":PRESENTATION_EVENT_SCHEMA,"version":PRESENTATION_EVENT_VERSION}}


def adapt_legacy_frames(campaign: Mapping[str, Any], legacy_frames: list[Mapping[str, Any]], dependency_by_revision: Mapping[int, list[dict[str, Any]]]) -> dict[str, Any]:
    """Normalize the Cycle 11–14 visual records without altering their journals."""
    if not legacy_frames:
        raise PresentationError("legacy evidence has no initial frame")
    snapshots: dict[int, str] = {}
    for row in legacy_frames:
        if row.get("state") == "committed" and isinstance(row.get("revision"), int):
            rev, code = int(row["revision"]), str(row.get("code", ""))
            if rev in snapshots and snapshots[rev] != code:
                raise PresentationError(f"conflicting committed source snapshots at revision {rev}")
            snapshots[rev] = code
    initial_row = legacy_frames[0]
    initial = {"revision":int(initial_row["revision"]), "code":str(initial_row["code"]),
               "dependencies":list(dependency_by_revision.get(int(initial_row["revision"]), []))}
    events: list[dict[str, Any]] = []
    current_revision=int(initial_row["revision"])
    current_code=str(initial_row["code"])
    for seq, row in enumerate(legacy_frames, 1):
        state = row.get("state", "selected")
        proposal = row.get("proposal")
        if seq == 1:
            event_type = "initial"
        elif state == "committed":
            code=str(row.get("code", ""))
            event_type = "commit" if code != current_code else "selection"
        elif state == "proposed":
            event_type = "rejection" if proposal and proposal.get("status") == "rejected" else "preview"
        elif state == "rejected":
            event_type = "rejection"
        elif state == "selected":
            event_type = "selection"
        elif state == "validated":
            event_type = "validation"
        elif state == "checkpoint":
            prov = str(row.get("provenance", "")).lower()
            title = str(row.get("title", "")).lower()
            event_type = "context_reset" if "recovery boundary" in prov or "context reset" in title else ("reconstruction" if "reconstruction" in prov else "checkpoint")
        else:
            continue
        old_highlights = row.get("highlights", {})
        raw_map = str(old_highlights.get("mapping", "unknown")).lower()
        mapping = "exact_semantic_span" if "exact" in raw_map else ("verified_unique_line_difference" if "unique" in raw_map or "diff" in raw_map else ("verified_function_boundary" if old_highlights.get("function_lines") else "unknown"))
        spans = {k:old_highlights[k] for k in ("lines", "function_lines", "call_lines", "expression_lines") if k in old_highlights}
        handles = [old_highlights["semantic_handle"]] if old_highlights.get("semantic_handle") else []
        handles.extend(old_highlights.get("semantic_handles", []))
        results = row.get("results")
        observation = None
        if results:
            args=row.get("validation", {}).get("arguments")
            if args is None and isinstance(results.get("interp"),dict):args={"fixture_ids":list(results["interp"].keys())}
            agreement=row.get("validation", {}).get("interpreter_jit_agree", row.get("validation", {}).get("engines_agree"))
            if agreement is None and "interp" in results and "jit" in results:agreement=results["interp"]==results["jit"]
            observation = {"function":row.get("validation", {}).get("function", "Recorded mission validation suite"),
                           "arguments":args, "argument_source":"recorded test result keys" if args else "not recorded",
                           "engine_results":results, "revision":int(row["revision"]), "agreement":agreement}
        validation=dict(row.get("validation") or {})
        if "passed" not in validation:
            verdict=validation.get("mission_complete", validation.get("success", validation.get("replay_equivalent")))
            if verdict is not None:validation["passed"]=bool(verdict)
        if "interpreter_jit_agree" not in validation and "engines_agree" in validation:
            validation["interpreter_jit_agree"]=validation["engines_agree"]
        preview_data=dict(proposal) if proposal else None
        if preview_data and preview_data.get("bound_callee"):
            preview_data["dependencies"]=[{"caller":preview_data.get("semantic_handle", "candidate"), "callee":preview_data["bound_callee"]}]
        focus={"handles":handles,"spans":spans,"mapping":mapping}
        if preview_data and preview_data.get("bound_callee"):focus["call_target"]=preview_data["bound_callee"]
        outcome=row.get("outcome")
        if old_highlights.get("annotation"):
            outcome={**(outcome if isinstance(outcome,dict) else {}),"annotation":old_highlights["annotation"]}
        event = {"event_id":str(row.get("id", f"legacy-{seq}")), "frame_id":str(row.get("id", f"legacy-{seq}")),
                 "presentation_sequence":seq, "event_type":event_type, "revision":int(row["revision"]),
                 "session_id":row.get("session_id"), "mission_id":row.get("chapter"), "provenance":row.get("provenance", "Historical evidence"),
                 "source_event_ref":row.get("event_refs", []), "title":row.get("title"), "chapter":row.get("chapter"),
                 "description":row.get("description", ""), "focus":focus,
                 "preview":preview_data, "outcome":outcome, "validation":validation, "observation":observation,
                 "dependencies":list(dependency_by_revision.get(int(row["revision"]), []))}
        events.append(event)
        if event_type == "commit":
            current_revision=int(row["revision"])
            current_code=str(row["code"])
    data = compile_visual_frames(campaign, initial, events, snapshots)
    data["_presentation_events"] = events
    data["_presentation_source"] = {"campaign":dict(campaign), "initial":initial, "snapshots":{str(k):v for k,v in snapshots.items()}}
    return data


VISUAL_EVENT_SCHEMA = {
    "$schema":"https://json-schema.org/draft/2020-12/schema", "title":"BASIC Workspace presentation event", "$id":PRESENTATION_EVENT_SCHEMA,
    "type":"object", "required":["event_id","event_type","provenance"],
    "properties":{"event_id":{"type":"string"},"frame_id":{"type":"string"},"presentation_sequence":{"type":"integer","minimum":1},
      "event_type":{"enum":["initial","selection","preview","rejection","commit","validation","checkpoint","context_reset","reconstruction","observation"]},
      "session_id":{"type":["string","null"]},"mission_id":{"type":["string","null"]},"revision":{"type":["integer","null"],"minimum":0},
      "provenance":{"type":"string"},"source_event_ref":{},"title":{"type":"string"},"chapter":{"type":"string"},"description":{"type":"string"},
      "focus":{"type":"object","properties":{"handles":{"type":"array","items":{"type":"string"}},"call_target":{"type":"string"},"mapping":{"enum":sorted(MAPPINGS)},"spans":{"type":"object","properties":{"ranges":{"type":"array","items":{"type":"object","required":["start_line","start_column","end_line","end_column"],"properties":{"start_line":{"type":"integer","minimum":1},"start_column":{"type":"integer","minimum":0},"end_line":{"type":"integer","minimum":1},"end_column":{"type":"integer","minimum":0},"role":{"type":"string"}},"additionalProperties":True}},"lines":{"type":"array","items":{"type":"integer","minimum":1}},"function_lines":{"type":"array","items":{"type":"integer","minimum":1}},"statement_lines":{"type":"array","items":{"type":"integer","minimum":1}},"expression_lines":{"type":"array","items":{"type":"integer","minimum":1}},"parameter_lines":{"type":"array","items":{"type":"integer","minimum":1}},"declaration_lines":{"type":"array","items":{"type":"integer","minimum":1}},"call_lines":{"type":"array","items":{"type":"integer","minimum":1}}}}}},
      "snapshot":{"type":"string","description":"Rendered display snapshot captured from the authoritative Workspace at commit; never re-imported."},
      "preview":{"type":["object","null"]},"outcome":{"type":["object","string","null"]},"validation":{"type":["object","null"]},"observation":{"type":["object","null"],"properties":{"revision":{"type":["integer","null"]},"function":{"type":"string"},"arguments":{},"engine_results":{"type":"object"},"agreement":{"type":["boolean","null"]}}},"dependencies":{"type":"array"}},
    "additionalProperties":True}

VISUAL_FRAME_JSON_SCHEMA = {
    "$schema":"https://json-schema.org/draft/2020-12/schema", "$id":FRAME_SCHEMA, "title":"BASIC Workspace visual frame v2", "type":"object",
    "required":["schema","version","campaigns"], "properties":{"schema":{"const":FRAME_SCHEMA},"version":{"const":FRAME_VERSION},
      "campaigns":{"type":"array","items":{"type":"object","required":["id","title","frames"],"properties":{"id":{"type":"string"},"title":{"type":"string"},"filename":{"type":"string"},"frames":{"type":"array","items":{"type":"object","required":["id","provenance","revision","event_type","state","code","highlights"],"properties":{"id":{"type":"string"},"source_event_ref":{},"session_id":{"type":["string","null"]},"mission_id":{"type":["string","null"]},"provenance":{"type":"string"},"revision":{"type":"integer","minimum":0},"event_revision":{"type":["integer","null"]},"event_type":{"type":"string"},"state":{"type":"string"},"code":{"type":"string"},"highlights":{"type":"object"},"preview":{"type":["object","null"]},"outcome":{"type":["object","string","null"]},"validation":{"type":["object","null"]},"dependencies":{"type":"array"},"observation":{"type":["object","null"]},"observation_freshness":{"enum":["current","historical","unknown"]}},"additionalProperties":True}}},"additionalProperties":True}},"additionalProperties":True}
}


def render(data: Mapping[str, Any], out: Any) -> None:
    out.write_text(render_html(data),encoding="utf-8")


def render_html(data: Mapping[str, Any]) -> str:
    payload=json.dumps(data,ensure_ascii=False,separators=(",",":")).replace("<","\\u003c")
    return HTML.replace("__FRAME_DATA__",payload)


def load_source_bundle(campaign_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]], dict[int, str]]:
    source=json.loads((campaign_dir/"visual-source.json").read_text(encoding="utf-8"))
    events=[json.loads(line) for line in (campaign_dir/"visual-events.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    snapshots={int(k):v for k,v in source.get("snapshots",{}).items()}
    if not events or events[0].get("event_type")!="initial":
        raise PresentationError("visual event stream must begin with one initial event")
    return source,events,snapshots


class LiveEventHub:
    """Bounded in-process SSE log for visualization frames only."""
    def __init__(self, retention: int=512) -> None:
        self.retention=retention
        self.events: list[tuple[str,dict[str,Any]]] = []
        self.event_ids: set[str] = set()
        self.condition=threading.Condition()
        self.finished=False
        self.error: str | None=None

    def publish(self, frame: dict[str,Any]) -> bool:
        with self.condition:
            if frame["id"] in self.event_ids:return False
            self.event_ids.add(frame["id"])
            self.events.append((str(int(self.events[-1][0])+1 if self.events else 1),frame))
            if len(self.events)>self.retention:self.events.pop(0)
            self.condition.notify_all()
            return True

    def finish(self) -> None:
        with self.condition:self.finished=True;self.condition.notify_all()

    def fail(self, message: str) -> None:
        with self.condition:self.error=message[:500];self.finished=True;self.condition.notify_all()

    def after(self, last_id: int) -> tuple[list[tuple[str,dict[str,Any]]], bool]:
        with self.condition:
            first_id=int(self.events[0][0]) if self.events else 1
            if last_id < first_id-1:raise PresentationError("event retention gap; reconnect from a fresh campaign snapshot")
            newest=int(self.events[-1][0]) if self.events else 0
            if last_id>newest:raise PresentationError("Last-Event-ID is beyond the current presentation stream")
            return [row for row in self.events if int(row[0])>last_id],self.finished


class ReadOnlyVisualServer:
    def __init__(self, html: str, hub: LiveEventHub, port: int=8765) -> None:
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_: Any) -> None:pass
            def do_GET(self) -> None:
                if self.path in ("/","/index.html"):
                    body=owner.html.encode();self.send_response(200);self.send_header("Content-Type","text/html; charset=utf-8");self.send_header("Content-Length",str(len(body)));self.send_header("Cache-Control","no-store");self.end_headers();self.wfile.write(body);return
                if self.path=="/health":
                    body=json.dumps({"ok":True,"frames_published":len(owner.hub.events),"read_only":True}).encode();self.send_response(200);self.send_header("Content-Type","application/json");self.send_header("Content-Length",str(len(body)));self.end_headers();self.wfile.write(body);return
                if self.path!="/events":self.send_error(404);return
                try:last=int(self.headers.get("Last-Event-ID","0"))
                except ValueError:last=0
                self.send_response(200);self.send_header("Content-Type","text/event-stream; charset=utf-8");self.send_header("Cache-Control","no-cache");self.send_header("Connection","keep-alive");self.end_headers()
                while True:
                    try:batch,done=owner.hub.after(last)
                    except PresentationError as ex:
                        self.wfile.write(f"event: stream-error\ndata: {ex}\n\n".encode());self.wfile.flush();return
                    for event_id,frame in batch:
                        payload=json.dumps(frame,ensure_ascii=False,separators=(",",":"))
                        self.wfile.write(f"id: {event_id}\nevent: frame\ndata: {payload}\n\n".encode());self.wfile.flush();last=int(event_id)
                    if owner.hub.error:
                        self.wfile.write(f"event: stream-error\ndata: {owner.hub.error}\n\n".encode());self.wfile.flush();return
                    if done:self.wfile.write(b"event: complete\ndata: complete\n\n");self.wfile.flush();return
                    with owner.hub.condition:owner.hub.condition.wait(timeout=12)
                    try:self.wfile.write(b": keep-alive\n\n");self.wfile.flush()
                    except (BrokenPipeError,ConnectionResetError):return
            def do_POST(self) -> None:self.send_error(405,"Read-only visualization endpoint")
            def do_PUT(self) -> None:self.send_error(405,"Read-only visualization endpoint")
            def do_DELETE(self) -> None:self.send_error(405,"Read-only visualization endpoint")
        self.html=html;self.hub=hub;self.server=ThreadingHTTPServer(("127.0.0.1",port),Handler);self.server.daemon_threads=True
    @property
    def url(self) -> str:return f"http://127.0.0.1:{self.server.server_port}/"
    def serve_forever(self) -> None:self.server.serve_forever()
    def shutdown(self) -> None:self.server.shutdown();self.server.server_close()


def serve_recorded_demo(campaign_dir: Path, port: int=8765, interval: float=0.65, follow: bool=False) -> None:
    source,records,snapshots=load_source_bundle(campaign_dir);campaign=dict(source["campaign"])
    compiler=VisualFrameCompiler(str(campaign["id"]),str(campaign["title"]),str(campaign.get("filename","PROGRAM.bas")),int(source["initial"]["revision"]),str(source["initial"]["code"]),snapshots,list(source["initial"].get("dependencies",[])))
    first=compiler.consume(records[0])
    if first is None:raise PresentationError("initial event was duplicated")
    hub=LiveEventHub();delivery="Loopback live · following append-only presentation events" if follow else "Recorded evidence · progressive delivery simulation"
    initial_data={"schema":FRAME_SCHEMA,"version":FRAME_VERSION,"campaigns":[{**campaign,"delivery_label":delivery,"frames":[first]}]}
    server=ReadOnlyVisualServer(render_html(initial_data),hub,port)
    print(f"Read-only viewer: {server.url}",flush=True);print("GET /events · GET /health · all writes disabled",flush=True)
    event_path=campaign_dir/"visual-events.jsonl"
    event_tail_offset=event_path.stat().st_size
    def publish(record: Mapping[str,Any]) -> None:
        frame=compiler.consume(record)
        if frame is not None:hub.publish(frame)
    def producer() -> None:
        try:
            for record in records[1:]:
                if not follow:time.sleep(max(.01,interval))
                publish(record)
            if not follow:hub.finish();return
            with event_path.open("r",encoding="utf-8") as stream:
                stream.seek(event_tail_offset)
                while True:
                    # Replacing/truncating the append-only journal would make the
                    # stream silently skip or reinterpret events. Surface that as
                    # an interruption instead of guessing where to resume.
                    if event_path.stat().st_size < stream.tell():
                        hub.fail("presentation event journal was truncated; live stream interrupted")
                        return
                    line=stream.readline()
                    if not line:time.sleep(.2);continue
                    publish(json.loads(line))
        except Exception as ex:hub.fail(f"presentation event rejected: {ex}")
    threading.Thread(target=producer,name="visual-event-publisher",daemon=True).start()
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.shutdown()

HTML = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>BASIC semantic replay</title><style>
:root{color-scheme:dark;--bg:#0d1118;--panel:#151c27;--panel2:#1b2532;--line:#2a3747;--text:#e4edf7;--muted:#95a5b8;--blue:#68b7ff;--green:#55d5a1;--yellow:#f2c76c;--red:#ff777f;--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px/1.45 system-ui,-apple-system,Segoe UI,sans-serif;height:100vh;display:flex;flex-direction:column;overflow:hidden}
header{height:54px;display:flex;align-items:center;gap:14px;padding:0 18px;background:#111822;border-bottom:1px solid var(--line);flex:none}header h1{font-size:15px;margin:0;font-weight:650;letter-spacing:.01em}header .tag{color:var(--muted);font-size:12px;border:1px solid var(--line);border-radius:20px;padding:4px 9px}header select{margin-left:auto;background:#202a37;color:var(--text);border:1px solid #38485a;border-radius:6px;padding:7px 10px}
.summary{height:55px;display:flex;align-items:center;gap:16px;padding:7px 18px;border-bottom:1px solid var(--line);background:#101721;flex:none}.mission{font-weight:650;font-size:14px}.sub{color:var(--muted);font-size:12px}.pill{border-radius:15px;padding:4px 9px;font-size:11px;font-weight:700;letter-spacing:.03em;text-transform:uppercase}.pill.committed,.pill.validated{background:#143829;color:#7ce8b8}.pill.baseline,.pill.status{background:#26374a;color:#c5d2df}.pill.proposed,.pill.selected,.pill.checkpoint{background:#423617;color:#ffd978}.pill.rejected{background:#48242a;color:#ff9397}.pill.host{background:#26374a;color:#b7d9ff}
main{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:12px;padding:12px 14px 8px;min-height:0;flex:1}.editor{min-width:0;display:flex;flex-direction:column;border:1px solid #293646;border-radius:10px;background:#10161f;overflow:hidden;box-shadow:0 10px 32px #0003}.editor-head{height:43px;padding:0 14px;display:flex;align-items:center;gap:11px;background:#161f2b;border-bottom:1px solid var(--line);flex:none}.filedot{width:9px;height:9px;border-radius:50%;background:#67b8ff}.file{font-family:var(--mono);color:#b9c7d8;font-size:12px}.rev{margin-left:auto;color:#a8b7c8;font:12px var(--mono)}.editor-scroll{overflow:auto;flex:1;scroll-behavior:smooth;padding:12px 0 20px}.source{font:14px/1.82 var(--mono);min-width:max-content}.code-line{display:grid;grid-template-columns:54px minmax(600px,1fr);padding:0 20px 0 0;border-left:3px solid transparent;min-height:25px}.code-line .ln{user-select:none;text-align:right;padding-right:15px;color:#526174}.code-line .code{white-space:pre;color:#d9e3ef}.code-line.focus{background:#17314a77;border-left-color:var(--blue)}.code-line.change{background:#193a2c88;border-left-color:var(--green)}.code-line.call{background:#16344988;border-left-color:#54c7e7}.code-line.rejected-focus{background:#4823296b;border-left-color:var(--red)}.code-line .proposed-value{color:var(--yellow);background:#41331c;border:1px dashed #a78238;border-radius:4px;padding:1px 5px;margin-left:8px;font:11px system-ui}.semantic-exact{background:#58491e66;border-bottom:2px solid var(--yellow)}.kw{color:#c792ea}.num{color:#f4bf75}.str{color:#a8dba3}.op{color:#8ccaff}.comment{color:#81909e;font-style:italic}.ident{color:#d8e3f0}.call-highlight{color:#7ddafa;text-decoration:underline;text-decoration-color:#3e91a7;text-underline-offset:3px}
.proposal-box{margin:15px 20px 8px 74px;border:1px dashed #927331;border-radius:8px;background:#2a2418;padding:9px 12px;color:var(--yellow);width:max-content;min-width:600px}.proposal-label{font:11px system-ui;text-transform:uppercase;letter-spacing:.08em;color:#eac66f;margin-bottom:4px}.proposal-code{font:13px/1.7 var(--mono);white-space:pre}.proposal-code .plus{color:#89e0b6;margin-right:8px}.reject-box{margin:14px 20px 8px 74px;border:1px solid #714249;border-radius:7px;background:#301b20;padding:10px 13px;color:#ffadb0;width:max-content;max-width:80ch}.annotation{display:inline-block;font:11px system-ui;color:#a9eacb;background:#1d3c2e;border-radius:5px;padding:3px 7px;margin:5px 0 5px 74px}.pane{min-width:0;display:flex;flex-direction:column;gap:10px;overflow:auto}.card{background:var(--panel);border:1px solid #293646;border-radius:9px;padding:12px 13px}.card h2{font-size:11px;text-transform:uppercase;letter-spacing:.09em;color:#93a8bf;margin:0 0 8px}.step-title{font-size:15px;line-height:1.3;font-weight:660;margin:0 0 6px}.step-desc{margin:0;color:#c2ceda;font-size:12px;line-height:1.55}.meta{color:var(--muted);font-size:11px;margin-top:9px}.dep{font:12px/1.6 var(--mono);color:#c8dded}.dep b{color:#69d8b1;font-weight:500}.result-row{display:grid;grid-template-columns:44px 1fr 1fr;gap:5px;font:11px/1.5 var(--mono);padding:4px 0;border-bottom:1px solid #26313d}.result-row.head{color:var(--muted)}.pass{color:#74e5b3}.fail{color:#ff9298}.status-text{font-size:12px;font-weight:650}.focus-chip{display:inline-block;margin:4px 4px 0 0;border:1px solid #344b60;color:#b6d5ee;border-radius:5px;padding:3px 6px;font:10px var(--mono)}details{margin-top:9px;color:var(--muted);font-size:11px}details pre{max-height:220px;overflow:auto;color:#c6d5e4;background:#0d131a;padding:9px;border-radius:5px;white-space:pre-wrap;word-break:break-word;font:10px/1.45 var(--mono)}
footer{height:112px;background:#111822;border-top:1px solid var(--line);padding:9px 14px 8px;flex:none;display:flex;flex-direction:column;gap:8px}.controls{display:flex;align-items:center;gap:8px}.controls button{background:#202a37;color:var(--text);border:1px solid #3a4a5c;border-radius:6px;padding:5px 11px;cursor:pointer}.controls button:hover{border-color:var(--blue)}.controls .play{background:#184b3c;border-color:#2d8366}.controls label{color:var(--muted);font-size:11px;margin-left:6px}.controls input[type=range]{accent-color:#58d6a5}.controls select{background:#202a37;color:var(--text);border:1px solid #38485a;border-radius:5px;padding:4px}.timeline{position:relative;height:22px;margin:0 4px;background:linear-gradient(transparent 9px,#52667d 9px,#52667d 11px,transparent 11px);flex:none}.tick{position:absolute;top:4px;transform:translateX(-50%);width:13px;height:13px;border-radius:50%;padding:0;background:#52667d;border:2px solid #a0b1c2;cursor:pointer}.tick.preview{background:var(--yellow);border-color:#fff0ba;border-radius:3px;transform:translateX(-50%) rotate(45deg)}.tick.commit{background:var(--green);border-color:#d9ffed}.tick.rejection{background:var(--red);border-color:#ffe1e2}.tick.validation{background:var(--blue);border-color:#dbeeff}.tick.context_reset{background:#b896ff;border-color:#eee4ff}.tick.reconstruction{background:#9ca9b7;border-color:#e8eef4}.tick.mission_status{background:#526e85;border-color:#e1edf7}.tick.active{box-shadow:0 0 0 4px #68b7ff55;z-index:2}.tick:focus-visible{outline:2px solid white;outline-offset:4px}.stream-status{font:10px var(--mono);color:var(--muted);margin-left:6px}.stream-status.live{color:var(--green)}.stream-status.error{color:var(--red)}.motion{transition:background-color .2s ease,border-color .2s ease}.hidden{display:none!important}@media(max-width:850px){main{grid-template-columns:1fr}.pane{display:none}header .tag{display:none}.code-line{grid-template-columns:45px minmax(420px,1fr)}footer{height:112px}}
@media(prefers-reduced-motion:reduce){*,*::before,*::after{scroll-behavior:auto!important;transition:none!important;animation:none!important}}
</style></head><body>
<header><span class="filedot"></span><h1>BASIC Workspace · Semantic Replay</h1><span class="tag">Code-first view · committed snapshots</span><span id="streamStatus" class="stream-status">Offline replay</span><select id="campaign"></select></header>
<section class="summary"><span class="mission" id="mission"></span><span class="sub" id="campaignStatus"></span><span class="pill" id="statePill"></span><span class="sub" id="revision"></span></section>
<main><section class="editor"><div class="editor-head"><span class="filedot"></span><span class="file" id="filename">PROGRAM.bas</span><span class="rev" id="revBadge"></span></div><div class="editor-scroll" id="scroll"><div class="source" id="source"></div><div id="proposal"></div><div id="annotation"></div></div></section>
<aside class="pane"><section class="card"><h2>Action</h2><p class="step-title" id="stepTitle"></p><p class="step-desc" id="stepDesc"></p><div class="meta" id="provenance"></div><div id="semanticFocus"></div><div id="diagnostic"></div><details id="evidenceDetails"><summary>Evidence and diagnostics</summary><pre id="evidence"></pre></details></section>
<section class="card"><h2>Function dependency</h2><div class="dep" id="deps"></div></section><section class="card"><h2>MIR observations</h2><div id="results"></div><div class="meta" id="validation"></div></section></aside></main>
<footer><div class="controls"><button id="prev" title="Previous action" aria-label="Previous action">◀</button><button id="play" class="play" aria-label="Play or pause">▶ Play</button><button id="next" title="Next action" aria-label="Next action">▶</button><label for="speed">Speed</label><input id="speed" type="range" min="0.5" max="3" value="1" step="0.5"><span id="speedLabel" class="sub">1×</span><label for="chapter">Mission</label><select id="chapter"></select><span class="sub" id="counter" style="margin-left:auto"></span></div><div id="timeline" class="timeline" aria-label="Significant event timeline"></div><input id="scrub" type="range" min="0" max="0" value="0" step="1" aria-label="Scrub event timeline"></footer>
<script id="frames-data" type="application/json">__FRAME_DATA__</script><script>
const DATA=JSON.parse(document.getElementById('frames-data').textContent);let campaignIndex=0,index=0,timer=null;
const $=id=>document.getElementById(id);const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function active(){return DATA.campaigns[campaignIndex]}function frames(){return active().frames}
function highlighter(line){let out='',i=0;const re=/('[^\n]*|"(?:\\.|[^"\\])*"|\b(?:FUNCTION|END|DIM|FOR|TO|STEP|NEXT|IF|THEN|ELSE|GOTO|GOSUB|RETURN|DATA|READ|RESTORE|SUB|CALL)\b|\b\d+(?:\.\d+)?\b|>=|<=|<>|=|\+|-|\*|\/|\b[A-Za-z_][A-Za-z0-9_$]*\b)/gi;for(const m of line.matchAll(re)){out+=esc(line.slice(i,m.index));const t=m[0];let cls='ident';if(/^['"]/.test(t))cls='str';else if(/^\d/.test(t))cls='num';else if(/^(FUNCTION|END|DIM|FOR|TO|STEP|NEXT|IF|THEN|ELSE|GOTO|GOSUB|RETURN|DATA|READ|RESTORE|SUB|CALL)$/i.test(t))cls='kw';else if(/^(>=|<=|<>|=|\+|-|\*|\/)$/i.test(t))cls='op';out+=`<span class="${cls}">${esc(t)}</span>`;i=m.index+t.length}out+=esc(line.slice(i));return out}
function codeLineHtml(line,lineNo,spans){const ranges=(spans?.ranges||[]).filter(r=>{const a=r.start_line??r.line,b=r.end_line??r.line;return lineNo>=a&&lineNo<=b}).map(r=>({start:lineNo===(r.start_line??r.line)?r.start_column??0:0,end:lineNo===(r.end_line??r.line)?r.end_column??line.length:line.length,role:r.role||'semantic'})).sort((a,b)=>a.start-b.start);let cursor=0,out='';for(const r of ranges){const start=Math.max(cursor,Math.min(line.length,r.start)),end=Math.max(start,Math.min(line.length,r.end));if(start>cursor)out+=highlighter(line.slice(cursor,start));if(end>start)out+=`<span class="semantic-exact" data-semantic-role="${esc(r.role)}">${highlighter(line.slice(start,end))}</span>`;cursor=end}return out+highlighter(line.slice(cursor))}
function setupTimeline(){const fs=frames(),tl=$('timeline');tl.innerHTML='';$('scrub').max=String(Math.max(0,fs.length-1));for(let i=0;i<fs.length;i++){const f=fs[i],b=document.createElement('button');b.className=`tick ${f.event_type||f.state||''}`;b.style.left=`${fs.length<2?0:i*100/(fs.length-1)}%`;b.setAttribute('aria-label',`${f.title}, revision ${f.revision}, ${f.provenance}`);b.title=`${f.title} · r${f.revision} · ${f.provenance}`;b.onclick=()=>show(i);tl.appendChild(b)}}
function setChapterOptions(){const ch=$('chapter');ch.innerHTML='';for(const n of [...new Set(frames().map(f=>f.chapter).filter(Boolean))]){const o=document.createElement('option');o.value=n;o.textContent=n;ch.appendChild(o)}ch.onchange=()=>{const target=frames().findIndex(f=>f.chapter===ch.value);if(target>=0)show(target)}}
function setSelects(){const sel=$('campaign');sel.innerHTML='';DATA.campaigns.forEach((c,i)=>{const o=document.createElement('option');o.value=i;o.textContent=c.title;sel.appendChild(o)});sel.onchange=()=>{campaignIndex=Number(sel.value);index=0;setChapterOptions();setupTimeline();show(0)};setChapterOptions();setupTimeline()}
function show(i){const fs=frames();index=Math.max(0,Math.min(i,fs.length-1));const f=fs[index];$('scrub').value=String(index);$('mission').textContent=f.chapter;$('campaignStatus').textContent=f.mission_status||active().summary||'';$('statePill').textContent=f.state;$('statePill').className=`pill ${f.state}`;$('revision').textContent=`revision ${f.revision}`;$('revBadge').textContent=`BASIC · r${f.revision}`;$('stepTitle').textContent=f.title;$('stepDesc').textContent=f.description;$('provenance').textContent=`Provenance: ${f.provenance}`;$('filename').textContent=active().filename||'PROGRAM.bas';$('counter').textContent=`Action ${index+1} / ${fs.length}`;if($('chapter').value!==f.chapter)$('chapter').value=f.chapter;if(location.hash!==`#${f.id}`)history.replaceState(null,'',`#${f.id}`);
 const proposalData=f.preview||f.proposal||null;const highlights=f.highlights||{},spanData=f.focus?.spans||{},lineKeys=['lines','function_lines','expression_lines','parameter_lines','declaration_lines','statement_lines','assignment_target_lines','literal_lines'],hi=new Set(lineKeys.flatMap(k=>highlights[k]||[])),calls=new Set(highlights.call_lines||[]),codeLines=(f.code||'').replace(/\n$/,'').split('\n');const src=$('source');src.innerHTML='';codeLines.forEach((line,n)=>{const num=n+1,div=document.createElement('div');let cls='code-line';if(hi.has(num))cls+=' '+(f.state==='rejected'?'rejected-focus':(f.state==='committed'||f.state==='validated'?'change':'focus'));if(calls.has(num))cls+=' call';div.className=cls;const call=calls.has(num),callee=proposalData?.bound_callee||f.focus?.call_target||'';div.innerHTML=`<span class="ln">${String(num).padStart(2,' ')}</span><span class="code">${codeLineHtml(line,num,spanData)}${call?`<span class="focus-chip call-highlight">bound call${callee?' → '+esc(callee):''}</span>`:''}</span>`;src.appendChild(div);if(proposalData?.line===num&&proposalData?.new){const chip=document.createElement('span');chip.className='proposed-value';chip.textContent=`proposed ${proposalData.new.trim()}`;div.querySelector('.code').appendChild(chip)}});
 const proposal=$('proposal');proposal.innerHTML='';if(proposalData?.append_lines){const box=document.createElement('div');box.className='proposal-box';box.innerHTML='<div class="proposal-label">Preview only · current committed source remains revision '+f.revision+'</div><div class="proposal-code"></div>';box.querySelector('.proposal-code').innerHTML=proposalData.append_lines.map((l,j)=>`<div class="${(proposalData.call_lines||[]).includes((proposalData.highlight_lines||[])[j])?'call-highlight':''}"><span class="plus">+</span>${highlighter(l)}</div>`).join('');proposal.appendChild(box)}else if(proposalData?.status==='rejected'){const box=document.createElement('div');box.className='reject-box';box.innerHTML=`<b>Denied · no committed source change</b><br>${esc(proposalData.function||'')} · ${esc(proposalData.message||proposalData.diagnostic||'Rejected')}`;proposal.appendChild(box)}
 const annotation=proposalData?.annotation||f.outcome?.annotation;$('annotation').innerHTML=annotation&&f.state==='committed'?`<div class="annotation">${esc(annotation)}</div>`:'';
 const focus=$('semanticFocus');focus.innerHTML='';for(const h of new Set([...(highlights.semantic_handles||[]),...(proposalData?.semantic_handles||[]),...(f.focus?.handles||[])].filter(Boolean))){const s=document.createElement('span');s.className='focus-chip';s.textContent=h;focus.appendChild(s)}if(proposalData?.bound_callee){const s=document.createElement('span');s.className='focus-chip';s.textContent=`calls ${proposalData.bound_callee}`;focus.appendChild(s)}
 const diag=$('diagnostic');diag.innerHTML='';if(proposalData?.status==='rejected'||f.event_type==='rejection'){diag.innerHTML=`<p class="status-text fail">${esc(proposalData?.diagnostic||'Rejected')} · committed revision remains ${f.revision}</p>`}else if(typeof f.validation?.passed==='boolean'){diag.innerHTML=`<p class="status-text ${f.validation.passed?'pass':'fail'}">${f.validation.passed?'✓':'×'} ${f.validation.passed?'Validation passed':'Validation failed'}</p>`}else if(f.validation&&Object.keys(f.validation).length){diag.innerHTML='<p class="status-text">Validation observation recorded; verdict unavailable</p>'}
 const deps=[...(f.dependencies||[]),...(proposalData?.dependencies||[]).map(e=>({...e,preview:true}))],reuse=proposalData?.reused_expression_handles||[];let depHtml=deps.length?deps.map(e=>`<div>${esc(e.caller)}<br>　└ ${e.preview?'proposes':'calls'} <b>${esc(e.callee)}</b></div>`).join(''):'<span class="sub">No dependency recorded at this frame.</span>';if(reuse.length)depHtml+=`<div class="sub">Draft reuses expression handle(s): ${reuse.map(h=>`<code>${esc(h)}</code>`).join(', ')}</div>`;$('deps').innerHTML=depHtml;
 const obs=f.observation||null;if(obs){const freshness=f.observation_freshness||'unknown',freshLabel=freshness==='current'?`Current revision r${obs.revision}`:freshness==='historical'?`Historical result · revision r${obs.revision}`:'Execution revision unknown';const engines=obs.engine_results||{};let rows='';for(const [engine,value] of Object.entries(engines))rows+=`<div class="result-row"><span>${esc(engine)}</span><span>${esc(JSON.stringify(value))}</span></div>`;$('results').innerHTML=`<div class="meta">${esc(freshLabel)}${obs.function?` · ${esc(obs.function)}`:''}</div>${obs.arguments?`<div class="meta">Arguments: ${esc(JSON.stringify(obs.arguments))}</div>`:'<div class="meta">Arguments not recorded</div>'}${rows||'<div class="sub">No engine-specific result payload.</div>'}`;$('validation').textContent=obs.agreement===true?'Interpreter = JIT':obs.agreement===false?'Interpreter/JIT differ':'Agreement not recorded'}else{$('results').innerHTML='<div class="sub">No runtime observation recorded.</div>';$('validation').textContent=''}
 const evidence={provenance:f.provenance,event_refs:f.event_refs||[],mapping:highlights.mapping||null,validation:f.validation||null,checkpoint:f.checkpoint||null,actual_proposal:f.proposal||null};$('evidence').textContent=JSON.stringify(evidence,null,2);for(const t of document.querySelectorAll('.tick'))t.classList.remove('active');document.querySelectorAll('.tick')[index]?.classList.add('active');const focusLine=(highlights.lines||highlights.function_lines||[])[0];if(focusLine){const node=src.children[focusLine-1];if(node)node.scrollIntoView({block:'center',behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'})}else $('scroll').scrollTop=0;
}
function step(delta){show(index+delta)}$('prev').onclick=()=>step(-1);$('next').onclick=()=>step(1);$('scrub').oninput=e=>show(Number(e.target.value));$('speed').oninput=e=>$('speedLabel').textContent=`${e.target.value}×`;$('play').onclick=()=>{if(timer){clearInterval(timer);timer=null;$('play').textContent='▶ Play';return}$('play').textContent='Ⅱ Pause';timer=setInterval(()=>{if(index>=frames().length-1){clearInterval(timer);timer=null;$('play').textContent='▶ Play'}else step(1)},1600/Number($('speed').value))};
document.addEventListener('keydown',e=>{if(['INPUT','SELECT','TEXTAREA'].includes(document.activeElement?.tagName))return;if(e.key==='ArrowLeft')step(-1);else if(e.key==='ArrowRight')step(1);else if(e.code==='Space'){e.preventDefault();$('play').click()}});
function appendLiveFrame(frame){if(DATA.campaigns[campaignIndex].frames.some(f=>f.id===frame.id))return;DATA.campaigns[campaignIndex].frames.push(frame);setupTimeline();setChapterOptions();show(frames().length-1)}
function startEventStream(){if(location.protocol==='file:'||!window.EventSource)return;const stream=new EventSource('/events');stream.addEventListener('open',()=>{$('streamStatus').textContent=active().delivery_label||'Live stream connected';$('streamStatus').className='stream-status live'});stream.addEventListener('frame',e=>{try{appendLiveFrame(JSON.parse(e.data))}catch(_){$('streamStatus').textContent='Invalid presentation frame';$('streamStatus').className='stream-status error'}});stream.addEventListener('stream-error',e=>{$('streamStatus').textContent=`Stream gap: ${e.data}`;$('streamStatus').className='stream-status error'});stream.addEventListener('complete',()=>{$('streamStatus').textContent='Recorded sequence complete';$('streamStatus').className='stream-status live';stream.close()});stream.onerror=()=>{$('streamStatus').textContent='Stream interrupted · reconnecting';$('streamStatus').className='stream-status error'}}
setSelects();const initialId=decodeURIComponent(location.hash.slice(1));let initialCampaign=DATA.campaigns.findIndex(c=>c.frames.some(f=>f.id===initialId));if(initialCampaign>=0){campaignIndex=initialCampaign;$('campaign').value=String(campaignIndex);setChapterOptions();setupTimeline();const initialFrame=frames().findIndex(f=>f.id===initialId);show(initialFrame)}else show(0);if(active().delivery_label)$('streamStatus').textContent=active().delivery_label;startEventStream();
</script></body></html>'''
