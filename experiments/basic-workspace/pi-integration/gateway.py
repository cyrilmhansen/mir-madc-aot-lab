#!/usr/bin/env python3
"""Cycle 16 loopback bridge: Python owns Workspace and mission policy."""
from __future__ import annotations
import argparse, importlib.util, json, socketserver, sys, threading, time, uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def load(name: str, path: Path):
    spec=importlib.util.spec_from_file_location(name,path); mod=importlib.util.module_from_spec(spec)
    assert spec and spec.loader; sys.modules[name]=mod; spec.loader.exec_module(mod); return mod

age=load("pi_cycle16_age",ROOT/"scripts/age-by-id-campaign.py")
senior=load("pi_cycle16_senior",ROOT/"scripts/is-senior-campaign.py")
campaign=load("pi_cycle16_longitudinal",ROOT/"scripts/longitudinal-campaign.py")
from basic_workspace.model import Workspace, WorkspaceError
from basic_workspace.projection import build_projection, projection_semantics
from basic_workspace.mir_execution import MirExecutionService

class Cycle16Gateway:
    def __init__(self, output: Path):
        self.output=output; output.mkdir(parents=True,exist_ok=True)
        self.pi_events=output/"pi-tool-lifecycle.jsonl"; self.visual_events=output/"visual-events.jsonl"
        self.trace=age.Trace(); self.ws=Workspace()
        self.doc,self.aliases,self.seed=age.create_seed(self.ws,self.trace,"cycle16-deterministic-seed")
        rev=self.ws.get_revision(self.doc)
        base=senior.normalized_state(projection_semantics(build_projection(self.ws,self.doc,rev)),self.aliases)
        self.seed_senior=senior.SeniorMissionGateway(self.ws,self.doc,self.aliases,base,senior.make_mission(),self.trace,
            "cycle16-deterministic-seed",function_name="IS_SENIOR",function_handle="is_senior.function")
        self.seed_senior.discover_functions()
        p=self.seed_senior.preview(senior.senior_operation(),rev,"age_by_id.function")
        if not p.get("ok"): raise RuntimeError("could not construct Cycle 14B IS_SENIOR seed")
        if not self.seed_senior.commit(p["transaction_id"]).get("committed"): raise RuntimeError("IS_SENIOR seed commit failed")
        self.aliases=self.seed_senior.aliases
        rev=self.ws.get_revision(self.doc)
        age_base=age.normalize_projection(projection_semantics(build_projection(self.ws,self.doc,rev)),self.aliases)
        age_mission=age.make_mission(55.0); age_mission["mission_id"]="cycle16.seed.age-205-55"
        self.seed_age=age.MissionGateway(self.ws,self.doc,self.aliases,age_base,age_mission,self.trace,"cycle16-deterministic-seed")
        target=self.aliases["people.age.205"]
        p=self.seed_age.preview(target,55.0,rev)
        if not p.get("ok") or not self.seed_age.commit(p["transaction_id"]).get("committed"):
            raise RuntimeError("could not construct the verified revision-4 age-55 seed")
        self.revision=self.ws.get_revision(self.doc)
        self.base=senior.normalized_state(projection_semantics(build_projection(self.ws,self.doc,self.revision)),self.aliases)
        mission=campaign.make_adult_mission(); mission["mission_id"]="cycle16.pi.is-adult.v1"
        self.gateway=senior.SeniorMissionGateway(self.ws,self.doc,self.aliases,self.base,mission,self.trace,
            "cycle16-real-pi-agent",function_name="IS_ADULT",function_handle="is_adult.function")
        self.pi_seen=set(); self.presentation_seq=0
        self.lock=threading.RLock()
        code=self.ws.render_document(self.doc)
        self.initial={"revision":self.revision,"code":code,"dependencies":self.dependencies()}
        bundle={"schema":"basic-workspace.visual-source","version":1,
            "campaign":{"id":"cycle16-pi-is-adult","title":"Cycle 16 · Pi semantic construction","filename":"ADDRESS_BOOK.bas"},
            "initial":self.initial,"snapshots":{str(self.revision):code}}
        (output/"visual-source.json").write_text(json.dumps(bundle,indent=2,ensure_ascii=False)+"\n")
        self.emit_visual({"event_id":"pi-seed-initial","frame_id":"pi-seed-initial","event_type":"initial",
            "presentation_sequence":1,"revision":self.revision,"provenance":"Deterministic Cycle 14B seed · not Pi activity",
            "mission_id":"IS_ADULT · Pi mission","title":"Existing revision-4 program",
            "description":"Deterministic seed from validated typed operations. The Pi agent has not acted yet.",
            "dependencies":self.initial["dependencies"]})
        self.flush_trace()
        (output/"MISSION.json").write_text(json.dumps(mission,indent=2)+"\n")
        profile=campaign.resolve_profile() if hasattr(campaign,"resolve_profile") else None
        if profile is None:
            profile_path=ROOT/"results/semantic-replay/execution-profile.json"
            profile=json.loads(profile_path.read_text())
        (output/"execution-profile.json").write_text(json.dumps(profile,indent=2)+"\n")
        self.append_log(output/"setup.jsonl",{"kind":"deterministic_seed","revision":self.revision,
            "functions":["AGE_BY_ID","IS_SENIOR"],"age_205":55,"pi_activity":False})
        self.dispatched={}; self.committed=False

    @staticmethod
    def append_log(path: Path,row: dict[str,Any]):
        with path.open("a",encoding="utf-8") as f:f.write(json.dumps(row,ensure_ascii=False,separators=(",",":"))+"\n")

    def flush_trace(self): self.trace.write(self.output/"history.jsonl")

    def emit_visual(self,event:dict[str,Any]):
        self.presentation_seq+=1; event["presentation_sequence"]=self.presentation_seq
        self.append_log(self.visual_events,event)

    def doc_functions(self): return self.ws.documents[self.doc].functions
    def function_span(self,symbol_id:str):
        rows=[f for f in self.doc_functions() if f["symbol_id"]==symbol_id]
        if len(rows)!=1:return {"mapping":"unknown","spans":{}}
        r=rows[0]; return {"mapping":"exact_semantic_span","spans":{"function_lines":list(range(r["start_line"],r["end_line"]+1))}}
    def call_lines(self,callee_id:str,scope:dict[str,Any]):
        lines=[]
        for token in self.ws.documents[self.doc].tokens:
            if scope["start_line"]<=token.line<=scope["end_line"] and self.ws.documents[self.doc].token_symbol.get(token.uid)==callee_id:
                lines.append(token.line)
        return sorted(set(lines))
    def dependencies(self):
        raw=projection_semantics(build_projection(self.ws,self.doc,self.ws.get_revision(self.doc)))
        norm=senior.normalized_state(raw,self.aliases); out=[]
        names={f["handle"]:f["name"] for f in norm["functions"]}
        age_fn=next((f for f in norm["functions"] if f["handle"]=="age_by_id.function"),None)
        if age_fn:
            arrays=[a["name"]+"[]" for a in age_fn.get("arrays",[])]
            if arrays:out.append({"caller":"AGE_BY_ID","callee":" · ".join(arrays)})
        for edge in senior.candidate_call_edges(norm):
            out.append({"caller":names.get(edge["caller"],edge["caller"]),"callee":names.get(edge["callee"],edge["callee"])})
        return out

    def record_pi(self,params):
        row=dict(params); event_key=str(row.get("toolCallId") or row.get("request_id") or uuid.uuid4())
        phase=str(row.get("phase","")); key=f"{event_key}:{phase}"
        duplicate=key in self.pi_seen
        if not duplicate:
            self.pi_seen.add(key); row["observed_at_monotonic_ns"]=time.monotonic_ns()
            self.append_log(self.pi_events,row)
        if row.get("type")=="tool_inventory":
            (self.output/"tool-inventory.json").write_text(json.dumps({"source":row.get("source"),"tools":row.get("tools",[])},indent=2)+"\n")
            (self.output/"tool-schemas.json").write_text(json.dumps(row.get("schemas",[]),indent=2)+"\n")
        return {"ok":True,"deduplicated":duplicate,"recorded_key":key}

    def handle(self,method:str,p:dict[str,Any],rid:str):
        if method=="record_pi_event":return self.record_pi(p)
        if method=="get_status":return {"revision":self.ws.get_revision(self.doc),"committed":self.gateway.committed,
            "document_id":self.doc,"function_handles":sorted(k for k in self.gateway.aliases if k.endswith(".function"))}
        if method=="discover_functions":
            result=self.gateway.discover_functions(); self.flush_trace()
            f=self.ws.documents[self.doc].functions[0]
            span=self.function_span(self.aliases["age_by_id.function"])
            self.emit_visual({"event_id":f"pi-discovery-{rid}","frame_id":f"pi-discovery-{rid}","event_type":"selection",
                "revision":self.revision,"session_id":"pi-cycle16","mission_id":"IS_ADULT · Pi mission",
                "provenance":"Genuine Pi semantic-tool action · gateway discovery","source_event_ref":rid,
                "title":"Pi discovers AGE_BY_ID","description":"Pi requested function discovery; the Python gateway returned the live signature and opaque identity.",
                "focus":{"handles":["age_by_id.function"],**span}})
            return {"revision":result["revision"],"functions":[{**x,"symbol_id":x["symbol_id"]} for x in result["functions"]]}
        if method=="inspect_program":
            result=self.gateway.inspect_structure(); self.flush_trace()
            return {"revision":result["revision"],"functions":[{"handle":f["handle"],"name":f["name"],
                "parameters":f["parameters"],"return_type":f["return_type"],"arrays":f.get("arrays",[]),
                "statement_count":len(f.get("statements",[]))} for f in result["structure"]["functions"]],
                "dependencies":self.dependencies()}
        if method=="preview_create_function":
            request={k:p.get(k) for k in ("name","parameters","body")}
            result=self.gateway.preview(request,p.get("expected_revision"),p.get("callee_handle")); self.flush_trace()
            self.dispatched[result.get("transaction_id",rid)]=rid
            last=next((e for e in reversed(self.trace.events) if e.get("event") in ("preview_accepted","transaction_rejected") and e.get("transaction_id")==result.get("transaction_id")),{})
            if result.get("ok"):
                diff=last.get("proposed_diff",""); added=[line[1:] for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++")]
                self.emit_visual({"event_id":f"pi-preview-{rid}","frame_id":f"pi-preview-{rid}","event_type":"preview",
                    "revision":self.revision,"session_id":"pi-cycle16","mission_id":"IS_ADULT · Pi mission",
                    "provenance":"Pi typed proposal · MissionGateway accepted preview","source_event_ref":rid,
                    "title":"IS_ADULT proposal preview","description":"Candidate passed authorization; committed revision 4 remains unchanged until commit.",
                    "focus":{"handles":["is_adult.function"],"mapping":"verified_function_boundary"},
                    "preview":{"status":"accepted","append_lines":added,"bound_callee":"AGE_BY_ID"},
                    "outcome":{"authorized":True,"committed":False}})
            else:
                self.emit_visual({"event_id":f"pi-rejection-{rid}","frame_id":f"pi-rejection-{rid}","event_type":"rejection",
                    "revision":self.revision,"session_id":"pi-cycle16","mission_id":"IS_ADULT · Pi mission",
                    "provenance":"Pi proposal · MissionGateway rejection","source_event_ref":rid,
                    "title":"Proposal rejected","description":result.get("message",result.get("code","rejected")),
                    "focus":{"handles":["age_by_id.function"],"mapping":"unknown"},
                    "preview":{"status":"rejected","function":request.get("name"),"message":result.get("message"),"diagnostic":result.get("code")}})
            return result
        if method=="commit_preview":
            result=self.gateway.commit(p.get("transaction_id")); self.flush_trace()
            if result.get("committed"):
                self.committed=True; self.revision=self.ws.get_revision(self.doc); source=self.ws.render_document(self.doc)
                self.aliases=self.gateway.aliases; span=self.function_span(self.aliases["is_adult.function"])
                scope=next(f for f in self.doc_functions() if f["symbol_id"]==self.aliases["is_adult.function"])
                span["spans"]["call_lines"]=self.call_lines(self.aliases["age_by_id.function"],scope)
                self.emit_visual({"event_id":f"pi-commit-{p.get('transaction_id')}","frame_id":f"pi-commit-{p.get('transaction_id')}","event_type":"commit",
                    "revision":self.revision,"snapshot":source,"session_id":"pi-cycle16","mission_id":"IS_ADULT · Pi mission",
                    "provenance":"Workspace atomic commit · correlated with Pi tool call","source_event_ref":self.dispatched.get(p.get("transaction_id"),rid),
                    "title":"IS_ADULT committed","description":"New function committed at revision 5 with a bound call to AGE_BY_ID.",
                    "focus":{"handles":["is_adult.function","age_by_id.function"],**span},"dependencies":self.dependencies(),
                    "outcome":{"committed":True,"transaction_id":p.get("transaction_id"),"bound_callee":"AGE_BY_ID"}})
            else:
                self.emit_visual({"event_id":f"pi-commit-reject-{rid}","frame_id":f"pi-commit-reject-{rid}","event_type":"rejection",
                    "revision":self.ws.get_revision(self.doc),"provenance":"Workspace/MissionGateway commit rejection",
                    "mission_id":"IS_ADULT · Pi mission","title":"Commit denied","description":result.get("message",result.get("code","rejected")),
                    "preview":{"status":"rejected","message":result.get("message"),"diagnostic":result.get("code")}})
            return result
        if method=="validate_mission":
            requested=p.get("expected_revision")
            result=campaign.adult_validator(self.ws,self.doc,self.gateway,requested)
            replay={"passed":False,"reason":"not_run"}; boundary={"passed":False,"reason":"not_run"}
            if result.get("mission_complete"):
                boundary=campaign.boundary_oracle({},self.seed_senior.committed_request,self.gateway.committed_request)
                stream=campaign.build_stream(self.seed["operation"],self.seed_senior.committed_request,
                    self.gateway.committed_request,sorted(self.gateway.aliases))
                replay_ws,replay_doc,replay_aliases,replay_state=campaign.replay_stream(stream,age.Trace())
                replay_rev=replay_ws.get_revision(replay_doc)
                original=campaign.execute_all(self.ws,self.doc,self.revision,self.gateway.aliases)
                remapped=campaign.execute_all(replay_ws,replay_doc,replay_rev,replay_aliases)
                normalized=senior.normalized_state(projection_semantics(build_projection(self.ws,self.doc,self.revision)),self.gateway.aliases)
                replay={"structural_equivalence":normalized==replay_state,
                    "behavioral_equivalence":original==remapped,"interpreter_jit_agreement":remapped["interp"]==remapped["jit"],
                    "identity_remappings":sum(self.gateway.aliases[k]!=replay_aliases.get(k) for k in self.gateway.aliases),
                    "passed":normalized==replay_state and original==remapped and remapped["interp"]==remapped["jit"]}
                stream_path=self.output/"constructive-operations.json"; stream_path.write_text(json.dumps(stream,indent=2)+"\n")
                (self.output/"equivalence.json").write_text(json.dumps({"mission":result,"boundary":boundary,"replay":replay},indent=2)+"\n")
            result["boundary_oracle"]=boundary; result["replay"]=replay
            self.append_log(self.output/"validation.jsonl",result)
            self.emit_visual({"event_id":f"pi-validation-r{self.revision}-{rid}","frame_id":f"pi-validation-r{self.revision}-{rid}","event_type":"validation",
                "revision":self.revision,"session_id":"pi-cycle16","mission_id":"IS_ADULT · Pi mission",
                "provenance":"Independent host validation · MIR interpreter/JIT","source_event_ref":rid,
                "title":"MIR and replay validation","description":"Independent oracle, threshold boundaries and fresh-workspace replay evaluated after commit.",
                "focus":{"handles":["is_adult.function"],"mapping":"verified_function_boundary"},
                "validation":{"passed":bool(result.get("mission_complete") and boundary.get("passed") and replay.get("passed")),
                    "interpreter_jit_agree":result.get("engines_agree"),"replay":replay},
                "observation":{"function":"IS_ADULT","arguments":[101,205,900,999,2],
                    "engine_results":result.get("observed_results"),"revision":result.get("executed_revision"),
                    "agreement":result.get("engines_agree")},"dependencies":self.dependencies()})
            return result
        raise WorkspaceError("UNKNOWN_TOOL","Unsupported gateway method")

class Handler(socketserver.StreamRequestHandler):
    MAX_LINE=1024*1024
    def handle(self):
        service=self.server.service
        while True:
            raw=self.rfile.readline(self.MAX_LINE+1)
            if not raw:return
            if len(raw)>self.MAX_LINE or not raw.endswith(b"\n"):
                self.wfile.write(b'{"request_id":"","ok":false,"error":{"code":"FRAME_TOO_LARGE"}}\n');self.wfile.flush();return
            try:
                req=json.loads(raw); rid=req.get("request_id")
                if not isinstance(rid,str) or not rid:raise ValueError("request_id is required")
                # Pi may dispatch tool calls concurrently. Keep revision checks,
                # preview bookkeeping and commits serialized against one Workspace.
                with service.lock:
                    result=service.handle(req.get("method"),req.get("params",{}),rid)
                resp={"request_id":rid,"ok":True,"result":result}
            except Exception as ex:
                resp={"request_id":req.get("request_id","") if 'req' in locals() else "","ok":False,
                      "error":{"code":getattr(ex,"code","GATEWAY_ERROR"),"message":str(ex)[:500]}}
                if 'service' in locals():service.flush_trace()
            self.wfile.write(json.dumps(resp,ensure_ascii=False,separators=(",",":")).encode()+b"\n");self.wfile.flush()

class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address=True; daemon_threads=True
    def __init__(self,address,service):self.service=service;super().__init__(address,Handler)

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--output",type=Path,required=True);ap.add_argument("--port",type=int,default=0);args=ap.parse_args()
    service=Cycle16Gateway(args.output)
    with Server(("127.0.0.1",args.port),service) as server:
        print(json.dumps({"ready":True,"host":"127.0.0.1","port":server.server_address[1],"revision":service.revision}),flush=True)
        server.serve_forever()
if __name__=="__main__":main()
