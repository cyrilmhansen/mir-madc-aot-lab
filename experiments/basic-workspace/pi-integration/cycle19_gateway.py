#!/usr/bin/env python3
"""Two-mission, empty-document semantic gateway for Cycle 19."""
from __future__ import annotations
import argparse, importlib.util, json, math, sys, threading, time, uuid
from pathlib import Path
from typing import Any

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(HERE))
from basic_workspace.model import Workspace, WorkspaceError
from basic_workspace.projection import build_projection, projection_semantics
from basic_workspace.mir_execution import MirExecutionService
from pi_lifecycle import completion_states
from gateway import Cycle16Gateway, Server

spec=importlib.util.spec_from_file_location("cycle19_senior",ROOT/"scripts/is-senior-campaign.py")
senior=importlib.util.module_from_spec(spec); assert spec and spec.loader; sys.modules[spec.name]=senior; spec.loader.exec_module(senior)
age_spec=importlib.util.spec_from_file_location("cycle19_age",ROOT/"scripts/age-by-id-campaign.py")
age=importlib.util.module_from_spec(age_spec); assert age_spec and age_spec.loader; sys.modules[age_spec.name]=age; age_spec.loader.exec_module(age)
PROFILE_ID="basic-workspace.numeric-composition.v1"
INPUTS=(-100,-1,0,1,59,60,99,100,101,200)

class Cycle19Gateway:
    def __init__(self, output:Path):
        self.output=output; output.mkdir(parents=True,exist_ok=True)
        self.ws=Workspace(); self.doc=self.ws.create_empty_document("memory://cycle19/empty.bas")["document_id"]
        self.aliases:dict[str,str]={}; self.trace=age.Trace(); self.lock=threading.RLock()
        self.revision=self.ws.get_revision(self.doc); self.phase=1; self.preview_pending={}; self.dispatched={}
        self.pi_seen=set(); self.presentation_seq=0; self.committed_operations=[]; self.completed_missions=[]
        self.last_validation=None; self.session_id="cycle19-mission-1"
        self.mission_specs={1:{"mission_id":"cycle19.normalize-score.v1","name":"CLAMP_SCORE","handle":"clamp_score.function","parameter":"X","callee":None,
            "objective":"Create CLAMP_SCORE(X): return 0 below 0, X from 0 through 100, and 100 above 100."},
            2:{"mission_id":"cycle19.classify-passing.v1","name":"IS_PASSING","handle":"is_passing.function","parameter":"X","callee":"clamp_score.function",
            "objective":"Create IS_PASSING(X): return 1 when CLAMP_SCORE(X) is at least 60, otherwise 0."}}
        self.base_snapshot={"functions":[]}; self.base_aliases={}; self.discovered=set(); self.committed=False
        self.current_contract=self.mission_specs[1]; self.mission_title="Mission 1 · CLAMP_SCORE"
        self.visual_events=output/"visual-events.jsonl"; self.gateway_timings=output/"gateway-tool-timings.jsonl"
        self.pi_events=output/"pi-tool-lifecycle.jsonl"
        self.initial={"revision":self.revision,"code":"","dependencies":[]}
        bundle={"schema":"basic-workspace.visual-source","version":1,
            "campaign":{"id":"cycle19-empty-workspace","title":"Cycle 19 · agent-built BASIC from an empty Workspace","filename":"SCORES.bas"},
            "initial":self.initial,"snapshots":{str(self.revision):""}}
        self.write_json("visual-source.json",bundle)
        (output/"MISSION-1.json").write_text(json.dumps(self.mission_contract(1),indent=2)+"\n")
        (output/"MISSION-2.json").write_text(json.dumps(self.mission_contract(2,base_revision=2),indent=2)+"\n")
        profile=json.loads((ROOT/"results/semantic-replay/execution-profile.json").read_text())
        self.write_json("execution-profile.json",profile)
        self.append_log(output/"setup.jsonl",{"kind":"empty_workspace_created","revision":self.revision,
            "document_token_count":0,"functions":[],"host_inserted_program_logic":False,"execution_profile_id":PROFILE_ID})
        self.emit_visual({"event_id":"cycle19-empty-start","event_type":"initial","revision":self.revision,
            "session_id":"cycle19-mission-1","mission_id":self.mission_title,"provenance":"Workspace.create_empty_document",
            "title":"Empty Workspace","description":"Canonical document created with zero tokens and no functions. No BASIC seed was inserted.",
            "mission_status":"Mission 1 pending · empty committed revision 1","dependencies":[]})

    def write_json(self,name:str,data:Any):
        (self.output/name).write_text(json.dumps(data,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    @staticmethod
    def append_log(path:Path,row:dict[str,Any]):
        with path.open("a",encoding="utf-8") as f:f.write(json.dumps(row,ensure_ascii=False,separators=(",",":"))+"\n")
    def emit_visual(self,event:dict[str,Any]):
        self.presentation_seq+=1; event["presentation_sequence"]=self.presentation_seq
        self.append_log(self.visual_events,event)
    def code(self):return self.ws.render_document(self.doc)
    def profile(self):return PROFILE_ID
    def _raw(self,revision=None):return projection_semantics(build_projection(self.ws,self.doc,revision or self.ws.get_revision(self.doc)))
    def _normalized(self,revision=None):return senior.normalized_state(self._raw(revision),self.aliases)
    def _handles_for_functions(self):
        return {symbol:handle for handle,symbol in self.aliases.items() if handle.endswith(".function")}
    def _function_handles(self):
        return sorted(handle for handle in self.aliases if handle.endswith(".function"))
    def _mission_id(self):return self.current_contract["mission_id"]
    def _function_span(self,symbol_id:str):
        rows=[f for f in self.ws.documents[self.doc].functions if f["symbol_id"]==symbol_id]
        if len(rows)!=1:return {"mapping":"unknown","spans":{}}
        row=rows[0]
        return {"mapping":"exact_semantic_span","spans":{"function_lines":list(range(row["start_line"],row["end_line"]+1))}}
    def _call_lines(self,callee_id:str,scope:dict[str,Any]):
        doc=self.ws.documents[self.doc]
        return sorted({t.line for t in doc.tokens if scope["start_line"]<=t.line<=scope["end_line"] and doc.token_symbol.get(t.uid)==callee_id})
    def _dependencies(self,norm=None):
        norm=norm or self._normalized(); names={f["handle"]:f["name"] for f in norm["functions"]}
        return [{"caller":names.get(edge["caller"],edge["caller"]),"callee":names.get(edge["callee"],edge["callee"])}
            for edge in senior.candidate_call_edges(norm)]
    def mission_contract(self,phase:int,base_revision:int|None=None):
        spec=self.mission_specs[phase]
        return {"schema":"basic-workspace.mission-contract","version":1,"mission_id":spec["mission_id"],
            "objective":spec["objective"],"execution_profile":PROFILE_ID,
            "base_document_revision":base_revision if base_revision is not None else (1 if phase==1 else self.ws.get_revision(self.doc)),
            "allowed_operations":["create_numeric_function"],"allowed_function":{"name":spec["name"],"parameters":[spec["parameter"]],"return_type":"numeric"},
            "required_discovered_dependency":spec["callee"],"preserved_program_invariants":["all prior functions and bindings remain structurally unchanged","exactly one new function is added","no arrays, locals, renames, edits, or unrelated declarations"],
            "required_validation":{"engines":["interp","jit"],"expected_outputs":"independent host oracle"},
            "trust_boundary":"This contract is enforced only through the loopback MissionGateway; unrestricted host access is outside this experiment."}

    def _calls(self,value):
        if isinstance(value,list):
            for child in value:yield from self._calls(child)
        elif isinstance(value,dict):
            if value.get("kind")=="call":yield value
            for child in value.values():yield from self._calls(child)
    def _candidate(self,request:dict[str,Any],expected_revision:int,callee_handle:str|None):
        spec=self.current_contract; now=self.ws.get_revision(self.doc)
        if expected_revision!=now:raise WorkspaceError("STALE_REVISION",f"Expected revision {expected_revision}, current revision {now}")
        if self.committed:raise WorkspaceError("MISSION_EDIT_LIMIT","Mission permits exactly one function commit")
        if set(request)!={"name","parameters","body"}:raise WorkspaceError("MISSION_OPERATION_FORBIDDEN","Only typed create_numeric_function is allowed")
        if request["name"].casefold()!=spec["name"].casefold() or request["parameters"]!=[spec["parameter"]]:
            raise WorkspaceError("MISSION_SIGNATURE",f"Mission permits only {spec['name']}({spec['parameter']})")
        calls=list(self._calls(request["body"]))
        required=spec["callee"]
        if required is None:
            if calls or callee_handle not in (None,""):raise WorkspaceError("MISSION_DEPENDENCY_FORBIDDEN","CLAMP_SCORE must be self-contained")
            discovered_calls=set()
        else:
            if required not in self.discovered:raise WorkspaceError("FUNCTION_NOT_DISCOVERED","Discover CLAMP_SCORE before constructing IS_PASSING")
            if callee_handle!=required:raise WorkspaceError("MISSION_DEPENDENCY_FORBIDDEN",f"Only discovered {required} is authorized")
            if not calls or any(call.get("function_handle")!=required for call in calls):
                raise WorkspaceError("MISSION_DEPENDENCY_REQUIRED","IS_PASSING must call the discovered CLAMP_SCORE function")
            discovered_calls={required}
        resolved=senior.resolve_function_handles(request, self.aliases, discovered_calls)
        operation={"operation":"create_numeric_function",**resolved}
        candidate=self.ws.preview_transaction_semantics(self.doc,expected_revision,[operation])["candidate_semantics"]
        if len(candidate.get("functions",[]))!=len(self.base_snapshot["functions"])+1:
            raise WorkspaceError("MISSION_FUNCTION_COUNT","Candidate must add exactly one function")
        candidate_aliases=senior.aliases_for_new_function(candidate,self.base_aliases,spec["name"],spec["handle"])
        normalized=senior.normalized_state(candidate,candidate_aliases)
        for existing in self.base_snapshot["functions"]:
            if senior.find_function(self.base_snapshot,existing["handle"])!=senior.find_function(normalized,existing["handle"]):
                raise WorkspaceError("MISSION_EXISTING_FUNCTION_CHANGED",f"Existing function {existing['name']} changed")
        added=senior.find_function(normalized,spec["handle"])
        if added["parameters"]!=[f"{spec['handle'].rsplit('.',1)[0]}.parameter.id"] or added["arrays"] or added["locals"]:
            raise WorkspaceError("MISSION_SIGNATURE","Candidate has unexpected locals, arrays, or parameters")
        call_refs=senior.expression_references(added["statements"],"call")
        if required is None and call_refs:raise WorkspaceError("MISSION_DEPENDENCY_FORBIDDEN","Unexpected function dependency")
        if required is not None and not any(row.get("value")==required for row in call_refs):
            raise WorkspaceError("MISSION_DEPENDENCY_REQUIRED",f"No bound call to {required} in candidate projection")
        return operation,normalized,candidate_aliases

    def _program_fingerprint(self,normalized):
        payload=json.dumps({"profile":PROFILE_ID,"revision":self.ws.get_revision(self.doc),"semantics":normalized},
            sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
        import hashlib
        return hashlib.sha256(payload).hexdigest()
    def _checkpoint(self,validation):
        normalized=self._normalized(); by_handle={row["handle"]:row for row in normalized["functions"]}
        return {"schema":"basic-workspace.semantic-recovery-checkpoint","version":1,
            "document_id":self.doc,"revision":self.ws.get_revision(self.doc),"execution_profile_id":PROFILE_ID,
            "semantic_fingerprint":self._program_fingerprint(normalized),"workspace_facts":{
                "functions":[{"handle":h,"name":by_handle[h]["name"],"parameters":by_handle[h]["parameters"],"return_type":by_handle[h]["return_type"]} for h in sorted(by_handle)],
                "arrays":[],"dependencies":self._dependencies(normalized),"validated_results":validation["observed_results"]},
            "completed_missions":[{"mission_id":self.mission_specs[1]["mission_id"],"revision":self.ws.get_revision(self.doc),"validated":True}],
            "active_mission":self.mission_specs[2]["objective"],"unsupported":["arrays","loops","strings","module state"],
            "agent_authored_notes":[]}
    def advance_mission2(self,checkpoint):
        if self.phase!=1 or not self.committed or not self.last_validation or not self.last_validation.get("mission_complete"):
            return {"ok":False,"code":"MISSION1_NOT_VALIDATED","revision":self.ws.get_revision(self.doc),"workspace_changed":False}
        current=self.ws.get_revision(self.doc); normalized=self._normalized()
        if checkpoint.get("revision")!=current or checkpoint.get("semantic_fingerprint")!=self._program_fingerprint(normalized) or checkpoint.get("execution_profile_id")!=PROFILE_ID:
            return {"ok":False,"code":"CHECKPOINT_MISMATCH","revision":current,"workspace_changed":False}
        if checkpoint.get("document_id")!=self.doc:
            return {"ok":False,"code":"CHECKPOINT_DOCUMENT_MISMATCH","revision":current,"workspace_changed":False}
        self.phase=2; self.current_contract=self.mission_specs[2]; self.mission_title="Mission 2 · IS_PASSING"
        self.base_snapshot=normalized; self.base_aliases=dict(self.aliases); self.discovered=set(); self.preview_pending={}; self.committed=False
        self.last_validation=None
        self.session_id="cycle19-mission-2"
        self.trace.emit("mission_started",phase="host",actor="host_orchestrator",mission_id=self._mission_id(),
            base_revision=current,previous_mission_validated=True)
        self.emit_visual({"event_id":"cycle19-context-reset","event_type":"context_reset","revision":current,
            "session_id":self.session_id,"mission_id":self.mission_title,"provenance":"Host checkpoint verified before a fresh Pi process",
            "title":"Mission boundary · fresh agent context","description":"Mission 1's committed program remains authoritative. Mission 2 begins in a new Pi conversation from this revision-bound checkpoint.",
            "mission_status":f"Mission 1 passed · context reset · Mission 2 pending · revision {current}",
            "focus":{"handles":["clamp_score.function"],"mapping":"verified_function_boundary"},"dependencies":self._dependencies(normalized)})
        self.write_json("checkpoint.json",checkpoint)
        self.write_json("mission-2-baseline.json",{"revision":current,"normalized_program":normalized,
            "semantic_fingerprint":self._program_fingerprint(normalized),"captured_after_mission_1_validation":True})
        self.append_log(self.output/"setup.jsonl",{"kind":"mission_2_started_from_verified_checkpoint","revision":current,
            "fingerprint":checkpoint["semantic_fingerprint"],"conversation_reset":True})
        self.flush_trace()
        return {"ok":True,"revision":current,"mission_id":self._mission_id(),"function_handles":self._function_handles()}
    def create_checkpoint(self):
        if self.phase!=1 or not self.last_validation or not self.last_validation.get("mission_complete"):
            return {"ok":False,"code":"MISSION1_NOT_VALIDATED","revision":self.ws.get_revision(self.doc)}
        checkpoint=self._checkpoint(self.last_validation); self.write_json("checkpoint.json",checkpoint)
        self.trace.emit("checkpoint_created",phase="host",actor="host_orchestrator",mission_id=self.mission_specs[1]["mission_id"],
            revision=self.ws.get_revision(self.doc),semantic_fingerprint=checkpoint["semantic_fingerprint"],
            included_conversation_history=False,checkpoint_bytes=len(json.dumps(checkpoint,separators=(",",":"),ensure_ascii=False).encode()))
        self.emit_visual({"event_id":"cycle19-checkpoint-created","event_type":"checkpoint","revision":self.ws.get_revision(self.doc),
            "session_id":self.session_id,"mission_id":self.mission_title,"provenance":"Host-generated from validated committed Workspace state",
            "title":"Verified semantic checkpoint","description":"Checkpoint records portable function handles, revision, profile, dependency facts and validated outputs; it contains no conversation transcript.",
            "focus":{"handles":["clamp_score.function"],"mapping":"verified_function_boundary"},
            "outcome":{"revision":checkpoint["revision"],"fingerprint":checkpoint["semantic_fingerprint"]},"dependencies":self._dependencies()})
        self.flush_trace(); return {"ok":True,"checkpoint":checkpoint}

    def _run_functions(self,revision):
        executor=MirExecutionService(timeout=15); result={"interp":{},"jit":{}}
        funcs={fn["name"].casefold():fn["symbol_id"] for fn in self.ws.documents[self.doc].functions}
        for engine in ("interp","jit"):
            for value in INPUTS:
                clamp=executor.execute_function(self.ws,self.doc,revision,funcs["clamp_score"],[value],engine)["result"]
                row={"clamp_score":clamp}
                if "is_passing" in funcs:
                    row["is_passing"]=executor.execute_function(self.ws,self.doc,revision,funcs["is_passing"],[value],engine)["result"]
                result[engine][str(value)]=row
        return result
    @staticmethod
    def _expected():
        return {str(x):{"clamp_score":float(min(100,max(0,x))),"is_passing":1.0 if min(100,max(0,x))>=60 else 0.0} for x in INPUTS}
    def _replay(self):
        stream={"schema":"basic-workspace.constructive-metafile","version":1,"execution_profile_id":PROFILE_ID,
            "portable_handles":sorted(self.aliases.keys()),"operations":self.committed_operations}
        ws=Workspace(); doc=ws.create_empty_document("memory://cycle19/replay.bas")["document_id"]; aliases={}; executor=MirExecutionService(timeout=15)
        for item in stream["operations"]:
            call_handles={row.get("function_handle") for row in self._calls(item["arguments"]) if row.get("function_handle")}
            if any(h not in aliases for h in call_handles):raise WorkspaceError("REPLAY_HANDLE_MISSING","Call handle missing in construction order")
            op=senior.resolve_function_handles(item["arguments"],aliases,call_handles)
            applied=ws.apply_transaction(doc,ws.get_revision(doc),[{"operation":"create_numeric_function",**op}])
            raw=projection_semantics(build_projection(ws,doc,applied["revision"]))
            aliases=senior.aliases_for_new_function(raw,aliases,op["name"],item["portable_handle"])
        revision=ws.get_revision(doc)
        norm=senior.normalized_state(projection_semantics(build_projection(ws,doc,revision)),aliases)
        names={fn["name"].casefold():fn["symbol_id"] for fn in ws.documents[doc].functions}
        obs={engine:{} for engine in ("interp","jit")}
        for engine in obs:
            for x in INPUTS:
                clamp=executor.execute_function(ws,doc,revision,names["clamp_score"],[x],engine)["result"]
                row={"clamp_score":clamp}
                if "is_passing" in names:row["is_passing"]=executor.execute_function(ws,doc,revision,names["is_passing"],[x],engine)["result"]
                obs[engine][str(x)]=row
        remapped=sum(self.aliases.get(h)!=aliases.get(h) for h in self.aliases)
        return stream,norm,obs,remapped

    def validate_current(self,requested_revision:int,actor="host"):
        revision=self.ws.get_revision(self.doc)
        if requested_revision!=revision:return {"reliable":False,"code":"STALE_VALIDATION_REVISION","mission_complete":False,
            "requested_revision":requested_revision,"workspace_revision":revision,"executed_revision":None}
        if not self.committed:return {"reliable":True,"mission_complete":False,"phase":"pre-create","executed_revision":revision,
            "diagnostics":[f"{self.current_contract['name']} is not committed"]}
        observed=self._run_functions(revision); expected_all=self._expected()
        expected=expected_all if self.phase==2 else {str(x):{"clamp_score":expected_all[str(x)]["clamp_score"]} for x in INPUTS}
        results_match=all(observed[engine]==expected for engine in observed)
        engines_agree=observed["interp"]==observed["jit"]
        norm=self._normalized(); base_unchanged=all(senior.find_function(self.base_snapshot,row["handle"])==senior.find_function(norm,row["handle"])
            for row in self.base_snapshot["functions"])
        target_handle=self.current_contract["handle"]
        dep=self.current_contract["callee"]
        function=senior.find_function(norm,target_handle)
        calls=senior.expression_references(function["statements"],"call")
        dependency_ok=(not dep and not calls) or (dep and any(row.get("value")==dep for row in calls))
        complete=bool(results_match and engines_agree and base_unchanged and dependency_ok)
        result={"schema":"basic-workspace.cycle19-validation","version":1,"mission_id":self._mission_id(),
            "actor":actor,"reliable":True,"revision":revision,"requested_revision":requested_revision,"executed_revision":revision,
            "observed_results":observed,"expected_results":expected,"expectation_source":"independent host-owned oracle",
            "engines_agree":engines_agree,"values_match":results_match,"prior_program_unchanged":base_unchanged,
            "required_dependency":dep,"dependency_bound":bool(dependency_ok),"mission_complete":complete,
            "boundary_oracle":{"passed":bool(results_match and engines_agree),
                "cases":len(INPUTS),"expectation_source":"independent host-owned oracle"},
            "diagnostics":[] if complete else ["Output, prior-program, or binding invariant failed"]}
        stream,replay_norm,replay_obs,remapped=self._replay()
        replay_ok=(norm==replay_norm and observed==replay_obs and replay_obs["interp"]==replay_obs["jit"])
        result["replay"]={"structural_equivalence":norm==replay_norm,"behavioral_equivalence":observed==replay_obs,
            "engine_agreement":replay_obs["interp"]==replay_obs["jit"],"identity_remappings":remapped,"passed":replay_ok}
        result["mission_complete"]=bool(result["mission_complete"] and replay_ok)
        if result["mission_complete"]:
            self.write_json("constructive-operations.json",stream)
            self.write_json("equivalence.json",result)
        self.write_json(f"mission-{self.phase}-validation-{actor}.json",result)
        self.append_log(self.output/"validation.jsonl",result)
        self.trace.emit("program_validated",phase=f"mission-{self.phase}",actor=actor,mission_id=self._mission_id(),
            revision=revision,passed=result["mission_complete"],executed_revision=revision,engines_agree=engines_agree,
            replay_passed=replay_ok,diagnostics=result["diagnostics"])
        title=f"{actor.title()} validation {'passed' if result['mission_complete'] else 'failed'} · revision {revision}"
        self.emit_visual({"event_id":f"cycle19-validation-{self.phase}-{actor}-{revision}","event_type":"validation",
            "revision":revision,"session_id":self.session_id,"mission_id":self.mission_title,
            "provenance":"Independent host MIR interpreter/JIT and portable replay oracle" if actor=="host" else "Pi-requested mission validator",
            "title":title,"description":"Expected-value checks, prior-program invariant, function bindings, and fresh-workspace replay were evaluated.",
            "validation":{"passed":result["mission_complete"],"engines_agree":engines_agree,"replay_passed":replay_ok},
            "observation":{"function":self.current_contract["name"],"arguments":list(INPUTS),"engine_results":observed,
                "revision":revision,"agreement":engines_agree},"dependencies":self._dependencies(norm)})
        self.flush_trace(); self.last_validation=result
        return result

    def _proposal_diagnostic(self,request,expected_revision,callee_handle):
        syntax=Cycle16Gateway.typed_shape_error(request)
        if syntax:return syntax
        try:return self._candidate(request,expected_revision,callee_handle)
        except WorkspaceError as exc:return {"ok":False,"code":exc.code,"message":str(exc)}
    def _discover(self,rid):
        revision=self.ws.get_revision(self.doc); by_symbol=self._handles_for_functions(); rows=[]
        for row in self.ws.list_symbols(self.doc):
            if row["kind"]!="function" or row["scope_id"]!="module":continue
            handle=by_symbol.get(row["symbol_id"])
            if not handle:continue
            fn=next(f for f in self.ws.documents[self.doc].functions if f["symbol_id"]==row["symbol_id"])
            self.discovered.add(handle)
            rows.append({"handle":handle,"symbol_id":row["symbol_id"],"name":row["name"],"parameter_count":len(fn["parameters"]),
                "parameter_names":[self.ws.documents[self.doc].symbols[s].name for s in fn["parameters"]],"return_type":"numeric"})
            span=self._function_span(row["symbol_id"])
            self.emit_visual({"event_id":f"cycle19-discovery-{self.phase}-{rid}-{handle}","event_type":"selection",
                "revision":revision,"session_id":self.session_id,"mission_id":self.mission_title,
                "provenance":"Genuine Pi semantic discovery tool call","source_event_ref":rid,
                "title":f"Discovered {row['name']}","description":f"Resolved portable function handle {handle} at revision {revision}.",
                "focus":{"handles":[handle],**span},"dependencies":self._dependencies()})
        if not rows and self.phase==1:
            self.emit_visual({"event_id":f"cycle19-discovery-empty-{rid}","event_type":"selection","revision":revision,
                "session_id":self.session_id,"mission_id":self.mission_title,"provenance":"Genuine Pi semantic discovery tool call",
                "source_event_ref":rid,"title":"No existing functions","description":"The agent inspected the initially empty Workspace.","focus":{"handles":[],"mapping":"unknown"}})
        return {"revision":revision,"functions":rows}
    def _preview(self,p,rid):
        revision=self.ws.get_revision(self.doc); request={k:p.get(k) for k in ("name","parameters","body")}
        syntax=Cycle16Gateway.typed_shape_error(request)
        if syntax:
            syntax.update({"reliable":True,"revision":revision,"revision_unchanged":True,"authoritative_workspace_changed":False})
            self.trace.emit("transaction_rejected",phase=f"mission-{self.phase}",actor="mission_gateway",mission_id=self._mission_id(),
                base_revision=p.get("expected_revision"),resulting_revision=revision,code=syntax["code"],path=syntax.get("path"),authoritative_state_unchanged=True)
            self.emit_visual({"event_id":f"cycle19-syntax-reject-{rid}","event_type":"rejection","revision":revision,
                "session_id":self.session_id,"mission_id":self.mission_title,"provenance":"Pi typed constructor · syntax/type validator",
                "source_event_ref":rid,"title":"Typed request rejected","description":f"{syntax['code']} at {syntax.get('path','arguments')}","preview":{"status":"rejected","diagnostic":syntax}})
            self.flush_trace(); return syntax
        # The typed call node itself carries the portable semantic reference.
        # Retain the optional wrapper field for compatibility, but do not require
        # agents to repeat the same dependency outside the expression tree.
        call_handles={call.get("function_handle") for call in self._calls(request["body"])
                      if isinstance(call.get("function_handle"),str)}
        effective_callee=p.get("callee_handle")
        if effective_callee is None and len(call_handles)==1:
            effective_callee=next(iter(call_handles))
        try:
            operation,candidate,candidate_aliases=self._candidate(request,p.get("expected_revision"),effective_callee)
        except WorkspaceError as exc:
            result={"ok":False,"reliable":True,"code":exc.code,"message":str(exc),"revision":revision,
                "revision_unchanged":True,"authoritative_workspace_changed":False}
            self.trace.emit("transaction_rejected",phase=f"mission-{self.phase}",actor="mission_gateway",mission_id=self._mission_id(),
                base_revision=p.get("expected_revision"),resulting_revision=revision,code=exc.code,authoritative_state_unchanged=True)
            self.emit_visual({"event_id":f"cycle19-policy-reject-{rid}","event_type":"rejection","revision":revision,
                "session_id":self.session_id,"mission_id":self.mission_title,"provenance":"MissionContract denied candidate",
                "source_event_ref":rid,"title":"Candidate rejected","description":str(exc),"preview":{"status":"rejected","diagnostic":result}})
            self.flush_trace(); return result
        preview=self.ws.preview_transaction(self.doc,p["expected_revision"],[operation],include_diff=True)
        txid="tx_"+uuid.uuid4().hex
        self.preview_pending[txid]={"request":request,"operation":operation,"base_revision":revision,
            "candidate":candidate,"candidate_aliases":candidate_aliases,"callee_handle":effective_callee}
        self.dispatched[txid]=rid
        self.trace.emit("operation_proposed",phase=f"mission-{self.phase}",actor="pi_model_tool",mission_id=self._mission_id(),
            transaction_id=txid,base_revision=revision,operation="create_numeric_function",arguments=request)
        self.trace.emit("preview_accepted",phase=f"mission-{self.phase}",actor="mission_gateway",mission_id=self._mission_id(),
            transaction_id=txid,base_revision=revision,resulting_revision=preview["expected_result_revision"],
            portable_handle=self.current_contract["handle"],bound_callee=effective_callee,candidate=candidate)
        additions=[line[1:] for line in preview.get("diff","").splitlines() if line.startswith("+") and not line.startswith("+++")]
        focus={"handles":[self.current_contract["handle"]],"mapping":"verified_function_boundary"}
        if self.current_contract["callee"]:focus["call_target"]=self.current_contract["callee"]
        self.emit_visual({"event_id":f"cycle19-preview-{rid}","event_type":"preview","revision":revision,
            "session_id":self.session_id,"mission_id":self.mission_title,"provenance":"Genuine Pi typed proposal · accepted MissionContract preview",
            "source_event_ref":rid,"title":f"{self.current_contract['name']} proposal","description":"Candidate accepted; committed BASIC remains unchanged until atomic commit.",
            "focus":focus,"preview":{"status":"accepted","append_lines":additions,"function":self.current_contract["name"],
                "bound_callee":effective_callee},"outcome":{"authorized":True,"committed":False}})
        self.flush_trace()
        return {"ok":True,"transaction_id":txid,"base_revision":revision,"expected_result_revision":revision+1,
            "portable_handle":self.current_contract["handle"],"bound_callee_handle":effective_callee,
            "diagnostics":preview["diagnostics"],"candidate_is_preview_only":True}
    def _commit(self,p,rid):
        txid=p.get("transaction_id"); pending=self.preview_pending.get(txid); current=self.ws.get_revision(self.doc)
        if pending is None:return {"ok":False,"committed":False,"code":"PREVIEW_NOT_FOUND","revision":current,"authoritative_workspace_changed":False}
        if pending["base_revision"]!=current:return {"ok":False,"committed":False,"code":"STALE_REVISION","revision":current,"authoritative_workspace_changed":False}
        try:
            op,candidate,candidate_aliases=self._candidate(pending["request"],pending["base_revision"],pending["callee_handle"])
            if candidate!=pending["candidate"] or candidate_aliases.keys()!=pending["candidate_aliases"].keys():
                return {"ok":False,"committed":False,"code":"PREVIEW_CANDIDATE_CHANGED","revision":current,"authoritative_workspace_changed":False}
            applied=self.ws.apply_transaction(self.doc,pending["base_revision"],[op])
        except WorkspaceError as exc:
            return {"ok":False,"committed":False,"code":exc.code,"message":str(exc),"revision":current,"authoritative_workspace_changed":False}
        raw=projection_semantics(build_projection(self.ws,self.doc,applied["revision"]))
        aliases=senior.aliases_for_new_function(raw,self.base_aliases,self.current_contract["name"],self.current_contract["handle"])
        norm=senior.normalized_state(raw,aliases)
        if norm!=candidate:raise RuntimeError("Committed semantic projection differs from authorized preview")
        self.aliases=aliases; self.revision=applied["revision"]; self.committed=True
        stored={"operation":"create_numeric_function","portable_handle":self.current_contract["handle"],
            "arguments":pending["request"]}
        if pending["callee_handle"]:stored["callee_handle"]=pending["callee_handle"]
        self.committed_operations.append(stored)
        source=self.code(); fn_id=self.aliases[self.current_contract["handle"]]; span=self._function_span(fn_id)
        if self.current_contract["callee"]:
            callee_id=self.aliases[self.current_contract["callee"]]
            fn=next(f for f in self.ws.documents[self.doc].functions if f["symbol_id"]==fn_id)
            span["spans"]["call_lines"]=self._call_lines(callee_id,fn)
        self.trace.emit("transaction_committed",phase=f"mission-{self.phase}",actor="mission_gateway",mission_id=self._mission_id(),
            transaction_id=txid,base_revision=current,resulting_revision=self.revision,operation="create_numeric_function",
            portable_handle=self.current_contract["handle"],bound_callee=self.current_contract["callee"],
            semantic_snapshot=norm,created_entities=applied["created_entities"],created_statements=applied["created_statements"])
        self.emit_visual({"event_id":f"cycle19-commit-{self.phase}-{txid}","event_type":"commit","revision":self.revision,"snapshot":source,
            "session_id":self.session_id,"mission_id":self.mission_title,"provenance":"Workspace atomic transaction · genuine Pi commit request",
            "source_event_ref":self.dispatched.get(txid,rid),"title":f"{self.current_contract['name']} committed",
            "description":f"Committed at revision {self.revision}"+(f"; bound call to {self.current_contract['callee']}" if self.current_contract["callee"] else "."),
            "focus":{"handles":[self.current_contract["handle"]]+([self.current_contract["callee"]] if self.current_contract["callee"] else []),**span},
            "dependencies":self._dependencies(norm),"outcome":{"committed":True,"transaction_id":txid,"bound_callee":self.current_contract["callee"]}})
        self.flush_trace()
        return {"ok":True,"committed":True,"revision":self.revision,"portable_handle":self.current_contract["handle"],
            "bound_callee_handle":self.current_contract["callee"],"created_entities":applied["created_entities"]}

    def record_pi(self,p):
        row=dict(p); key=(str(row.get("toolCallId") or row.get("request_id") or uuid.uuid4())+":"+str(row.get("type","")))
        duplicate=key in self.pi_seen
        if not duplicate:
            self.pi_seen.add(key); row["observed_monotonic_ns"]=time.monotonic_ns(); self.append_log(self.pi_events,row)
        if row.get("type")=="tool_inventory":
            self.write_json("tool-inventory.json",{"source":row.get("source"),"tools":row.get("tools",[])})
            self.write_json("tool-schemas.json",row.get("schemas",[]))
        return {"ok":True,"deduplicated":duplicate,"recorded_key":key}
    def _record_status(self,state,info):
        labels={"working":"Agent working","waiting_for_tool":"Agent waiting for a semantic tool",
            "no_observable_progress":"No Pi event observed; provider/generation state unresolved",
            "agent_turn_ended":"Pi agent turn ended; session settlement not yet observed",
            "agent_session_completed":"Pi reports agent session settled; waiting for process exit"}
        title=labels.get(state,state.replace("_"," "))
        self.append_log(self.output/"pi-viewer-status.jsonl",{"state":state,"revision":self.ws.get_revision(self.doc),
            "info":info,"observed_monotonic_ns":time.monotonic_ns()})
        self.emit_visual({"event_id":f"cycle19-life-{uuid.uuid4()}","event_type":"mission_status",
            "revision":self.ws.get_revision(self.doc),"session_id":self.session_id,"mission_id":self.mission_title,
            "provenance":"Host observation of Pi event arrival","title":title,"description":info.get("description",title),
            "mission_status":title,"lifecycle":{"state":state,"info":info},"dependencies":self._dependencies_safe()})
    def _dependencies_safe(self):
        try:return self._dependencies()
        except WorkspaceError:return []
    def record_gateway_timing(self,request,elapsed_ms):
        params=request.get("params") or {}; method=request.get("method")
        self.append_log(self.gateway_timings,{"request_id":request.get("request_id"),"tool_call_id":params.get("toolCallId"),
            "method":method,"mission_id":self._mission_id(),"phase":self.phase,"elapsed_ms":round(elapsed_ms,3),
            "agent_tool":method in {"discover_functions","inspect_program","preview_create_function","commit_preview","validate_mission"}})
    def flush_trace(self):self.trace.write(self.output/"history.jsonl")
    def handle(self,method,p,rid):
        if method=="record_pi_event":return self.record_pi(p)
        if method=="record_agent_status":
            self._record_status(str(p.get("state","unknown")),p.get("info") if isinstance(p.get("info"),dict) else {})
            return {"ok":True,"revision":self.ws.get_revision(self.doc)}
        if method=="get_status":return {"revision":self.ws.get_revision(self.doc),"phase":self.phase,
            "mission_id":self._mission_id(),"document_id":self.doc,"function_handles":self._function_handles(),
            "committed":self.committed}
        if method=="discover_functions":
            result=self._discover(rid); self.flush_trace(); return result
        if method=="inspect_program":
            revision=self.ws.get_revision(self.doc)
            if revision==1 and not self.ws.documents[self.doc].tokens:structure={"functions":[]}
            else:structure=self._normalized()
            return {"revision":revision,"structure":structure,"code":"(empty)" if not self.ws.documents[self.doc].tokens else None}
        if method=="preview_create_function":return self._preview(p,rid)
        if method=="commit_preview":return self._commit(p,rid)
        if method=="validate_mission":
            result=self.validate_current(p.get("expected_revision"),actor="pi_tool")
            return result
        if method=="host_validate":return self.validate_current(p.get("expected_revision"),actor="host")
        if method=="create_checkpoint":return self.create_checkpoint()
        if method=="advance_mission2":return self.advance_mission2(p.get("checkpoint",{}))
        if method=="finalize_session":
            lifecycle=p.get("pi_lifecycle") if isinstance(p.get("pi_lifecycle"),dict) else {}
            validation=p.get("validation") if isinstance(p.get("validation"),dict) else None
            events=[e for e in self.trace.events if e.get("mission_id")==self._mission_id()]
            authorization="authorized" if any(e.get("event")=="preview_accepted" for e in events) else "denied" if any(e.get("event")=="transaction_rejected" for e in events) else "not_attempted"
            states=completion_states(committed=self.committed,validation=validation,timed_out=bool(p.get("timed_out")),
                exit_code=p.get("pi_exit_code"),agent_end_seen=bool(lifecycle.get("agent_end_seen")),
                agent_settled_seen=bool(lifecycle.get("agent_settled_seen")),
                pending_tool_count=len(lifecycle.get("pending_tools",{})),authorization_status=authorization)
            self.write_json(f"mission-{self.phase}-session-status.json",states)
            self.append_log(self.output/"pi-viewer-status.jsonl",{"kind":"session_completion","mission_id":self._mission_id(),
                "revision":self.ws.get_revision(self.doc),"completion_states":states,"lifecycle":lifecycle})
            status=" · ".join(f"{k}: {v}" for k,v in states.items())+f" · revision {self.ws.get_revision(self.doc)}"
            self.emit_visual({"event_id":f"cycle19-session-end-{self.phase}","event_type":"mission_status",
                "revision":self.ws.get_revision(self.doc),"session_id":self.session_id,"mission_id":self.mission_title,
                "provenance":"Host classification of Pi lifecycle and independent validation",
                "title":f"Mission {self.phase} session outcome","description":status,"mission_status":status,
                "lifecycle":{"completion_states":states,"agent":lifecycle,
                    "validation_revision":validation.get("executed_revision") if validation else None},
                "dependencies":self._dependencies_safe()})
            self.flush_trace(); return {"completion_states":states,"mission_status":status}
        raise WorkspaceError("UNKNOWN_TOOL",f"Unsupported gateway method {method}")

class Handler(__import__("gateway").Handler):
    pass
class Server(__import__("gateway").Server):
    pass

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--output",type=Path,required=True);ap.add_argument("--port",type=int,default=0);a=ap.parse_args()
    service=Cycle19Gateway(a.output)
    with Server(("127.0.0.1",a.port),service) as server:
        print(json.dumps({"ready":True,"host":"127.0.0.1","port":server.server_address[1],"revision":service.revision},separators=(",",":")),flush=True)
        server.serve_forever()
if __name__=="__main__":main()
