#!/usr/bin/env python3
"""Cycle 16 loopback bridge: Python owns Workspace and mission policy."""
from __future__ import annotations
import argparse, importlib.util, json, socketserver, sys, threading, time, uuid
import math
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT))
from pi_lifecycle import completion_states

def load(name: str, path: Path):
    spec=importlib.util.spec_from_file_location(name,path); mod=importlib.util.module_from_spec(spec)
    assert spec and spec.loader; sys.modules[name]=mod; spec.loader.exec_module(mod); return mod

age=load("pi_cycle16_age",ROOT/"scripts/age-by-id-campaign.py")
senior=load("pi_cycle16_senior",ROOT/"scripts/is-senior-campaign.py")
campaign=load("pi_cycle16_longitudinal",ROOT/"scripts/longitudinal-campaign.py")
from basic_workspace.model import Workspace, WorkspaceError
from basic_workspace.projection import build_projection, projection_semantics
from basic_workspace.mir_execution import MirExecutionService
from draft_protocol import DraftProtocol, DraftError

class Cycle16Gateway:
    def __init__(self, output: Path, authoring_mode: str = "atomic", mission_kind: str = "adult"):
        if authoring_mode not in {"atomic", "incremental"}: raise ValueError("unsupported authoring mode")
        if mission_kind not in {"adult", "category"}: raise ValueError("unsupported mission kind")
        self.authoring_mode=authoring_mode
        self.mission_kind=mission_kind
        self.function_name="IS_ADULT" if mission_kind=="adult" else "AGE_CATEGORY"
        self.function_handle="is_adult.function" if mission_kind=="adult" else "age_category.function"
        self.required_callee_handle="age_by_id.function"
        self.allowed_parameters=["ID"]
        self.discoverable_functions={"age_by_id.function","is_senior.function"} if mission_kind=="category" else {"age_by_id.function"}
        self.output=output; output.mkdir(parents=True,exist_ok=True)
        self.pi_events=output/"pi-tool-lifecycle.jsonl"; self.visual_events=output/"visual-events.jsonl"
        self.gateway_timings=output/"gateway-tool-timings.jsonl"
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
        mission=campaign.make_adult_mission()
        mission["mission_id"]=f"cycle18.pi.age-category.{authoring_mode}.v1" if mission_kind=="category" else f"cycle17.pi.is-adult.{authoring_mode}.v1"
        if mission_kind=="category":
            mission["objective"]="Add AGE_CATEGORY(ID): unknown ID -> -1; age 0..17 -> 0; 18..49 -> 1; 50..130 -> 2. Preserve AGE_BY_ID, IS_SENIOR and data."
            mission["enforcement"]["allowed_function"]={"name":"AGE_CATEGORY","parameter_count":1,"parameter_type":"numeric"}
            mission["functional_goal"]={"classes":{"unknown":-1,"0..17":0,"18..49":1,"50..130":2}}
        self.gateway=senior.SeniorMissionGateway(self.ws,self.doc,self.aliases,self.base,mission,self.trace,
            f"cycle18-category-{authoring_mode}-agent" if mission_kind=="category" else f"cycle17-{authoring_mode}-agent",
            function_name=self.function_name,function_handle=self.function_handle,
            required_callee_handle=self.required_callee_handle,
            discoverable_function_handles=self.discoverable_functions)
        self.pi_seen=set(); self.presentation_seq=0
        self.session_id=f"pi-cycle18-category-{authoring_mode}" if mission_kind=="category" else f"pi-cycle17-{authoring_mode}"
        self.mission_title=f"AGE_CATEGORY · {authoring_mode} arm" if mission_kind=="category" else f"IS_ADULT · {authoring_mode} arm"
        self.draft_protocol=DraftProtocol(); self.draft_id=None; self.draft_transactions={}
        self.draft_log=output/"draft-operations.jsonl"
        self.lock=threading.RLock()
        code=self.ws.render_document(self.doc)
        self.initial={"revision":self.revision,"code":code,"dependencies":self.dependencies()}
        bundle={"schema":"basic-workspace.visual-source","version":1,
            "campaign":{"id":f"cycle18-{authoring_mode}-age-category" if mission_kind=="category" else f"cycle17-{authoring_mode}-is-adult",
                "title":f"Cycle 18 · {authoring_mode.title()} AGE_CATEGORY construction" if mission_kind=="category" else f"Cycle 17 · {authoring_mode.title()} semantic construction","filename":"ADDRESS_BOOK.bas"},
            "initial":self.initial,"snapshots":{str(self.revision):code}}
        (output/"visual-source.json").write_text(json.dumps(bundle,indent=2,ensure_ascii=False)+"\n")
        self.emit_visual({"event_id":"pi-seed-initial","frame_id":"pi-seed-initial","event_type":"initial",
            "presentation_sequence":1,"revision":self.revision,"provenance":"Deterministic Cycle 14B seed · not Pi activity",
            "mission_id":self.mission_title,"title":"Existing revision-4 program",
            "description":"Deterministic seed from validated typed operations. The Pi agent has not acted yet.",
            "mission_status":f"Agent mission pending · committed seed revision {self.revision}",
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

    def category_replay_stream(self, request: dict[str,Any]) -> dict[str,Any]:
        return {"schema":"basic-workspace.constructive-metafile","version":1,
            "execution_profile_id":campaign.PROFILE_ID,
            "portable_handles":["age_by_id.function","is_senior.function","people.age.205",self.function_handle],
            "operations":[
                {"operation":"create_numeric_function","portable_handle":"age_by_id.function","arguments":self.seed["operation"]},
                {"operation":"create_numeric_function","portable_handle":"is_senior.function","callee_handle":"age_by_id.function","arguments":self.seed_senior.committed_request},
                {"operation":"edit_assignment_expression","target_handle":"people.age.205","expression":{"kind":"number","value":55.0}},
                {"operation":"create_numeric_function","portable_handle":self.function_handle,"callee_handle":"age_by_id.function","arguments":request}]}

    @staticmethod
    def replay_category_stream(stream:dict[str,Any]):
        if stream.get("schema")!="basic-workspace.constructive-metafile" or stream.get("version")!=1:
            raise WorkspaceError("REPLAY_SCHEMA","Unknown constructive stream")
        ws=Workspace(); doc,aliases,seed=age.create_seed(ws,age.Trace(),"cycle18-category-replay")
        operations=stream.get("operations",[])
        if len(operations)!=4 or operations[0].get("arguments")!=seed["operation"]:
            raise WorkspaceError("REPLAY_OPERATION_SEQUENCE","AGE_CATEGORY replay seed differs")
        if operations[0].get("portable_handle")!="age_by_id.function":
            raise WorkspaceError("REPLAY_HANDLE_MISSING","AGE_BY_ID portable handle is missing")
        for index,operation in enumerate(operations[1:],1):
            revision=ws.get_revision(doc)
            if operation["operation"]=="create_numeric_function":
                callee=operation.get("callee_handle")
                if callee!="age_by_id.function" or callee not in aliases:
                    raise WorkspaceError("REPLAY_HANDLE_MISSING",f"Cannot resolve call handle {callee!r}")
                function_handle=operation.get("portable_handle")
                function_name={"is_senior.function":"IS_SENIOR","age_category.function":"AGE_CATEGORY"}.get(function_handle)
                if function_name is None: raise WorkspaceError("REPLAY_HANDLE_MISSING",f"Unknown function handle {function_handle!r}")
                resolved=senior.resolve_function_handles(operation["arguments"],aliases,{callee})
                applied=ws.apply_transaction(doc,revision,[{"operation":"create_numeric_function",**resolved}])
                raw=projection_semantics(build_projection(ws,doc,applied["revision"]))
                aliases=senior.aliases_for_new_function(raw,aliases,function_name,function_handle)
            elif operation["operation"]=="edit_assignment_expression":
                target=operation.get("target_handle")
                if target!="people.age.205" or target not in aliases:
                    raise WorkspaceError("REPLAY_HANDLE_MISSING","Age assignment handle is unresolved")
                ws.apply_transaction(doc,revision,[{"operation":"edit_assignment_expression",
                    "statement_id":aliases[target],"expression":operation["expression"]}])
            else: raise WorkspaceError("REPLAY_OPERATION_UNSUPPORTED","Unsupported category replay operation")
        return ws,doc,aliases,senior.normalized_state(projection_semantics(build_projection(ws,doc,ws.get_revision(doc))),aliases)

    @staticmethod
    def category_observations(workspace,doc,revision,aliases,executor=None):
        executor=executor or MirExecutionService(timeout=12)
        ids=[101,205,900,999,2]
        return {engine:{str(entity_id):{
            "age":executor.execute_function(workspace,doc,revision,aliases["age_by_id.function"],[entity_id],engine)["result"],
            "senior":executor.execute_function(workspace,doc,revision,aliases["is_senior.function"],[entity_id],engine)["result"],
            "category":executor.execute_function(workspace,doc,revision,aliases["age_category.function"],[entity_id],engine)["result"]}
            for entity_id in ids} for engine in ("interp","jit")}

    def category_boundary_oracle(self,request:dict[str,Any]):
        cases={}; executor=MirExecutionService(timeout=12)
        for boundary_age in (0,17,18,49,50,130):
            ws=Workspace(); doc,aliases,seed=age.create_seed(ws,age.Trace(),f"age-category-boundary-{boundary_age}")
            revision=seed["revision"]
            senior_op={"operation":"create_numeric_function",**senior.resolve_function_handles(
                self.seed_senior.committed_request,aliases,{"age_by_id.function"})}
            added=ws.apply_transaction(doc,revision,[senior_op]); revision=added["revision"]
            raw=projection_semantics(build_projection(ws,doc,revision))
            aliases=senior.aliases_for_new_function(raw,aliases,"IS_SENIOR","is_senior.function")
            edited=ws.apply_transaction(doc,revision,[{"operation":"edit_assignment_expression",
                "statement_id":aliases["people.age.205"],"expression":{"kind":"number","value":float(boundary_age)}}])
            revision=edited["revision"]
            category_op={"operation":"create_numeric_function",**senior.resolve_function_handles(
                request,aliases,{"age_by_id.function"})}
            added=ws.apply_transaction(doc,revision,[category_op]); revision=added["revision"]
            raw=projection_semantics(build_projection(ws,doc,revision))
            aliases=senior.aliases_for_new_function(raw,aliases,"AGE_CATEGORY","age_category.function")
            observed={engine:{
                "age":executor.execute_function(ws,doc,revision,aliases["age_by_id.function"],[205],engine)["result"],
                "category":executor.execute_function(ws,doc,revision,aliases["age_category.function"],[205],engine)["result"],
                "unknown":executor.execute_function(ws,doc,revision,aliases["age_category.function"],[999],engine)["result"]}
                for engine in ("interp","jit")}
            expected={"age":float(boundary_age),"category":0.0 if boundary_age<18 else 1.0 if boundary_age<50 else 2.0,"unknown":-1.0}
            cases[str(boundary_age)]={"observed":observed,"expected":expected,
                "matches":all(value==expected for value in observed.values()),"engines_agree":observed["interp"]==observed["jit"]}
        passed=all(row["matches"] and row["engines_agree"] for row in cases.values())
        return {"cases":cases,"passed":passed,"isolated_workspaces":True}

    def validate_category(self,requested_revision:int):
        revision=self.ws.get_revision(self.doc)
        if requested_revision!=revision:
            return {"reliable":False,"code":"STALE_VALIDATION_REVISION","mission_complete":False,
                "requested_revision":requested_revision,"workspace_revision":revision,"executed_revision":None}
        if not self.gateway.committed:
            return {"reliable":True,"phase":"pre-create","mission_complete":False,"revision":revision,
                "diagnostics":["AGE_CATEGORY not committed"]}
        try:
            observed=self.category_observations(self.ws,self.doc,revision,self.gateway.aliases)
            normalized=senior.normalized_state(projection_semantics(build_projection(self.ws,self.doc,revision)),self.gateway.aliases)
        except (WorkspaceError,KeyError) as exc:
            return {"reliable":False,"code":getattr(exc,"code","PROJECTION_INVALID"),"message":str(exc),
                "mission_complete":False,"executed_revision":revision}
        expected={"101":{"age":25.0,"senior":0.0,"category":1.0},
            "205":{"age":55.0,"senior":1.0,"category":2.0},
            "900":{"age":53.0,"senior":1.0,"category":2.0},
            "999":{"age":-1.0,"senior":0.0,"category":-1.0},
            "2":{"age":-1.0,"senior":0.0,"category":-1.0}}
        engines_agree=observed["interp"]==observed["jit"]
        values_match=all(observed[engine]==expected for engine in observed)
        edges=senior.candidate_call_edges(normalized)
        dependency={"caller":self.function_handle,"callee":self.required_callee_handle} in edges
        base_unchanged=all(senior.find_function(normalized,row["handle"])==row
            for row in self.gateway.base_snapshot["functions"])
        complete=bool(values_match and engines_agree and dependency and base_unchanged)
        result={"schema":"basic-workspace.age-category-validation","version":1,"reliable":True,
            "phase":"post-create","revision":revision,"requested_revision":requested_revision,
            "workspace_revision":revision,"executed_revision":revision,"observed_results":observed,
            "expected_results":expected,"expectation_source":"independent host-owned mission oracle",
            "engines_agree":engines_agree,"values_match":values_match,
            "existing_functions_unchanged":base_unchanged,"age_by_id_call_bound":dependency,
            "mission_complete":complete,"diagnostics":[] if complete else ["Category oracle or invariant check failed"]}
        boundary=self.category_boundary_oracle(self.gateway.committed_request) if complete else {"passed":False,"reason":"mission oracle failed"}
        stream=self.category_replay_stream(self.gateway.committed_request)
        replay={"passed":False,"reason":"not_run"}
        if complete:
            replay_ws,replay_doc,replay_aliases,replay_state=self.replay_category_stream(stream)
            replay_revision=replay_ws.get_revision(replay_doc)
            replay_observed=self.category_observations(replay_ws,replay_doc,replay_revision,replay_aliases)
            replay_normalized=senior.normalized_state(projection_semantics(build_projection(replay_ws,replay_doc,replay_revision)),replay_aliases)
            remapped=sum(self.gateway.aliases.get(handle)!=replay_aliases.get(handle) for handle in self.gateway.aliases)
            replay={"structural_equivalence":normalized==replay_state==replay_normalized,
                "behavioral_equivalence":observed==replay_observed,
                "interpreter_jit_agreement":replay_observed["interp"]==replay_observed["jit"],
                "identity_remappings":remapped,
                "passed":normalized==replay_state==replay_normalized and observed==replay_observed and replay_observed["interp"]==replay_observed["jit"] and boundary.get("passed")}
            (self.output/"constructive-operations.json").write_text(json.dumps(stream,indent=2)+"\n")
            (self.output/"equivalence.json").write_text(json.dumps({"mission":result,"boundary":boundary,"replay":replay},indent=2)+"\n")
        result["boundary_oracle"]=boundary; result["replay"]=replay
        return result

    @staticmethod
    def append_log(path: Path,row: dict[str,Any]):
        with path.open("a",encoding="utf-8") as f:f.write(json.dumps(row,ensure_ascii=False,separators=(",",":"))+"\n")

    def flush_trace(self): self.trace.write(self.output/"history.jsonl")

    def record_gateway_timing(self,request:dict[str,Any],elapsed_ms:float):
        params=request.get("params") or {}; transport=request.get("transport") or {}; method=request.get("method")
        tool_methods={"discover_functions","inspect_program","preview_create_function","commit_preview",
            "validate_mission","begin_function_draft","apply_draft_operations","inspect_function_draft","preview_function_draft"}
        self.append_log(self.gateway_timings,{"request_id":request.get("request_id"),
            "tool_call_id":transport.get("tool_call_id"),"method":method,"elapsed_ms":round(elapsed_ms,3),
            "operation_count":len(params.get("operations",[])) if isinstance(params.get("operations"),list) else None,
            "agent_tool":method in tool_methods})

    def emit_visual(self,event:dict[str,Any]):
        self.presentation_seq+=1; event["presentation_sequence"]=self.presentation_seq
        self.append_log(self.visual_events,event)

    def doc_functions(self): return self.ws.documents[self.doc].functions
    def function_name_for_handle(self,handle:str)->str:
        symbol_id=self.aliases.get(handle)
        if symbol_id is None or symbol_id not in self.ws.documents[self.doc].symbols:return handle
        return self.ws.documents[self.doc].symbols[symbol_id].name
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

    def render_draft_lines(self, request: dict[str, Any]) -> list[str]:
        function_names={symbol: self.ws.documents[self.doc].symbols[symbol].name
            for handle,symbol in self.aliases.items() if handle.endswith(".function") and symbol in self.ws.documents[self.doc].symbols}
        def expr(row):
            kind=row["kind"]
            if kind=="number": return str(int(row["value"])) if float(row["value"]).is_integer() else str(row["value"])
            if kind=="local_ref": return row["name"]
            if kind=="call": return function_names.get(self.aliases.get(row["function_handle"]),row["function_handle"])+"("+", ".join(expr(x) for x in row["arguments"])+")"
            if kind=="unary": return row["operator"]+expr(row["operand"])
            if kind=="binary": return f"({expr(row['left'])} {row['operator']} {expr(row['right'])})"
            raise ValueError("unsupported draft expression in display projection")
        def block(rows, indent=2):
            lines=[]; prefix=" "*indent
            for row in rows:
                if row["kind"]=="assign": lines.append(f"{prefix}{request['name']} = {expr(row['expression'])}")
                else:
                    lines.append(f"{prefix}IF {expr(row['condition'])} THEN")
                    lines.extend(block(row.get("then",[]),indent+2))
                    if "else" in row:
                        lines.append(f"{prefix}ELSE"); lines.extend(block(row["else"],indent+2))
                    lines.append(f"{prefix}END IF")
            return lines
        return [f"FUNCTION {request['name']}({', '.join(request['parameters'])})",*block(request["body"]),"END FUNCTION"]

    def record_draft_event(self, kind: str, *, draft_id: str, row: dict[str, Any]):
        self.append_log(self.draft_log,{"schema":"basic-workspace.draft-activity","version":1,
            "event":kind,"draft_id":draft_id,"mission_id":self.gateway.mission_id,
            "workspace_revision":self.ws.get_revision(self.doc),**row})

    def draft_diagnostic(self, error: DraftError, draft_id: str | None = None):
        rev=self.ws.get_revision(self.doc); draft_rev=0
        if draft_id and draft_id in self.draft_protocol.drafts: draft_rev=self.draft_protocol.get(draft_id).revision
        response=error.diagnostic(draft_rev)
        response["workspace_revision"]=rev
        response["workspace_changed"]=False
        if draft_id:
            self.record_draft_event("operation_rejected",draft_id=draft_id,
                row={"draft_revision":draft_rev,"diagnostic":response})
        return response

    def record_pi(self,params):
        row=dict(params); event_key=str(row.get("toolCallId") or row.get("request_id") or uuid.uuid4())
        # Pi emits both start and end for one toolCallId. When there is no explicit
        # phase, include the event type in the idempotency key so the completion is
        # not mistaken for a duplicate start.
        phase=str(row.get("phase") or row.get("type", "")); key=f"{event_key}:{phase}"
        duplicate=key in self.pi_seen
        if not duplicate:
            self.pi_seen.add(key); row["observed_at_monotonic_ns"]=time.monotonic_ns()
            self.append_log(self.pi_events,row)
        if row.get("type")=="tool_inventory":
            (self.output/"tool-inventory.json").write_text(json.dumps({"source":row.get("source"),"tools":row.get("tools",[])},indent=2)+"\n")
            (self.output/"tool-schemas.json").write_text(json.dumps(row.get("schemas",[]),indent=2)+"\n")
        return {"ok":True,"deduplicated":duplicate,"recorded_key":key}

    @staticmethod
    def typed_shape_error(request: Any) -> dict[str,Any] | None:
        """Syntactic diagnostics only; mission authorization remains in SeniorMissionGateway."""
        def issue(code,path,expected,received):
            return {"ok":False,"code":code,"path":path,"expected":expected,
                    "received_kind":type(received).__name__ if received is not None else "missing"}
        def expr(node,path,depth=0):
            if depth>3:return issue("INVALID_TYPED_EXPRESSION",path,{"max_depth":4},node)
            if not isinstance(node,dict):return issue("INVALID_TYPED_EXPRESSION",path,{"kind":"object"},node)
            kind=node.get("kind")
            if kind=="number":
                if set(node)!={"kind","value"} or isinstance(node.get("value"),bool) or not isinstance(node.get("value"),(int,float)) or not math.isfinite(float(node["value"])):
                    return issue("INVALID_TYPED_EXPRESSION",path,{"kind":"number","required":["kind","value"]},kind)
            elif kind=="local_ref":
                if set(node)!={"kind","name"} or not isinstance(node.get("name"),str):
                    return issue("INVALID_TYPED_EXPRESSION",path,{"kind":"local_ref","required":["kind","name"]},kind)
            elif kind=="binary":
                if set(node)!={"kind","operator","left","right"}:
                    return issue("INVALID_TYPED_EXPRESSION",path,{"kind":"binary","required":["kind","operator","left","right"]},kind)
                if node.get("operator") not in ("+","-","*","/","=","<>","<","<=",">",">="):
                    return issue("INVALID_TYPED_EXPRESSION",path+".operator",{"enum":["+","-","*","/","=","<>","<","<=",">",">="]},node.get("operator"))
                return expr(node["left"],path+".left",depth+1) or expr(node["right"],path+".right",depth+1)
            elif kind=="call":
                if set(node)!={"kind","function_handle","arguments"}:
                    return issue("INVALID_TYPED_EXPRESSION",path,{"kind":"call","required":["kind","function_handle","arguments"]},kind)
                if (not isinstance(node.get("function_handle"),str) or not isinstance(node.get("arguments"),list)
                        or not 1<=len(node["arguments"])<=8):
                    return issue("INVALID_TYPED_EXPRESSION",path,{"kind":"call","argument_count":"1..8"},kind)
                return expr(node["arguments"][0],path+".arguments[0]",depth+1)
            else:return issue("INVALID_TYPED_EXPRESSION",path,{"kind":["number","local_ref","binary","call"]},kind)
            return None
        def body(items,path,depth=0):
            if depth>2:return issue("INVALID_TYPED_STATEMENT",path,{"max_if_nesting":2},items)
            if not isinstance(items,list) or len(items)>64:return issue("INVALID_TYPED_STATEMENT",path,{"type":"array","maxItems":64},items)
            for i,node in enumerate(items):
                p=f"{path}[{i}]"
                if not isinstance(node,dict):return issue("INVALID_TYPED_STATEMENT",p,{"kind":"object"},node)
                kind=node.get("kind")
                if kind=="assign":
                    if set(node)!={"kind","target","expression"}:return issue("INVALID_TYPED_STATEMENT",p,{"kind":"assign","required":["kind","target","expression"]},kind)
                    target=node.get("target")
                    if target!={"kind":"result"}:return issue("INVALID_TYPED_STATEMENT",p+".target",{"kind":"result"},target)
                    error=expr(node.get("expression"),p+".expression")
                    if error:return error
                elif kind=="if":
                    if set(node)-{"kind","condition","then","else"} or "condition" not in node or not isinstance(node.get("then"),list) or ("else" in node and not isinstance(node["else"],list)):
                        return issue("INVALID_TYPED_STATEMENT",p,{"kind":"if","required":["kind","condition","then"],"optional":["else"]},kind)
                    error=expr(node["condition"],p+".condition")
                    if error:return error
                    error=body(node["then"],p+".then",depth+1)
                    if error:return error
                    if "else" in node:
                        error=body(node["else"],p+".else",depth+1)
                        if error:return error
                else:return issue("INVALID_TYPED_STATEMENT",p+".kind",{"enum":["assign","if"]},kind)
            return None
        if not isinstance(request,dict):return issue("INVALID_TYPED_FUNCTION","arguments",{"type":"object"},request)
        if set(request)!={"name","parameters","body"} or not isinstance(request.get("name"),str) or not isinstance(request.get("parameters"),list):
            return issue("INVALID_TYPED_FUNCTION","arguments",{"required":["name","parameters","body"]},request)
        statements=request.get("body")
        if not isinstance(statements,list) or not statements:return issue("INVALID_TYPED_STATEMENT","body",{"type":"non-empty array"},statements)
        return body(statements,"body")

    def handle(self,method:str,p:dict[str,Any],rid:str):
        if method=="record_pi_event":return self.record_pi(p)
        if method=="record_agent_status":
            state=str(p.get("state","unknown")); info=p.get("info") if isinstance(p.get("info"),dict) else {}
            revision=self.ws.get_revision(self.doc)
            labels={"working":"Agent working","waiting_for_tool":"Agent waiting for tool",
                "no_observable_progress":"No Pi event observed; agent state unresolved",
                "agent_turn_ended":"Pi agent turn ended; session settlement not yet observed",
                "agent_session_completed":"Pi reports agent session settled; waiting for process exit"}
            title=labels.get(state,"Pi lifecycle: "+state.replace("_"," "))
            self.append_log(self.output/"pi-viewer-status.jsonl",{"record_type":"viewer_status",
                "state":state,"revision":revision,"info":info,"observed_monotonic_ns":time.monotonic_ns()})
            self.emit_visual({"event_id":f"pi-live-status-{uuid.uuid4()}","frame_id":f"pi-live-status-{uuid.uuid4()}",
                "event_type":"mission_status","revision":revision,"session_id":self.session_id,
                "mission_id":self.mission_title,"provenance":"Host observation of Pi JSON event arrivals",
                "title":title,"description":info.get("description",title),"mission_status":title,
                "lifecycle":{"state":state,"info":info,"workspace_revision":revision},
                "outcome":{"agent_commit":self.gateway.committed}})
            return {"ok":True,"state":state,"revision":revision}
        draft_methods={"begin_function_draft","apply_draft_operations","inspect_function_draft","preview_function_draft"}
        if method in draft_methods and self.authoring_mode!="incremental":
            return {"ok":False,"code":"AUTHORING_MODE_MISMATCH","message":"Draft tools are disabled for the atomic arm",
                    "authoritative_workspace_changed":False}
        if method=="preview_create_function" and self.authoring_mode!="atomic":
            return {"ok":False,"code":"AUTHORING_MODE_MISMATCH","message":"Whole-function construction is disabled for the incremental arm",
                    "authoritative_workspace_changed":False}
        if method=="get_status":return {"revision":self.ws.get_revision(self.doc),"committed":self.gateway.committed,
            "document_id":self.doc,"function_handles":sorted(k for k in self.gateway.aliases if k.endswith(".function")),
            "authoring_mode":self.authoring_mode,"draft_id":self.draft_id}
        if method=="finalize_mission":
            revision=self.ws.get_revision(self.doc); validation=p.get("validation") or {}
            lifecycle=p.get("pi_lifecycle") if isinstance(p.get("pi_lifecycle"),dict) else {}
            validation_ok=bool(validation.get("mission_complete") and validation.get("engines_agree") and
                (validation.get("boundary_oracle") or {}).get("passed") and
                (validation.get("replay") or {}).get("passed"))
            mission_events=[e for e in self.trace.events if e.get("mission_id")==self.gateway.mission_id]
            if self.gateway.committed or any(e.get("event")=="preview_accepted" for e in mission_events):
                authorization_status="authorized"
            elif any(e.get("event")=="transaction_rejected" for e in mission_events):
                authorization_status="denied"
            else:
                authorization_status="not_attempted"
            states=completion_states(committed=self.gateway.committed,validation=p.get("validation") if isinstance(p.get("validation"),dict) else None,
                timed_out=bool(p.get("timed_out")),exit_code=p.get("pi_exit_code"),
                agent_end_seen=bool(lifecycle.get("agent_end_seen")),
                agent_settled_seen=bool(lifecycle.get("agent_settled_seen")),
                pending_tool_count=len(lifecycle.get("pending_tools",{})) if isinstance(lifecycle.get("pending_tools"),dict) else len(lifecycle.get("pending_tool_ids",[])),
                authorization_status=authorization_status)
            status=(f"Program {states['semantic_program']} · authorization {states['mission_authorization']} · "
                f"commit {states['program_commit']} · "
                f"host validation {states['host_validation']} · Pi session {states['pi_agent_session']} · "
                f"launcher {states['launcher_process']} · revision {revision}")
            self.append_log(self.output/"pi-viewer-status.jsonl",{"record_type":"completion_classification",
                "completion_states":states,"revision":revision,"agent_lifecycle":lifecycle,
                "validation_revision":validation.get("executed_revision")})
            self.trace.emit("session_completed",phase=f"cycle17-{self.authoring_mode}-agent",actor="host_observer",
                mission_id=self.gateway.mission_id,revision=revision,committed=self.gateway.committed,
                timed_out=bool(p.get("timed_out")),mission_status=status,completion_states=states)
            self.flush_trace()
            self.emit_visual({"event_id":f"pi-mission-status-r{revision}","frame_id":f"pi-mission-status-r{revision}",
                "event_type":"mission_status","revision":revision,"session_id":self.session_id,
                "mission_id":self.mission_title,"provenance":"Host observation of actual Pi/gateway outcome",
                "title":"Mission outcome","description":status,"mission_status":status,
                "lifecycle":{"completion_states":states,"agent":lifecycle,
                    "validation_revision":validation.get("executed_revision")},
                "outcome":{"agent_commit":self.gateway.committed,"validation":validation or None,
                    "timed_out":bool(p.get("timed_out"))}})
            return {"revision":revision,"committed":self.gateway.committed,"mission_status":status,"completion_states":states}
        if method=="discover_functions":
            result=self.gateway.discover_functions(); self.flush_trace()
            f=self.ws.documents[self.doc].functions[0]
            span=self.function_span(self.aliases["age_by_id.function"])
            self.emit_visual({"event_id":f"pi-discovery-{rid}","frame_id":f"pi-discovery-{rid}","event_type":"selection",
                "revision":self.revision,"session_id":self.session_id,"mission_id":self.mission_title,
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
        if method=="begin_function_draft":
            try:
                if self.required_callee_handle not in self.gateway.discovered_handles:
                    raise DraftError("FUNCTION_NOT_DISCOVERED","Discover callable functions before beginning a draft")
                expected=p.get("expected_revision")
                if expected!=self.ws.get_revision(self.doc):
                    raise DraftError("STALE_WORKSPACE_REVISION","Draft base revision must match the live Workspace",
                        path="expected_revision",expected=self.ws.get_revision(self.doc),received=expected)
                discovered=[row for row in self.gateway.discover_functions().get("functions",[]) if row["handle"]==p.get("callee_handle")]
                if len(discovered)!=1:
                    raise DraftError("FUNCTION_NOT_DISCOVERED","Draft call target must be discovered and permitted by this mission",
                        path="callee_handle",expected=sorted(self.discoverable_functions),received=p.get("callee_handle"))
                signature=discovered[0]
                result=self.draft_protocol.begin(mission_id=self.gateway.mission_id,base_revision=expected,
                    name=p.get("name"),parameters=p.get("parameters"),callee_handle=p.get("callee_handle"),
                    allowed_name=self.function_name,allowed_parameters=self.allowed_parameters,
                    allowed_callee_handle=self.required_callee_handle,allowed_callee_arity=signature["parameter_count"])
                self.draft_id=result["draft_id"]
                self.record_draft_event("draft_started",draft_id=self.draft_id,row={"draft_revision":0,"base_revision":expected})
                self.emit_visual({"event_id":f"draft-start-{self.draft_id}","frame_id":f"draft-start-{self.draft_id}",
                    "event_type":"selection","revision":self.revision,"session_id":self.session_id,
                    "mission_id":self.mission_title,"provenance":"Genuine Pi draft operation · no Workspace mutation",
                    "title":f"Incremental {self.function_name} draft started","description":f"A temporary draft is open. The authoritative BASIC remains at revision {self.revision}.",
                    "focus":{"handles":[self.required_callee_handle],"mapping":"verified_function_boundary"},
                    "outcome":{"draft_id":self.draft_id,"draft_revision":0,"committed":False}})
                return result
            except DraftError as error:return self.draft_diagnostic(error)
        if method=="apply_draft_operations":
            draft_id=p.get("draft_id"); before=self.ws.get_revision(self.doc)
            try: result=self.draft_protocol.apply_batch(draft_id,p.get("expected_draft_revision"),p.get("operations"))
            except DraftError as error: return self.draft_diagnostic(error,draft_id)
            if not result.get("ok"):
                self.record_draft_event("operation_batch_rejected",draft_id=str(draft_id or "missing"),
                    row={"draft_revision":result.get("draft_revision"),"operations":p.get("operations"),"diagnostic":result})
                self.emit_visual({"event_id":f"draft-reject-{uuid.uuid4().hex}","frame_id":f"draft-reject-{uuid.uuid4().hex}",
                    "event_type":"rejection","revision":before,"session_id":self.session_id,
                    "mission_id":self.mission_title,"provenance":"Draft protocol validation · no Workspace mutation",
                    "title":"Draft operation rejected","description":f"{result.get('code')} · {result.get('message','')}",
                    "preview":{"status":"rejected","diagnostic":result},
                    "outcome":{"draft_changed":False,"workspace_changed":False}})
                return result
            d=self.draft_protocol.get(draft_id)
            progress=result.pop("_progress_states",[])
            self.record_draft_event("operations_applied",draft_id=draft_id,row={"draft_revision":d.revision,
                "operations":p["operations"],"operation_results":result["operation_results"],
                "workspace_revision":before,"progress_event_count":len(progress),
                "single_pi_tool_call":p.get("toolCallId")})
            for index,step in enumerate(progress,1):
                request=step["request"]; lines=self.render_draft_lines(request)
                event_id=f"draft-r{step['draft_revision']}-{uuid.uuid4().hex}"
                self.emit_visual({"event_id":event_id,"frame_id":event_id,
                    "event_type":"preview","revision":before,"session_id":self.session_id,
                    "mission_id":self.mission_title,"provenance":"Ordered operation replay from one genuine Pi batch · uncommitted draft",
                    "title":f"Draft step {index}/{len(progress)} · {step['operation_kind']}",
                    "description":f"Applied draft operation {step['operation_id']} at draft revision {step['draft_revision']}; these steps arrived together in one Pi tool call. Committed Workspace remains revision {before}.",
                    "focus":{"handles":["draft."+h for h in step["created_handles"]],"mapping":"unknown"},
                    "preview":{"status":"draft","function":request["name"],"append_lines":lines,
                        "bound_callee":self.function_name_for_handle(self.required_callee_handle),"draft_revision":step["draft_revision"],
                        "reused_expression_handles":step["reused_expression_handles"],
                        "operation_id":step["operation_id"],"operation_kind":step["operation_kind"]},
                    "outcome":{"committed":False,"draft_revision":step["draft_revision"],"workspace_revision":before}})
            return result
        if method=="inspect_function_draft":
            try:
                draft_id=p.get("draft_id"); summary=self.draft_protocol.inspect(draft_id)
                summary["body"]=self.draft_protocol.function_request(draft_id)["body"] if self.draft_protocol.get(draft_id).blocks["root"] else []
                return summary
            except DraftError as error:return self.draft_diagnostic(error,p.get("draft_id"))
        if method=="preview_function_draft":
            draft_id=p.get("draft_id")
            try:
                d=self.draft_protocol.get(draft_id)
                if p.get("expected_draft_revision")!=d.revision:
                    raise DraftError("STALE_DRAFT_REVISION","Preview must name the current draft revision",
                        expected=d.revision,received=p.get("expected_draft_revision"))
                current=self.ws.get_revision(self.doc)
                if p.get("expected_revision")!=d.base_revision or current!=d.base_revision:
                    raise DraftError("STALE_WORKSPACE_REVISION","Draft is stale against the authoritative Workspace",
                        expected=d.base_revision,received=current)
                request=self.draft_protocol.function_request(draft_id)
                result=self.gateway.preview(request,p["expected_revision"],d.callee_handle)
                self.flush_trace()
                if result.get("ok"):
                    d.accepted_preview={"transaction_id":result["transaction_id"],"draft_revision":d.revision,
                                        "base_revision":d.base_revision}
                    self.draft_transactions[result["transaction_id"]]=draft_id
                    self.record_draft_event("candidate_preview_accepted",draft_id=draft_id,row={
                        "draft_revision":d.revision,"transaction_id":result["transaction_id"],"base_revision":d.base_revision})
                    lines=self.render_draft_lines(request)
                    self.emit_visual({"event_id":f"draft-preview-{result['transaction_id']}","frame_id":f"draft-preview-{result['transaction_id']}",
                        "event_type":"preview","revision":d.base_revision,"session_id":self.session_id,
                        "mission_id":self.mission_title,"provenance":"MissionGateway accepted complete draft candidate",
                        "title":f"Complete {self.function_name} candidate preview accepted","description":"Full draft passed the existing MissionGateway; committed Workspace remains unchanged until commit.",
                        "focus":{"handles":[self.required_callee_handle],"mapping":"verified_function_boundary"},
                        "preview":{"status":"accepted","function":request["name"],"append_lines":lines,
                            "bound_callee":self.function_name_for_handle(d.callee_handle),"draft_revision":d.revision},
                        "outcome":{"authorized":True,"committed":False,"transaction_id":result["transaction_id"]}})
                else:
                    self.record_draft_event("candidate_preview_rejected",draft_id=draft_id,row={
                        "draft_revision":d.revision,"result":result,"base_revision":d.base_revision})
                result.update({"draft_id":draft_id,"draft_revision":d.revision,"workspace_revision":current,
                               "authoritative_workspace_changed":False})
                return result
            except DraftError as error:return self.draft_diagnostic(error,draft_id)
        if method=="preview_create_function":
            request={k:p.get(k) for k in ("name","parameters","body")}
            shape_error=self.typed_shape_error(request)
            if shape_error:
                txid="tx_"+uuid.uuid4().hex; revision=self.ws.get_revision(self.doc)
                shape_error.update({"reliable":True,"revision":revision,"revision_unchanged":True,"transaction_id":txid})
                self.trace.emit("operation_proposed",phase=f"cycle17-{self.authoring_mode}-agent",actor="llm_tool",
                    mission_id=self.gateway.mission_id,transaction_id=txid,base_revision=p.get("expected_revision"),
                    operation_envelope={"operation":"create_numeric_function","arguments":request,"state":"proposed"})
                self.trace.emit("transaction_rejected",phase=f"cycle17-{self.authoring_mode}-agent",actor="mission_gateway",
                    mission_id=self.gateway.mission_id,transaction_id=txid,base_revision=p.get("expected_revision"),
                    resulting_revision=revision,code=shape_error["code"],path=shape_error["path"],
                    expected=shape_error["expected"],received_kind=shape_error["received_kind"],authoritative_state_unchanged=True)
                self.flush_trace()
                self.emit_visual({"event_id":f"pi-rejection-{rid}","frame_id":f"pi-rejection-{rid}",
                    "event_type":"rejection","revision":revision,"session_id":self.session_id,"mission_id":self.mission_title,
                    "provenance":"Pi typed request · Workspace schema diagnostic","source_event_ref":rid,
                    "title":"Malformed typed request","description":f"{shape_error['code']} at {shape_error['path']}",
                    "preview":{"status":"rejected","diagnostic":shape_error}})
                return shape_error
            result=self.gateway.preview(request,p.get("expected_revision"),p.get("callee_handle")); self.flush_trace()
            self.dispatched[result.get("transaction_id",rid)]=rid
            last=next((e for e in reversed(self.trace.events) if e.get("event") in ("preview_accepted","transaction_rejected") and e.get("transaction_id")==result.get("transaction_id")),{})
            if result.get("ok"):
                diff=last.get("proposed_diff",""); added=[line[1:] for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++")]
                self.emit_visual({"event_id":f"pi-preview-{rid}","frame_id":f"pi-preview-{rid}","event_type":"preview",
                    "revision":self.revision,"session_id":self.session_id,"mission_id":self.mission_title,
                    "provenance":"Pi typed proposal · MissionGateway accepted preview","source_event_ref":rid,
                    "title":f"{self.function_name} proposal preview","description":f"Candidate passed authorization; committed revision {self.revision} remains unchanged until commit.",
                    "focus":{"handles":[self.function_handle],"mapping":"verified_function_boundary"},
                    "preview":{"status":"accepted","append_lines":added,"bound_callee":self.function_name_for_handle(self.required_callee_handle)},
                    "outcome":{"authorized":True,"committed":False}})
            else:
                self.emit_visual({"event_id":f"pi-rejection-{rid}","frame_id":f"pi-rejection-{rid}","event_type":"rejection",
                    "revision":self.revision,"session_id":self.session_id,"mission_id":self.mission_title,
                    "provenance":"Pi proposal · MissionGateway rejection","source_event_ref":rid,
                    "title":"Proposal rejected","description":result.get("message",result.get("code","rejected")),
                    "focus":{"handles":["age_by_id.function"],"mapping":"unknown"},
                    "preview":{"status":"rejected","function":request.get("name"),"message":result.get("message"),"diagnostic":result.get("code")}})
            return result
        if method=="commit_preview":
            txid=p.get("transaction_id"); draft_id=self.draft_transactions.get(txid)
            if draft_id:
                d=self.draft_protocol.get(draft_id)
                accepted=d.accepted_preview or {}
                if d.committed or accepted.get("transaction_id")!=txid or accepted.get("draft_revision")!=d.revision or d.base_revision!=self.ws.get_revision(self.doc):
                    result={"ok":False,"committed":False,"code":"STALE_DRAFT_PREVIEW",
                        "message":"Draft changed or its base Workspace revision is stale; preview again before commit",
                        "revision":self.ws.get_revision(self.doc),"draft_revision":d.revision,
                        "authoritative_workspace_changed":False}
                    self.record_draft_event("draft_commit_rejected",draft_id=draft_id,row={"transaction_id":txid,
                        "draft_revision":d.revision,"result":result})
                    return result
            result=self.gateway.commit(txid); self.flush_trace()
            if result.get("committed"):
                self.committed=True; self.revision=self.ws.get_revision(self.doc); source=self.ws.render_document(self.doc)
                if draft_id:
                    d=self.draft_protocol.get(draft_id); d.committed=True
                    d.accepted_preview={**(d.accepted_preview or {}),"committed_revision":self.revision}
                    (self.output/"draft-operation-history.json").write_text(json.dumps({
                        "schema":"basic-workspace.incremental-draft-history","version":1,
                        "draft_id":draft_id,"mission_id":d.mission_id,"base_revision":d.base_revision,
                        "final_draft_revision":d.revision,"committed_revision":self.revision,
                        "operations":d.history,"constructive_metafile_is_separate":True},indent=2)+"\n")
                    self.record_draft_event("draft_committed",draft_id=draft_id,row={"draft_revision":d.revision,
                        "transaction_id":txid,"committed_revision":self.revision})
                self.aliases=self.gateway.aliases; span=self.function_span(self.aliases[self.function_handle])
                scope=next(f for f in self.doc_functions() if f["symbol_id"]==self.aliases[self.function_handle])
                span["spans"]["call_lines"]=self.call_lines(self.aliases[self.required_callee_handle],scope)
                self.emit_visual({"event_id":f"pi-commit-{p.get('transaction_id')}","frame_id":f"pi-commit-{p.get('transaction_id')}","event_type":"commit",
                    "revision":self.revision,"snapshot":source,"session_id":self.session_id,"mission_id":self.mission_title,
                    "provenance":"Workspace atomic commit · correlated with Pi tool call","source_event_ref":self.dispatched.get(p.get("transaction_id"),rid),
                    "title":f"{self.function_name} committed","description":f"New function committed at revision {self.revision} with a bound call to {self.function_name_for_handle(self.required_callee_handle)}.",
                    "mission_status":f"Agent commit revision {self.revision} · host validation pending",
                    "focus":{"handles":[self.function_handle,self.required_callee_handle],**span},"dependencies":self.dependencies(),
                    "outcome":{"committed":True,"transaction_id":p.get("transaction_id"),"bound_callee":self.function_name_for_handle(self.required_callee_handle)}})
            else:
                self.emit_visual({"event_id":f"pi-commit-reject-{rid}","frame_id":f"pi-commit-reject-{rid}","event_type":"rejection",
                    "revision":self.ws.get_revision(self.doc),"provenance":"Workspace/MissionGateway commit rejection",
                    "mission_id":self.mission_title,"title":"Commit denied","description":result.get("message",result.get("code","rejected")),
                    "preview":{"status":"rejected","message":result.get("message"),"diagnostic":result.get("code")}})
            return result
        if method=="validate_mission":
            agent_requested=bool(p.get("toolCallId"))
            requested=p.get("expected_revision")
            if self.mission_kind=="category":
                result=self.validate_category(requested)
                boundary=result.get("boundary_oracle",{"passed":False,"reason":"not_run"})
                replay=result.get("replay",{"passed":False,"reason":"not_run"})
            else:
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
            passed=bool(result.get("mission_complete") and boundary.get("passed") and replay.get("passed"))
            status=(f"Host validation passed · revision {self.revision}" if passed
                    else f"Host validation failed · revision {self.revision}")
            self.emit_visual({"event_id":f"pi-validation-r{self.revision}-{rid}","frame_id":f"pi-validation-r{self.revision}-{rid}","event_type":"validation",
                "revision":self.revision,"session_id":self.session_id,"mission_id":self.mission_title,
                "provenance":("Pi-requested validation executed by Python host · MIR interpreter/JIT" if agent_requested
                              else "Independent host verification · MIR interpreter/JIT"),"source_event_ref":rid,
                "title":("Pi requests MIR and replay validation" if agent_requested else "Host independently verifies MIR and replay"),
                "description":("Pi invoked the validation tool; the Python host ran the mission oracle, threshold boundaries and fresh-workspace replay after commit."
                               if agent_requested else "The host independently repeated the oracle, threshold boundary and fresh-workspace replay checks after the Pi tool completed."),
                "mission_status":status,
                "focus":{"handles":[self.function_handle],"mapping":"verified_function_boundary"},
                "validation":{"passed":passed,
                    "interpreter_jit_agree":result.get("engines_agree"),"replay":replay},
                "observation":{"function":self.function_name,"arguments":[101,205,900,999,2],
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
                transport=req.get("transport",{})
                if not isinstance(transport,dict) or set(transport)-{"tool_call_id"}:
                    raise ValueError("transport metadata may contain only tool_call_id")
                call_id=transport.get("tool_call_id")
                if call_id is not None and (not isinstance(call_id,str) or not call_id or len(call_id)>256):
                    raise ValueError("transport.tool_call_id must be a non-empty string of at most 256 characters")
                # Pi may dispatch tool calls concurrently. Keep revision checks,
                # preview bookkeeping and commits serialized against one Workspace.
                started=time.perf_counter_ns()
                with service.lock:
                    result=service.handle(req.get("method"),req.get("params",{}),rid)
                service.record_gateway_timing(req,(time.perf_counter_ns()-started)/1_000_000)
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
    ap=argparse.ArgumentParser();ap.add_argument("--output",type=Path,required=True);ap.add_argument("--port",type=int,default=0)
    ap.add_argument("--authoring-mode",choices=("atomic","incremental"),default="atomic")
    ap.add_argument("--mission-kind",choices=("adult","category"),default="adult");args=ap.parse_args()
    service=Cycle16Gateway(args.output,args.authoring_mode,args.mission_kind)
    with Server(("127.0.0.1",args.port),service) as server:
        print(json.dumps({"ready":True,"host":"127.0.0.1","port":server.server_address[1],"revision":service.revision}),flush=True)
        server.serve_forever()
if __name__=="__main__":main()
