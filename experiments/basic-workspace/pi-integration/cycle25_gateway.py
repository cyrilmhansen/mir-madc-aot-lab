#!/usr/bin/env python3
"""Cycle 25: one contract-bounded typed IF insertion using the shared kernel."""
from __future__ import annotations
import argparse, copy, importlib.util, json, math, sys, threading, time, uuid
from pathlib import Path
from typing import Any
HERE=Path(__file__).resolve().parent; ROOT=HERE.parent
sys.path[:0]=[str(ROOT),str(HERE)]
from basic_workspace.model import Workspace, WorkspaceError
from basic_workspace.projection import build_projection, projection_semantics
from basic_workspace.portable_replay import replay_constructive_stream
from basic_workspace.mir_execution import MirExecutionService
from transaction_kernel import SemanticTransactionKernel
from gateway import Server
from cycle20_gateway import Cycle20Gateway, senior, _calls
from pi_lifecycle import completion_states

C24=HERE/"results/cycle24-dependency-propagation"
M1=C24/"mission-1-real-agent-01"; M2=C24/"mission-2-real-agent-01"
CONTRACT=HERE/"results/cycle25-structural-edit/contracts/score-class-append-if.json"
PROFILE="basic-workspace.numeric-composition.v1"
INPUTS=(-100,-1,0,1,19,20,39,40,44,45,49,50,51,60,100,200)
NEW_STATEMENT_HANDLE="score_class.statement.category50"

def read(path): return json.loads(Path(path).read_text(encoding="utf-8"))
def write(path,value): Path(path).write_text(json.dumps(value,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
def rows(path): return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
def call_handles(value):
    out=set()
    def walk(v):
        if isinstance(v,dict):
            if v.get("kind")=="call" and isinstance(v.get("function_handle"),str):out.add(v["function_handle"])
            for child in v.values():walk(child)
        elif isinstance(v,list):
            for child in v:walk(child)
    walk(value); return out

class Cycle25Gateway(Cycle20Gateway):
    """Reuse Cycle20's verified replay, Workspace, kernel and bridge lifecycle."""
    def __init__(self, output:Path, contract_path:Path=CONTRACT, *, baseline_stream_path:Path|None=None,
                 baseline_history_path:Path|None=None, baseline_validation_path:Path|None=None):
        output=output.resolve(); output.mkdir(parents=True,exist_ok=True)
        # Cycle20's verified stream loader reconstructs revision 6 from the
        # genuine Cycle24 Mission 1 stream. Its contract is only used to verify
        # that committed checkpoint, then the authentic revision-7 edit is
        # replayed and checked against Mission 2's commit evidence.
        m1_stream=baseline_stream_path or M1/"constructive-operations.json"
        m1_history=baseline_history_path or M1/"history.jsonl"
        m1_validation=baseline_validation_path or M1/"mission-3-validation-host.json"
        super().__init__(output/"baseline-bootstrap", contract_path=C24/"contracts/mission-2-threshold45.json",
            baseline_stream_path=m1_stream,baseline_history_path=m1_history,
            baseline_validation_path=m1_validation)
        self.output=output; self.trace_path=output/"history.jsonl"; self.visual_path=output/"visual-events.jsonl"
        self.timing_path=output/"gateway-tool-timings.jsonl"; self.pi_path=output/"pi-tool-lifecycle.jsonl"
        self.session_id=f"cycle25-{output.name}"; self.mission_id="cycle25.score-class-fourth-category.v1"
        self.contract=read(contract_path); self.contract_path=contract_path
        if self.contract.get("schema")!="basic-workspace.typed-structural-edit-contract" or self.contract.get("version")!=1:
            raise WorkspaceError("MISSION_CONTRACT_VERSION","Unsupported structural edit contract")
        if self.contract.get("execution_profile_id")!=PROFILE or self.contract.get("base_document_revision")!=7:
            raise WorkspaceError("MISSION_CONTRACT_INVALID","Structural mission must bind to revision 7 and the numeric profile")
        full_stream=read(C24/"constructive-operations.json")
        first_stream=read(m1_stream)
        second_stream=read(M2/"constructive-operations.json")
        if full_stream.get("operations")!=second_stream.get("operations") or full_stream.get("operations")[:-1]!=first_stream.get("operations"):
            raise WorkspaceError("BASELINE_STREAM_MISMATCH","Cycle 24 committed stream lineage is inconsistent")
        final_edit=full_stream["operations"][-1]
        if final_edit.get("operation")!="edit_numeric_literals" or final_edit.get("mission_id")!="cycle24.raise-passing-threshold45.v1":
            raise WorkspaceError("BASELINE_OPERATION_MISMATCH","Expected authentic Cycle 24 threshold edit as operation six")
        edit_ops=self._workspace_operations_for_edits(final_edit["edits"],self.aliases)
        applied=self.ws.apply_transaction(self.doc,6,edit_ops)
        if applied["revision"]!=7: raise WorkspaceError("BASELINE_REVISION_MISMATCH","Cycle 24 edit did not reconstruct revision 7")
        raw=projection_semantics(build_projection(self.ws,self.doc,7)); self.baseline=senior.normalized_state(raw,self.aliases)
        c24_events=rows(M2/"history.jsonl")
        commits=[e for e in c24_events if e.get("event")=="transaction_committed" and e.get("resulting_revision")==7]
        if len(commits)!=1 or commits[0].get("semantic_snapshot")!=self.baseline:
            raise WorkspaceError("BASELINE_SEMANTIC_MISMATCH","Reconstructed revision 7 differs from genuine Cycle 24 commit snapshot")
        c24_validation=read(M2/"validation.json")
        if c24_validation.get("mission_complete") is not True or c24_validation.get("revision")!=7:
            raise WorkspaceError("BASELINE_VALIDATION_MISSING","Cycle 24 host validation is not complete at revision 7")
        observations=self._observe(self.ws,self.doc,7,self.aliases)
        recorded=c24_validation.get("observed_results",{})
        if not all(observations[e].get(x)==r for e in observations for x,r in recorded.get(e,{}).items()):
            raise WorkspaceError("BASELINE_BEHAVIOR_MISMATCH","Reconstructed program differs from recorded interpreter/JIT evidence")
        if observations["interp"]!=observations["jit"]: raise WorkspaceError("BASELINE_ENGINE_MISMATCH","Baseline MIR engines disagree")
        self.committed_operations=copy.deepcopy(full_stream["operations"])
        self.aliases=dict(self.aliases); self.base_aliases=dict(self.aliases); self.baseline_aliases=dict(self.aliases)
        if len(self.aliases)!=17 or sorted(self.aliases)!=sorted(full_stream["portable_handles"]):
            raise WorkspaceError("BASELINE_IDENTITY_MISMATCH","Revision-7 baseline must resolve all 17 portable handles")
        self.base_revision=7; self.baseline_observed=observations; self.initial_code=self.ws.render_document(self.doc)
        self.initial_identity_map=[{"portable_handle":h,"workspace_id":v,"remapped":True} for h,v in sorted(self.aliases.items())]
        self.revision=7; self.committed=False; self.discovered=set(); self.discovered_statements=set(); self.seq=0
        self.lock=threading.RLock(); self.pi_seen=set(); self.executor=MirExecutionService(timeout=20)
        self.transactions=SemanticTransactionKernel(self.ws,self.doc); self.pending_request_ids={}
        self.output.mkdir(parents=True,exist_ok=True)
        self.write_json(output/"MISSION.json",self.contract)
        self.write_json(output/"execution-profile.json",read(ROOT/"results/semantic-replay/execution-profile.json"))
        self.write_json(output/"baseline-reconstruction.json",{"schema":"basic-workspace.cycle25-baseline","version":1,
            "source_stream":str(C24/"constructive-operations.json"),"starting_document_empty":True,
            "resulting_revision":7,"normalized_semantic_equivalence":True,"identity_remappings":17,
            "existing_score_class_implementation_preserved":True,"mir_interpreter_jit_agree":True,
            "recorded_commit_and_validation_match":True,"portable_identity_mapping":self.initial_identity_map})
        write(output/"baseline-observations.json",{"revision":7,"source":"host replay of genuine Cycle 24 stream",
            "observed_results":observations,"dependencies":self.dependencies()})
        write(output/"visual-source.json",{"schema":"basic-workspace.visual-source","version":1,
            "campaign":{"id":"cycle25-structural-edit","title":"Cycle 25 · typed structural maintenance","filename":"SCORES.bas"},
            "initial":{"revision":7,"code":self.initial_code,"dependencies":self.dependencies()},"snapshots":{"7":self.initial_code}})
        self._emit({"event_type":"initial","revision":7,"snapshot":self.initial_code,
            "provenance":"Host deterministic replay of authentic Cycle 24 operations","title":"Verified revision-7 baseline",
            "description":"Six committed operations reconstructed from an empty Workspace. No source text was imported.",
            "dependencies":self.dependencies(),"focus":{"handles":["score_class.function"],"mapping":"verified_function_boundary"}})
        self._history("program_reconstructed","host_deterministic_replay",revision=7,operations=6,identity_remappings=17,
            semantic_equivalence=True,recorded_behavior_match=True)

    def write_json(self,path,value): write(path,value)
    def _history(self,event,actor,**fields):
        row={"sequence":len(rows(self.trace_path))+1 if self.trace_path.exists() else 1,"event":event,"actor":actor,
             "mission_id":self.mission_id,"observed_monotonic_ns":time.monotonic_ns(),**fields}
        self._append(self.trace_path,row)
    @staticmethod
    def _append(path,row):
        Path(path).parent.mkdir(parents=True,exist_ok=True)
        with Path(path).open("a",encoding="utf-8") as f:f.write(json.dumps(row,ensure_ascii=False,separators=(",",":"))+"\n")
    def _emit(self,event):
        self.seq+=1;event.setdefault("event_id",f"cycle25-{self.seq}-{uuid.uuid4().hex[:8]}")
        event.setdefault("session_id",self.session_id);event.setdefault("mission_id",self.mission_id)
        event.setdefault("presentation_sequence",self.seq);self._append(self.visual_path,event)
    def flush_trace(self): return None
    def record_gateway_timing(self,request,elapsed_ms):
        method=request.get("method"); transport=request.get("transport") or {}
        self._append(self.timing_path,{"request_id":request.get("request_id"),"tool_call_id":transport.get("tool_call_id"),
          "method":method,"agent_tool":method in {"discover_functions","inspect_program","preview_structural_edit","commit_preview","validate_mission"},
          "elapsed_ms":round(elapsed_ms,3),"observed_monotonic_ns":time.monotonic_ns()})
    def record_pi(self,p):
        key=str(p.get("toolCallId") or p.get("request_id") or uuid.uuid4())+":"+str(p.get("type"))
        duplicate=key in self.pi_seen
        if not duplicate:self.pi_seen.add(key);self._append(self.pi_path,{**p,"observed_monotonic_ns":time.monotonic_ns()})
        if p.get("type")=="tool_inventory":
            write(self.output/"tool-inventory.json",{"source":p.get("source"),"tools":p.get("tools",[])})
            write(self.output/"tool-schemas.json",p.get("schemas",[]))
        return {"ok":True,"deduplicated":duplicate}
    def _observe(self,ws,doc,revision,aliases,inputs=INPUTS):
        result={"interp":{},"jit":{}}
        for engine in result:
            for x in inputs:
                row={}
                for handle,key in (("clamp_score.function","clamp_score"),("is_passing.function","is_passing"),("score_class.function","score_class")):
                    row[key]=self.executor.execute_function(ws,doc,revision,aliases[handle],[x],engine)["result"]
                result[engine][str(x)]=row
        return result
    def _expected(self,inputs=INPUTS):
        result={}
        for x in inputs:
            n=min(50,max(0,x)); result[str(x)]={"clamp_score":float(n),"is_passing":float(n>=45),
                "score_class":float(0 if n<20 else 1 if n<45 else 2 if n<50 else 3)}
        return result
    def dependencies(self,state=None):
        state=self.baseline if state is None else state
        names={f["handle"]:f["name"] for f in state["functions"]}
        edges=senior.candidate_call_edges(state)
        return [{"caller":names.get(e["caller"],e["caller"]),"callee":names.get(e["callee"],e["callee"])}
            for e in edges]
    def _find(self,state,handle): return senior.find_function(state,handle)
    def discover(self):
        self.discovered={"clamp_score.function","is_passing.function","score_class.function"}
        result=[]
        for handle in sorted(self.discovered):
            fn=self._find(self.baseline,handle); sid=self.aliases[handle]
            result.append({"handle":handle,"symbol_id":sid,"name":fn["name"],"parameters":fn["parameters"],"return_type":fn["return_type"]})
        self._history("symbol_discovered","pi_model_tool",revision=7,functions=result)
        self._emit({"event_type":"selection","revision":7,"provenance":"Genuine Pi function discovery tool call",
            "title":"Functions discovered","description":"The agent requested the live callable identities for SCORE_CLASS and its two dependencies.",
            "focus":{"handles":["score_class.function","clamp_score.function","is_passing.function"],"mapping":"verified_function_boundary"},
            "dependencies":self.dependencies()})
        return {"revision":self.ws.get_revision(self.doc),"functions":result}
    def inspect(self):
        if "score_class.function" not in self.discovered:raise WorkspaceError("FUNCTION_NOT_DISCOVERED","Discover functions before inspection")
        fn=self._find(self.baseline,"score_class.function")
        anchors=[]
        for handle,sid in self.aliases.items():
            if handle.startswith("score_class.statement."):
                anchors.append({"statement_handle":handle,"statement_id":sid,"kind":"result_assignment" if handle.endswith(".3") else "assignment"})
        if "score_class.statement.3" not in self.aliases:raise WorkspaceError("BOUNDARY_ANCHOR_MISSING","Verified result epilogue handle is missing")
        self.discovered_statements.add("score_class.statement.3")
        result={"revision":7,"functions":self.baseline["functions"],"function_handle":"score_class.function",
            "statement_handles":anchors,"structural_insertion_anchors":[{"kind":"before_result_epilogue",
              "statement_handle":"score_class.statement.3","description":"Verified final SCORE_CLASS = SCORE_CLASS assignment immediately before END FUNCTION"}],
            "identity_note":"Existing function and assignment identities are stable token-anchored IDs. Existing IF blocks have no independent IDs. The inserted IF has no ID; its new result assignment receives one statement ID."}
        self._history("program_inspected","pi_model_tool",revision=7,structural_anchors=result["structural_insertion_anchors"])
        self._emit({"event_type":"selection","revision":7,"provenance":"Genuine Pi semantic inspection tool call",
            "title":"SCORE_CLASS structure inspected","description":"The function body boundary and existing assignment handles were resolved from the Workspace projection.",
            "focus":{"handles":["score_class.function","score_class.statement.3"],"mapping":"exact_semantic_span"},
            "dependencies":self.dependencies()})
        return result
    def _resolve_expression(self,value,fn_id,scope_id,params):
        if not isinstance(value,dict):raise WorkspaceError("INVALID_EXPRESSION","Typed expression must be an object")
        kind=value.get("kind")
        if kind=="number" and set(value)=={"kind","value"}:
            n=value["value"]
            if isinstance(n,bool) or not isinstance(n,(int,float)) or not math.isfinite(float(n)):raise WorkspaceError("INVALID_EXPRESSION","Number must be finite")
            return {"kind":"number","value":n}
        if kind=="local_ref" and set(value)=={"kind","name"}:
            name=value["name"]
            if not isinstance(name,str):raise WorkspaceError("INVALID_EXPRESSION","local_ref name must be text")
            sid=next((sid for sid in params if self.ws.documents[self.doc].symbols[sid].name.casefold()==name.casefold()),None)
            if sid is None:raise WorkspaceError("UNKNOWN_PARAMETER","Only the discovered SCORE_CLASS parameter X is in scope")
            return {"kind":"symbol_ref","symbol_id":sid}
        if kind=="call" and set(value)=={"kind","function_handle","arguments"}:
            handle=value["function_handle"]; args=value["arguments"]
            if handle!="clamp_score.function" or handle not in self.discovered or handle not in self.aliases:
                raise WorkspaceError("MISSION_DEPENDENCY_FORBIDDEN","Only the discovered CLAMP_SCORE dependency is authorized")
            if not isinstance(args,list) or len(args)!=1:raise WorkspaceError("FUNCTION_SIGNATURE_MISMATCH","CLAMP_SCORE requires one numeric argument")
            callee_id=self.aliases[handle]
            return {"kind":"call","function_id":callee_id,"arguments":[self._resolve_expression(arg,fn_id,scope_id,params) for arg in args]}
        if kind=="binary" and set(value)=={"kind","operator","left","right"} and value.get("operator") in {"=","<>","<","<=",">",">="}:
            return {"kind":"binary","operator":value["operator"],
                "left":self._resolve_expression(value["left"],fn_id,scope_id,params),
                "right":self._resolve_expression(value["right"],fn_id,scope_id,params)}
        raise WorkspaceError("INVALID_TYPED_EXPRESSION",f"Unsupported structural expression {kind!r}")
    def _resolve_statement(self,statement):
        if not isinstance(statement,dict) or set(statement)-{"kind","condition","then","else"} or statement.get("kind")!="if":
            raise WorkspaceError("INVALID_TYPED_IF","Structural operation must contain exactly one IF block")
        fn_id=self.aliases["score_class.function"]
        fn=next(f for f in self.ws.documents[self.doc].functions if f["symbol_id"]==fn_id)
        params=fn["parameters"]
        out={"kind":"if","condition":self._resolve_expression(statement.get("condition"),fn_id,fn["scope_id"],params),"then":[]}
        for branch in ("then","else"):
            items=statement.get(branch,[])
            if not isinstance(items,list) or len(items)>1:raise WorkspaceError("INVALID_TYPED_IF","Each branch may contain at most one result assignment")
            converted=[]
            for item in items:
                if not isinstance(item,dict) or set(item)!={"kind","target","expression"} or item.get("kind")!="assign" or item.get("target")!={"kind":"result"}:
                    raise WorkspaceError("INVALID_TYPED_STATEMENT","IF branches may contain only result assignments")
                converted.append({"kind":"assign","target":{"kind":"result"},
                    "expression":self._resolve_expression(item["expression"],fn_id,fn["scope_id"],params)})
            out[branch]=converted
        if not out["then"] and not out["else"]:raise WorkspaceError("INVALID_TYPED_IF","IF must contain a result assignment")
        return out
    def _candidate(self,request):
        if not isinstance(request,dict) or set(request)!={"expected_revision","function_handle","before_statement_handle","statement"}:
            raise WorkspaceError("INVALID_STRUCTURAL_REQUEST","Structural edit requires expected_revision, function_handle, before_statement_handle, and statement")
        current=self.ws.get_revision(self.doc)
        if request["expected_revision"]!=current or current!=7:raise WorkspaceError("STALE_REVISION","Structural edit is bound to the current revision 7")
        if self.committed:raise WorkspaceError("MISSION_EDIT_LIMIT","Mission permits one atomic structural insertion")
        handle=request["function_handle"]
        if handle!="score_class.function" or handle not in self.discovered:raise WorkspaceError("MISSION_EDIT_SCOPE","Discover SCORE_CLASS before editing it")
        anchor=request["before_statement_handle"]
        if anchor!="score_class.statement.3" or anchor not in self.discovered_statements:
            raise WorkspaceError("INVALID_INSERTION_ANCHOR","Use the inspected SCORE_CLASS result-epilogue statement handle")
        resolved_statement=self._resolve_statement(request["statement"])
        operation={"operation":"insert_typed_if_block","function_id":self.aliases[handle],
            "before_statement_id":self.aliases[anchor],"statement":resolved_statement}
        # Apply only to private copies to recover the exact newly created stable
        # assignment ID and validate the full candidate projection.
        candidate_ws=copy.deepcopy(self.ws)
        applied=candidate_ws.apply_transaction(self.doc,current,[operation])
        created=[row for row in applied["created_statements"] if row["containing_function_id"]==self.aliases[handle]]
        if len(created)!=1:raise WorkspaceError("MISSION_CANDIDATE_MISMATCH","Candidate must create exactly one result-assignment identity")
        new_aliases=dict(self.aliases);new_aliases[NEW_STATEMENT_HANDLE]=created[0]["statement_id"]
        normalized=senior.normalized_state(projection_semantics(build_projection(candidate_ws,self.doc,applied["revision"])),new_aliases)
        self._authorize_projection(normalized,new_aliases)
        old_tokens={t.uid:t.text for t in self.ws.documents[self.doc].tokens}
        new_tokens={t.uid:t.text for t in candidate_ws.documents[self.doc].tokens}
        if not set(old_tokens).issubset(new_tokens) or any(new_tokens[uid]!=text for uid,text in old_tokens.items()):
            raise WorkspaceError("IDENTITY_PRESERVATION_FAILED","Structural insertion changed an existing token identity or value")
        if set(new_aliases)-set(self.aliases)!={NEW_STATEMENT_HANDLE}:
            raise WorkspaceError("MISSION_CANDIDATE_MISMATCH","Only the new result assignment may receive a portable identity")
        observed=self._observe(candidate_ws,self.doc,applied["revision"],new_aliases)
        expected=self._expected()
        if observed!={"interp":expected,"jit":expected}:raise WorkspaceError("MISSION_PREVIEW_ORACLE","Candidate does not satisfy the independent classification oracle")
        return [operation],normalized,new_aliases,candidate_ws,applied,observed
    def _authorize_projection(self,candidate,aliases):
        for handle in ("clamp_score.function","is_passing.function"):
            if self._find(candidate,handle)!=self._find(self.baseline,handle):
                raise WorkspaceError("MISSION_EXISTING_FUNCTION_CHANGED",f"{handle} must remain structurally unchanged")
        old=self._find(self.baseline,"score_class.function");new=self._find(candidate,"score_class.function")
        if any(new.get(k)!=old.get(k) for k in ("handle","name","parameters","locals","local_types","return_type","arrays")):
            raise WorkspaceError("MISSION_SIGNATURE_OR_SCOPE_CHANGED","SCORE_CLASS signature and scope must remain unchanged")
        before=old["statements"]; after=new["statements"]
        if len(after)!=len(before)+1 or after[:-2]!=before[:-1] or after[-1]!=before[-1]:
            raise WorkspaceError("MISSION_STATEMENT_PRESERVATION","Only one top-level IF may be inserted before the existing result epilogue")
        inserted=after[-2]
        if inserted.get("kind")!="if" or inserted.get("else")!=[]:
            raise WorkspaceError("MISSION_IF_SHAPE","Inserted control must be one top-level IF without ELSE")
        condition=inserted.get("condition",{}); children=condition.get("children",[])
        if condition.get("kind")!="compare" or condition.get("value")!="=" or len(children)!=2:
            raise WorkspaceError("MISSION_IF_CONDITION","Inserted IF must compare the normalized CLAMP_SCORE result")
        call,num=children
        if (call.get("kind")!="call" or call.get("value")!="clamp_score.function" or
                call.get("children")!=[{"kind":"variable","value":"score_class.parameter.id","children":[]}] or
                num.get("kind")!="number" or float(num.get("value"))!=50.0):
            raise WorkspaceError("MISSION_DEPENDENCY_OR_CONDITION","The new IF must be CLAMP_SCORE(X) = 50")
        then=inserted.get("then",[])
        if len(then)!=1 or then[0].get("kind")!="assignment" or then[0].get("target_handle")!="score_class.function" or then[0].get("expression",{}).get("kind")!="number" or float(then[0]["expression"].get("value"))!=3.0:
            raise WorkspaceError("MISSION_FOURTH_CATEGORY","The new branch must assign result value 3")
        if {(e["caller"],e["callee"]) for e in senior.candidate_call_edges(candidate)} != {
            (e["caller"],e["callee"]) for e in senior.candidate_call_edges(self.baseline)}:
            raise WorkspaceError("MISSION_DEPENDENCY_CHANGED","No dependency edge may be introduced or removed")
        return True
    def handle(self,method,params,rid):
        if method=="record_pi_event":return self.record_pi(params)
        if method=="get_status":return {"revision":self.ws.get_revision(self.doc),"committed":self.committed,
            "document_id":self.doc,"function_handles":sorted(h for h in self.aliases if h.endswith(".function"))}
        if method=="discover_functions":return self.discover()
        if method=="inspect_program":return self.inspect()
        if method=="preview_structural_edit":return self._preview(params,rid)
        if method=="commit_preview":return self._commit(params,rid)
        if method=="validate_mission":return self.validate(params.get("expected_revision"),rid,actor="pi")
        if method=="host_validate":return self.validate(params.get("expected_revision"),rid,actor="host")
        if method=="record_agent_status":
            self._emit({"event_type":"mission_status","revision":self.ws.get_revision(self.doc),"provenance":"Host Pi lifecycle observation",
                "title":str(params.get("state","status")),"description":str((params.get("info") or {}).get("description",params.get("state","status")))})
            return {"ok":True,"revision":self.ws.get_revision(self.doc)}
        if method=="finalize_mission":
            life=params.get("pi_lifecycle") or {}; validation=params.get("validation") or {}
            states=completion_states(committed=self.committed,validation=validation,timed_out=bool(params.get("timed_out")),
                exit_code=params.get("pi_exit_code"),agent_end_seen=bool(life.get("agent_end_seen")),
                agent_settled_seen=bool(life.get("agent_settled_seen")),pending_tool_count=len(life.get("pending_tools",{})),
                authorization_status="authorized" if self.committed else "not_committed")
            write(self.output/"completion-states.json",{"completion_states":states,"lifecycle":life})
            return {"completion_states":states}
        raise WorkspaceError("UNKNOWN_TOOL","Unsupported structural-mission tool")
    def _preview(self,request,rid):
        try: operations,candidate,aliases,candidate_ws,applied,observed=self._candidate(request)
        except WorkspaceError as exc:
            revision=self.ws.get_revision(self.doc); result={"ok":False,"code":exc.code,"message":str(exc),"revision":revision,
                "revision_unchanged":True,"authoritative_workspace_changed":False}
            self._history("transaction_rejected","mission_gateway",request_id=rid,code=exc.code,revision=revision,authoritative_state_unchanged=True)
            self._emit({"event_type":"rejection","revision":revision,"provenance":"MissionContract rejected structural candidate",
                "title":"Structural proposal rejected","description":str(exc),"outcome":result})
            return result
        txid,preview=self.transactions.preview(operation_kind="insert_typed_if_block",base_revision=request["expected_revision"],
            operations=operations,candidate=candidate,metadata={"request":copy.deepcopy(request),"candidate_aliases":aliases})
        self.pending_request_ids[txid]=rid
        self._history("operation_proposed","pi_model_tool",request_id=rid,transaction_id=txid,base_revision=7,
            operation="insert_typed_if_block",arguments=request)
        self._history("preview_accepted","mission_gateway",transaction_id=txid,base_revision=7,resulting_revision=8,
            candidate=candidate,new_statement_handle=NEW_STATEMENT_HANDLE)
        diff=preview.get("diff",""); lines=[line[1:] for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++")]
        self._emit({"event_type":"preview","revision":7,"provenance":"Genuine Pi typed structural proposal · accepted MissionGateway preview",
            "source_event_ref":rid,"title":"SCORE_CLASS IF preview accepted","description":"The candidate inserts one bound IF; committed BASIC remains revision 7 until commit.",
            "focus":{"handles":["score_class.function","clamp_score.function","score_class.statement.3"],"mapping":"verified_function_boundary"},
            "preview":{"status":"accepted","function":"SCORE_CLASS","append_lines":lines,"new_statement_handle":NEW_STATEMENT_HANDLE,
                "bound_callee":"CLAMP_SCORE"},"outcome":{"authorized":True,"committed":False,"transaction_id":txid}})
        return {"ok":True,"transaction_id":txid,"base_revision":7,"expected_result_revision":8,
            "candidate_is_preview_only":True,"new_statement_handle":NEW_STATEMENT_HANDLE,
            "preserved_existing_identity_count":17,"diagnostics":preview["diagnostics"]}
    def _commit(self,params,rid):
        txid=params.get("transaction_id");record=self.transactions.get(txid) if isinstance(txid,str) else None
        if record is None:return {"ok":False,"committed":False,"code":"PREVIEW_NOT_FOUND","revision":self.ws.get_revision(self.doc)}
        try:
            def revalidate(row,revision):
                req=row["metadata"]["request"]
                ops,candidate,aliases,_,_,_=self._candidate(req)
                return ops,candidate,{"candidate_aliases":aliases,"request":req}
            receipt=self.transactions.commit(txid,revalidate)
        except WorkspaceError as exc:
            return {"ok":False,"committed":False,"code":exc.code,"message":str(exc),"revision":self.ws.get_revision(self.doc),"authoritative_workspace_changed":False}
        actual=[r for r in receipt.applied["created_statements"] if r["containing_function_id"]==self.aliases["score_class.function"]]
        if len(actual)!=1:raise RuntimeError("Committed structural insertion did not create exactly one assignment")
        self.aliases[NEW_STATEMENT_HANDLE]=actual[0]["statement_id"]
        self.committed=True;self.revision=receipt.revision
        self.committed_operations.append({"operation":"insert_typed_if_block","function_handle":"score_class.function",
            "insertion_anchor_handle":"score_class.statement.3","created_statement_handle":NEW_STATEMENT_HANDLE,
            "statement":copy.deepcopy(receipt.metadata["request"]["statement"])})
        normalized=senior.normalized_state(projection_semantics(build_projection(self.ws,self.doc,self.revision)),self.aliases)
        if normalized!=receipt.candidate:raise RuntimeError("Committed structural program differs from authorized preview")
        code=self.ws.render_document(self.doc)
        write(self.output/"constructive-operations.json",{"schema":"basic-workspace.constructive-metafile","version":1,
            "execution_profile_id":PROFILE,"portable_handles":sorted(self.aliases),"operations":self.committed_operations})
        source=read(self.output/"visual-source.json");source["snapshots"]["8"]=code;write(self.output/"visual-source.json",source)
        self._history("transaction_committed","mission_gateway",request_id=rid,transaction_id=txid,base_revision=7,resulting_revision=8,
            operation="insert_typed_if_block",created_statement_handle=NEW_STATEMENT_HANDLE,
            created_statements=receipt.applied["created_statements"],semantic_snapshot=normalized,
            preserved_existing_statement_handles=17)
        self._emit({"event_type":"commit","revision":8,"snapshot":code,"provenance":"Workspace atomic transaction · genuine Pi commit request",
            "source_event_ref":self.pending_request_ids.get(txid,rid),"title":"SCORE_CLASS structural edit committed",
            "description":"One IF block and one result-assignment statement were committed at revision 8; all 17 existing portable identities remain bound.",
            "focus":{"handles":["score_class.function",NEW_STATEMENT_HANDLE,"clamp_score.function"],"mapping":"verified_function_boundary"},
            "dependencies":self.dependencies(),"outcome":{"committed":True,"revision":8,"transaction_id":txid}})
        return {"ok":True,"committed":True,"revision":8,"new_statement_handle":NEW_STATEMENT_HANDLE,
            "created_statements":receipt.applied["created_statements"],"preserved_existing_identity_count":17}
    def validate(self,requested_revision,rid,actor="host"):
        revision=self.ws.get_revision(self.doc)
        if requested_revision!=revision:return {"reliable":False,"code":"STALE_VALIDATION_REVISION","requested_revision":requested_revision,"executed_revision":None,"mission_complete":False}
        if not self.committed:return {"reliable":True,"mission_complete":False,"executed_revision":revision,"diagnostics":["No structural edit committed"]}
        observed=self._observe(self.ws,self.doc,revision,self.aliases)
        expected=self._expected();engine_ok=observed["interp"]==observed["jit"]
        oracle_ok=observed=={"interp":expected,"jit":expected}
        normalized=senior.normalized_state(projection_semantics(build_projection(self.ws,self.doc,revision)),self.aliases)
        self._authorize_projection(normalized,self.aliases)
        identity_ok=all(self.aliases.get(h)==self.base_aliases.get(h) for h in self.base_aliases)
        replay=self.replay(self.committed_operations)
        replay_ok=replay["normalized"]==normalized and replay["observed"]==observed and replay["identity_count"]==18
        result={"schema":"basic-workspace.cycle25-structural-validation","version":1,"reliable":True,
            "revision":revision,"requested_revision":requested_revision,"executed_revision":revision,
            "observed_results":observed,"expected_results":{"interp":expected,"jit":expected},
            "expectation_source":"independent host-owned numeric oracle","engines_agree":engine_ok,
            "values_match":oracle_ok,"existing_functions_unchanged":True,"existing_score_class_statements_preserved":True,
            "existing_identity_bindings_preserved":identity_ok,"new_statement_handle":NEW_STATEMENT_HANDLE,
            "new_statement_id":self.aliases[NEW_STATEMENT_HANDLE],"dependency_edges_unchanged":True,
            "replay":{"passed":replay_ok,"structural_equivalence":replay["normalized"]==normalized,
                "behavioral_equivalence":replay["observed"]==observed,"portable_identity_count":replay["identity_count"],
                "identity_remappings":replay["remapped_count"],"existing_17_handles_preserved":replay["existing_handles_preserved"]},
            "mission_complete":bool(engine_ok and oracle_ok and identity_ok and replay_ok)}
        write(self.output/"mission-validation-host.json" if actor=="host" else self.output/"mission-validation-pi_tool.json",result)
        self._history("program_validated","pi_model_tool" if actor=="pi" else "host_validation",revision=revision,
            passed=result["mission_complete"],engines_agree=engine_ok,replay_passed=replay_ok)
        self._emit({"event_type":"validation","revision":revision,"provenance":"Pi-requested MIR validation" if actor=="pi" else "Independent host validation",
            "title":"MIR interpreter/JIT and replay validation","description":"Both engines were checked against the host oracle; a fresh Workspace replay was compared.",
            "focus":{"handles":["score_class.function",NEW_STATEMENT_HANDLE],"mapping":"verified_function_boundary"},
            "validation":{"passed":result["mission_complete"],"interpreter_jit_agree":engine_ok,"replay":result["replay"]},
            "observation":{"function":"SCORE_CLASS","arguments":list(INPUTS),"engine_results":observed,"revision":revision,"agreement":engine_ok},
            "dependencies":self.dependencies()})
        return result
    def replay(self,operations):
        """Replay the portable prefix through the shared operation interpreter."""
        ws=Workspace();doc=ws.create_empty_document("memory://cycle25/replay.bas")["document_id"]
        replay=replay_constructive_stream(ws,doc,operations,expected_start_revision=1)
        aliases=replay.live_handles;revision=replay.revision
        norm=senior.normalized_state(projection_semantics(build_projection(ws,doc,revision)),aliases)
        observed=self._observe(ws,doc,revision,aliases)
        remapped=sum(self.aliases.get(handle)!=aliases.get(handle) for handle in aliases if handle in self.aliases)
        return {"workspace":ws,"document_id":doc,"revision":revision,"aliases":aliases,"normalized":norm,
            "observed":observed,"identity_count":len(aliases),"remapped_count":remapped,
            "existing_handles_preserved":all(handle in aliases for handle in self.base_aliases),
            "operation_events":replay.operation_events,"retired_handles":replay.retired_handles}


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--output",type=Path,required=True);parser.add_argument("--contract",type=Path,default=CONTRACT);parser.add_argument("--port",type=int,default=0)
    args=parser.parse_args();service=Cycle25Gateway(args.output,args.contract)
    with Server(("127.0.0.1",args.port),service) as server:
        print(json.dumps({"ready":True,"host":"127.0.0.1","port":server.server_address[1],"revision":7,
            "baseline_verified":True,"mission_id":service.mission_id,"identity_count":len(service.aliases)},separators=(",",":")),flush=True)
        server.serve_forever()
if __name__=="__main__":main()
