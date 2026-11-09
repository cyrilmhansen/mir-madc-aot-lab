#!/usr/bin/env python3
"""Cycle 28 narrow conditional-refactor policy on the shared transaction kernel."""
from __future__ import annotations
import argparse, copy, json, sys, time, uuid
from pathlib import Path
HERE=Path(__file__).resolve().parent; ROOT=HERE.parent
sys.path.insert(0,str(HERE)); sys.path.insert(0,str(ROOT))
from cycle20_gateway import Cycle20Gateway, senior, PROFILE_ID, BASE as C20_BASE
from basic_workspace.model import Workspace, WorkspaceError
from basic_workspace.portable_replay import replay_constructive_stream
from basic_workspace.projection import build_projection, projection_semantics
from basic_workspace.typed_expr import Expr
from basic_workspace.mir_execution import MirExecutionService
from gateway import Server

STREAM=HERE/"results/cycle27-post-rename-reuse/real-agent-01/constructive-operations.json"
HISTORY=HERE/"results/cycle27-post-rename-reuse/real-agent-01/history.jsonl"
VALIDATION=HERE/"results/cycle27-post-rename-reuse/real-agent-01/mission-3-validation-host.json"
MISSION="cycle28.score-class-use-is-at-cap.v1"
PATH=[{"block":"body","index":2}]
ANCHOR="score_class.statement.category50"
INPUTS=[-100,-1,0,1,19,20,39,40,44,45,49,50,51,60,100,200]

class Cycle28Gateway(Cycle20Gateway):
    def _emit(self,event):
        self.session_id=f"cycle28-{self.output.name}"
        self.mission_id=MISSION
        return super()._emit(event)

    @staticmethod
    def _discover_authorized_targets(self=None):
        return []

    @staticmethod
    def _validate_contract_shape(contract):
        required={"schema","version","mission_id","objective","base_document_revision","execution_profile_id",
            "function_handle","control_path","anchor_statement_handle","expected_condition","replacement_condition",
            "unchanged_function_handles","required_baseline_dependency_edges","authorized_new_dependency_edge",
            "revision_increment","validation"}
        if not isinstance(contract,dict) or set(contract)!=required or contract.get("schema")!="basic-workspace.conditional-refactor-contract" or contract.get("version")!=1:
            raise WorkspaceError("MISSION_CONTRACT_INVALID","Conditional refactor contract has an unsupported shape or version")
        if contract["base_document_revision"]!=10 or contract["revision_increment"]!=1 or contract["execution_profile_id"]!=PROFILE_ID:
            raise WorkspaceError("MISSION_CONTRACT_INVALID","Conditional contract must bind to revision 10 and one revision increment")
        if (not isinstance(contract["function_handle"],str) or not isinstance(contract["anchor_statement_handle"],str)
                or not isinstance(contract["control_path"],list) or not contract["control_path"]
                or not isinstance(contract["unchanged_function_handles"],list)
                or not isinstance(contract["required_baseline_dependency_edges"],list)
                or not isinstance(contract["authorized_new_dependency_edge"],dict)):
            raise WorkspaceError("MISSION_CONTRACT_INVALID","Conditional target and invariant declarations must be typed")
        validation=contract["validation"]
        if not isinstance(validation,dict) or set(validation)!={"inputs","functions"} or not validation["inputs"] or not validation["functions"]:
            raise WorkspaceError("MISSION_CONTRACT_INVALID","Conditional contract requires executable oracle observations")

    def _validate_contract_against_baseline(self):
        if self.contract.get("execution_profile_id")!=PROFILE_ID or self.base_revision!=10:
            raise WorkspaceError("BASELINE_REVISION_MISMATCH","Cycle 28 requires verified revision 10")
        required={ (x["caller_handle"],x["callee_handle"]) for x in self.contract["required_baseline_dependency_edges"] }
        if {(x["caller"],x["callee"]) for x in self._dependency_edges(self.baseline)}!=required:
            raise WorkspaceError("BASELINE_DEPENDENCY_MISMATCH","Revision-10 dependency graph differs from contract")
        if len(self.aliases)!=23 or self.contract["anchor_statement_handle"] not in self.aliases:
            raise WorkspaceError("BASELINE_IDENTITY_MISMATCH","Expected all 23 Cycle 27 handles and category-50 anchor")
        for handle in ("clamp_score.function","is_passing.function","is_at_cap.function","score_class.function"):
            if handle not in self.aliases: raise WorkspaceError("BASELINE_HANDLE_MISSING",f"Missing {handle}")

    def __init__(self, output, contract_path):
        super().__init__(output, contract_path=contract_path, baseline_stream_path=STREAM,
            baseline_history_path=HISTORY, baseline_validation_path=VALIDATION)
        self.mission_id=self.contract["mission_id"]; self.session_id=f"cycle28-{Path(output).name}"
        self.discovered=set(); self.committed=False; self.transactions.clear()
        self.executor=MirExecutionService(timeout=20)
        self.expected_old=self._portable_expr(self._selected_if().condition,"score_class.function")
        if self.expected_old != self.contract["expected_condition"]:
            raise WorkspaceError("BASELINE_TARGET_MISMATCH","Final SCORE_CLASS condition is not the verified NORMALIZE_SCORE(X)=50 comparison")
        code=self.ws.render_document(self.doc)
        self.write_json(self.output/"MISSION.json",self.contract)
        self.write_json(self.output/"visual-source.json",{"schema":"basic-workspace.visual-source","version":1,
            "campaign":{"id":MISSION,"title":self.contract["objective"],"filename":"SCORES.bas"},
            "initial":{"revision":10,"code":code,"dependencies":self.dependencies()},"snapshots":{"10":code}})
        self.write_json(self.output/"baseline-reconstruction.json",{"resulting_revision":10,"portable_identity_count":23,
            "normalized_equivalence":True,"behavior_match":True,"interpreter_jit_agree":True,"passed":True})

    def _selected_if(self):
        projection=build_projection(self.ws,self.doc,self.ws.get_revision(self.doc))
        fn=next(x for x in projection.functions if x.symbol_id==self.aliases["score_class.function"])
        return fn.statements[2]

    def _portable_expr(self, expr, function_handle):
        symbols=self.ws.documents[self.doc].symbols
        if expr.kind=="number": return {"kind":"number","value":float(expr.value)}
        if expr.kind in ("variable","result"):
            sid=str(expr.value); sym=symbols.get(sid)
            if sym is None: raise WorkspaceError("SEMANTIC_REFERENCE_MISSING","Expression symbol missing")
            return {"kind":"local_ref","name":sym.name}
        if expr.kind=="call":
            handle=next((h for h,sid in self.aliases.items() if sid==str(expr.value)),None)
            if handle is None: raise WorkspaceError("UNKNOWN_FUNCTION_HANDLE","Call has no portable handle")
            return {"kind":"call","function_handle":handle,"arguments":[self._portable_expr(c,function_handle) for c in expr.children]}
        if expr.kind in ("compare","binary"):
            return {"kind":"binary","operator":str(expr.value),"left":self._portable_expr(expr.children[0],function_handle),"right":self._portable_expr(expr.children[1],function_handle)}
        raise WorkspaceError("UNSUPPORTED_TYPED_EXPRESSION",f"Cannot expose {expr.kind}")

    def _resolve_expr(self,value,function_id):
        if not isinstance(value,dict): raise WorkspaceError("INVALID_EXPRESSION","Typed expression must be an object")
        kind=value.get("kind")
        if kind=="number" and set(value)=={"kind","value"}: return {"kind":"number","value":value["value"]}
        if kind=="local_ref" and set(value)=={"kind","name"}:
            fn=next(f for f in self.ws.documents[self.doc].functions if f["symbol_id"]==function_id)
            sid=next((sid for sid in fn["parameters"] if self.ws.documents[self.doc].symbols[sid].name.casefold()==value["name"].casefold()),None)
            if sid is None: raise WorkspaceError("UNKNOWN_LOCAL_REFERENCE","Parameter reference is not in selected function")
            return {"kind":"symbol_ref","symbol_id":sid}
        if kind=="call" and set(value)=={"kind","function_handle","arguments"}:
            handle=value["function_handle"]
            if handle not in self.discovered: raise WorkspaceError("FUNCTION_NOT_DISCOVERED","Discover called functions before use")
            sid=self.aliases.get(handle)
            if sid is None: raise WorkspaceError("UNKNOWN_FUNCTION_HANDLE","Portable function handle is unknown")
            return {"kind":"call","function_id":sid,"arguments":[self._resolve_expr(x,function_id) for x in value["arguments"]]}
        if kind=="binary" and set(value)=={"kind","operator","left","right"}:
            return {"kind":"binary","operator":value["operator"],"left":self._resolve_expr(value["left"],function_id),"right":self._resolve_expr(value["right"],function_id)}
        raise WorkspaceError("INVALID_EXPRESSION","Unsupported typed condition expression")

    def _all_observations(self,ws,doc,rev,aliases):
        out={"interp":{},"jit":{}}
        keys=[("clamp_score.function","normalize_score"),("is_passing.function","is_passing"),("score_class.function","score_class"),("is_at_cap.function","is_at_cap")]
        for engine in out:
            for x in INPUTS:
                out[engine][str(x)]={key:self.executor.execute_function(ws,doc,rev,aliases[h],[x],engine)["result"] for h,key in keys}
        return out

    def discover(self):
        self.discovered={h for h in self.aliases if h.endswith(".function")}
        rows=[]
        for h in sorted(self.discovered):
            sid=self.aliases[h]; sym=self.ws.documents[self.doc].symbols[sid]
            fn=next(f for f in self.ws.documents[self.doc].functions if f["symbol_id"]==sid)
            rows.append({"handle":h,"name":sym.name,"symbol_id":sid,"parameters":[self.ws.documents[self.doc].symbols[p].name for p in fn["parameters"]],"return_type":"numeric"})
        self._history("symbol_discovered","pi_model_tool",revision=10,functions=rows)
        self._emit({"event_type":"selection","revision":10,"provenance":"Genuine Pi discovery","title":"Callable functions discovered","description":"Agent discovered IS_AT_CAP and SCORE_CLASS dependencies by portable identity.","focus":{"handles":sorted(self.discovered),"mapping":"verified_function_boundary"},"dependencies":self.dependencies()})
        return {"revision":self.ws.get_revision(self.doc),"functions":rows}

    def inspect(self):
        if "score_class.function" not in self.discovered or "is_at_cap.function" not in self.discovered:
            raise WorkspaceError("FUNCTION_NOT_DISCOVERED","Discover functions before inspecting target")
        result={"revision":10,"structure":self.baseline,"conditional_edit_target":{"function_handle":"score_class.function","control_path":PATH,
            "anchor_statement_handle":ANCHOR,"anchor_statement_id":self.aliases[ANCHOR],"expected_condition":self.expected_old,
            "affected_assignment_handles":[ANCHOR],"mapping":"verified_function_boundary"}}
        self._history("program_inspected","pi_model_tool",revision=10,target=ANCHOR)
        return result

    def _operation(self,params):
        allowed={"expected_revision","function_handle","control_path","anchor_statement_handle","expected_condition","condition"}
        if set(params)!=allowed: raise WorkspaceError("UNKNOWN_SEMANTIC_FIELD","Conditional edit request has missing or unsupported semantic fields")
        rev=self.ws.get_revision(self.doc)
        if params["expected_revision"]!=rev: raise WorkspaceError("STALE_REVISION","Conditional edit revision is stale")
        if self.committed: raise WorkspaceError("MISSION_EDIT_LIMIT","Mission authorizes one conditional replacement")
        if params["function_handle"]!=self.contract["function_handle"] or params["function_handle"] not in self.discovered:
            raise WorkspaceError("MISSION_TARGET_DENIED","Only discovered SCORE_CLASS may be edited")
        if params["control_path"]!=self.contract["control_path"] or params["anchor_statement_handle"]!=self.contract["anchor_statement_handle"]:
            raise WorkspaceError("MISSION_TARGET_DENIED","Conditional path and semantic assignment anchor do not match contract")
        if params["expected_condition"]!=self.expected_old:
            raise WorkspaceError("EXPECTED_IF_CONDITION_MISMATCH","Expected condition does not match verified baseline")
        fnid=self.aliases["score_class.function"]
        resolved_condition=self._resolve_expr(params["condition"],fnid)
        expected_new=self.contract["replacement_condition"]
        if params["condition"]!=expected_new:
            raise WorkspaceError("MISSION_CONDITION_DENIED","Only discovered IS_AT_CAP(X)=1 condition is authorized")
        op={"operation":"edit_typed_if_condition","function_id":fnid,"control_path":PATH,
            "anchor_statement_id":self.aliases[ANCHOR],"expected_condition":self._resolve_expr(params["expected_condition"],fnid),
            "condition":resolved_condition}
        return [op]

    def _authorized(self,params):
        ops=self._operation(params); rev=self.ws.get_revision(self.doc)
        candidate_ws=copy.deepcopy(self.ws)
        applied=candidate_ws.apply_transaction(self.doc,rev,copy.deepcopy(ops))
        candidate=senior.normalized_state(projection_semantics(build_projection(candidate_ws,self.doc,applied["revision"])),self.aliases)
        old=copy.deepcopy(self.baseline); fn=next(f for f in old["functions"] if f["handle"]=="score_class.function")
        target=fn["statements"][2]
        target["condition"]=copy.deepcopy(candidate["functions"][next(i for i,f in enumerate(candidate["functions"]) if f["handle"]=="score_class.function")]["statements"][2]["condition"])
        if candidate!=old: raise WorkspaceError("MISSION_CANDIDATE_MISMATCH","Candidate changed entities outside the authorized IF condition")
        edges={(e["caller"],e["callee"]) for e in self._dependency_edges(candidate)}
        expected={(e["caller"],e["callee"]) for e in self._dependency_edges(self.baseline)}|{("score_class.function","is_at_cap.function")}
        if edges!=expected: raise WorkspaceError("MISSION_DEPENDENCY_CHANGED","Candidate call graph differs from authorized one-edge extension")
        for h in ("clamp_score.function","is_passing.function","is_at_cap.function"):
            if senior.find_function(candidate,h)!=senior.find_function(self.baseline,h): raise WorkspaceError("MISSION_UNCHANGED_FUNCTION",f"{h} changed")
        before_doc=self.ws.documents[self.doc]; after_doc=candidate_ws.documents[self.doc]
        before={t.uid:t for t in before_doc.tokens}; after={t.uid:t for t in after_doc.tokens}
        allowed_line=self._selected_if().line
        removed=set(before)-set(after); added=set(after)-set(before)
        if any(before[uid].line!=allowed_line for uid in removed) or any(after[uid].line!=allowed_line for uid in added):
            raise WorkspaceError("MISSION_TOKEN_SCOPE","Token identities changed outside selected condition line")
        shared=set(before)&set(after)
        if any(before[uid].text!=after[uid].text for uid in shared):
            raise WorkspaceError("MISSION_TOKEN_SCOPE","Unrelated canonical tokens changed")
        before_line=[t.uid for t in before_doc.tokens if t.line==allowed_line]
        after_line=[t.uid for t in after_doc.tokens if t.line==allowed_line]
        first=next(i for i,uid in enumerate(before_line) if before[uid].kind!="WS")
        last=next(i for i in range(len(before_line)-1,-1,-1) if before[before_line[i]].kind!="WS")
        start=first+1; end=last-1
        if (after_line[:start]!=before_line[:start]
                or after_line[-(len(before_line)-end-1):] != before_line[end+1:]):
            raise WorkspaceError("MISSION_TOKEN_SCOPE","IF markers, surrounding whitespace or other line tokens changed")
        changed=sorted(removed|added)
        observations=self._all_observations(candidate_ws,self.doc,applied["revision"],self.aliases)
        if observations["interp"]!=observations["jit"] or observations["interp"]!=self._all_observations(self.ws,self.doc,rev,self.aliases)["interp"]:
            raise WorkspaceError("MISSION_BEHAVIOR_CHANGED","Refactor must preserve all specified observations")
        return ops,candidate,{"changed_token_ids":changed,"candidate_observations":observations,"added_edge":["score_class.function","is_at_cap.function"]}

    def preview(self,params,rid):
        rev=self.ws.get_revision(self.doc)
        try: ops,candidate,meta=self._authorized(params)
        except WorkspaceError as e:
            self._history("transaction_rejected","mission_gateway",request_id=rid,code=e.code,revision=rev,authoritative_state_unchanged=True)
            self._emit({"event_type":"rejection","revision":rev,"provenance":"MissionGateway rejection","title":"Conditional edit rejected","description":e.message,"outcome":{"code":e.code,"committed":False}})
            return {"ok":False,"code":e.code,"message":e.message,"revision":rev,"revision_unchanged":True,"authoritative_workspace_changed":False}
        tx,raw=self.transactions.preview(operation_kind="edit_typed_if_condition",base_revision=rev,operations=ops,candidate=candidate,metadata={"request":params,"impact":meta})
        self._history("preview_accepted","mission_gateway",transaction_id=tx,base_revision=rev,diff=raw.get("diff"),impact=meta)
        self._emit({"event_type":"preview","revision":rev,"provenance":"Genuine Pi proposal · MissionGateway accepted preview","title":"SCORE_CLASS condition preview","description":"Candidate replaces NORMALIZE_SCORE(X)=50 with IS_AT_CAP(X)=1. Committed source remains revision 10.","focus":{"handles":["score_class.function",ANCHOR,"is_at_cap.function"],"mapping":"verified_function_boundary"},"preview":{"status":"accepted","diff":raw.get("diff"),"candidate_revision":rev+1},"dependencies":self.dependencies(),"outcome":{"authorized":True,"committed":False}})
        self._history("operation_proposed","pi_model_tool",request_id=rid,transaction_id=tx,arguments=params)
        return {"ok":True,"accepted":True,"transaction_id":tx,"base_revision":rev,"expected_result_revision":rev+1,"candidate_is_preview_only":True,"diff":raw.get("diff"),"impact":meta}

    def commit(self,params,rid):
        if set(params)!={"transaction_id"}: raise WorkspaceError("UNKNOWN_SEMANTIC_FIELD","commit accepts only transaction_id")
        tx=params["transaction_id"]
        def check(record,rev):
            ops,candidate,meta=self._authorized(record["metadata"]["request"])
            return ops,candidate,{"impact":meta}
        try: receipt=self.transactions.commit(tx,check)
        except WorkspaceError as exc:
            return {"ok":False,"committed":False,"code":exc.code,"message":exc.message,
                "revision":self.ws.get_revision(self.doc),"authoritative_workspace_changed":False}
        self.committed=True; rev=receipt.revision; code=self.ws.render_document(self.doc)
        edit={"operation":"edit_typed_if_condition","mission_id":MISSION,"function_handle":"score_class.function","control_path":PATH,
            "anchor_statement_handle":self.contract["anchor_statement_handle"],"expected_condition":self.expected_old,"condition":self.contract["replacement_condition"]}
        self.constructive_ops.append(edit)
        stream={"schema":"basic-workspace.constructive-metafile","version":1,"execution_profile_id":PROFILE_ID,"portable_handles":sorted(self.aliases),"operations":self.constructive_ops}
        self.write_json(self.output/"constructive-operations.json",stream)
        self.write_json(self.output/"visual-source.json",{"schema":"basic-workspace.visual-source","version":1,"campaign":{"id":MISSION,"title":self.contract["objective"],"filename":"SCORES.bas"},"initial":{"revision":10,"code":self.initial_code,"dependencies":self.dependencies()},"snapshots":{"10":self.initial_code,str(rev):code}})
        self._history("transaction_committed","mission_gateway",request_id=rid,transaction_id=tx,base_revision=10,resulting_revision=rev,operation="edit_typed_if_condition",semantic_snapshot=self._normalized(rev),changed_token_ids=receipt.metadata["impact"]["changed_token_ids"],preserved_alias_count=len(self.aliases))
        self._emit({"event_type":"commit","revision":rev,"snapshot":code,"provenance":"Workspace atomic semantic transaction · genuine Pi commit","title":"SCORE_CLASS condition refactored","description":"One typed IF condition changed; assignments and branch structure were preserved.","focus":{"handles":["score_class.function",ANCHOR,"is_at_cap.function"],"mapping":"verified_function_boundary"},"dependencies":self.dependencies_after(),"outcome":{"committed":True,"workspace_revision":rev,"changed_token_ids":receipt.metadata["impact"]["changed_token_ids"]}})
        return {"ok":True,"committed":True,"revision":rev,"preserved_semantic_identities":len(self.aliases),"changed_token_ids":receipt.metadata["impact"]["changed_token_ids"]}

    def dependencies_after(self):
        state=self._normalized(self.ws.get_revision(self.doc)); names={f["handle"]:f["name"] for f in state["functions"]}
        return [{"caller":names[a],"callee":names[b]} for a,b in sorted({(e["caller"],e["callee"]) for e in self._dependency_edges(state)})]

    def validate(self,params,actor="host"):
        rev=self.ws.get_revision(self.doc)
        if params.get("expected_revision")!=rev: return {"reliable":False,"code":"STALE_VALIDATION_REVISION","mission_complete":False,"executed_revision":None}
        observed=self._all_observations(self.ws,self.doc,rev,self.aliases)
        expected={engine:{} for engine in ("interp","jit")}
        for engine in expected:
            for x in INPUTS:
                n=max(0,min(50,x)); score=0 if n<20 else 1 if n<45 else 2 if n<50 else 3
                expected[engine][str(x)]={"normalize_score":float(n),"is_passing":float(n>=45),"score_class":float(score),"is_at_cap":float(n>=50)}
        equal=observed==expected; agree=observed["interp"]==observed["jit"]
        state=self._normalized(rev); edges={(e["caller"],e["callee"]) for e in self._dependency_edges(state)}
        base={(e["caller"],e["callee"]) for e in self._dependency_edges(self.baseline)}
        edge=self.contract["authorized_new_dependency_edge"]
        dep=edges==base|{(edge["caller_handle"],edge["callee_handle"])}
        assignments_preserved=all(senior.find_function(state,"score_class.function")["statements"][i]==senior.find_function(self.baseline,"score_class.function")["statements"][i] for i in (0,1,3))
        unchanged=all(senior.find_function(state,h)==senior.find_function(self.baseline,h) for h in ("clamp_score.function","is_passing.function","is_at_cap.function"))
        complete=bool(self.committed and equal and agree and dep and assignments_preserved and unchanged and len(self.aliases)==23)
        result={"schema":"basic-workspace.cycle28-validation","version":1,"actor":actor,"revision":rev,"executed_revision":rev,"observed_results":observed,"expected_results":expected,"expectation_source":"host-owned independent oracle","values_match":equal,"engines_agree":agree,"dependency_graph_correct":dep,"existing_assignments_preserved":assignments_preserved,"other_functions_unchanged":unchanged,"mission_complete":complete}
        if complete:
            stream={"schema":"basic-workspace.constructive-metafile","version":1,"execution_profile_id":PROFILE_ID,"portable_handles":sorted(self.aliases),"operations":self.constructive_ops}
            rw=Workspace(); rd=rw.create_empty_document("memory://cycle28/replay.bas")["document_id"]
            replay=replay_constructive_stream(rw,rd,stream["operations"],expected_start_revision=1,
                expected_final_handles=stream["portable_handles"])
            ra=replay.live_handles
            rrev=rw.get_revision(rd); rstate=senior.normalized_state(projection_semantics(build_projection(rw,rd,rrev)),ra)
            robs=self._all_observations(rw,rd,rrev,ra)
            replay_ok=rstate==state and robs==observed and robs["interp"]==robs["jit"] and len(ra)==23
            result["replay"]={"passed":replay_ok,"structural_equivalence":rstate==state,"binding_equivalence":self._dependency_edges(rstate)==self._dependency_edges(state),"behavioral_equivalence":robs==observed,"revision":rrev,"identity_remappings":sum(ra[h]!=self.aliases[h] for h in ra)}
            result["mission_complete"] &= replay_ok
            self.write_json(self.output/"replay-equivalence.json",result["replay"])
        self.write_json(self.output/"validation.json",result)
        self._history("program_validated",actor,revision=rev,executed_revision=rev,passed=result["mission_complete"],engines_agree=agree)
        self._emit({"event_type":"validation","revision":rev,"provenance":f"Independent {actor} MIR validation","title":f"Validation {'passed' if result['mission_complete'] else 'failed'}","description":"All four functions were checked through interpreter and JIT against the 16-input oracle and fresh replay.","observations":observed,"dependencies":self.dependencies_after(),"outcome":{"passed":result["mission_complete"],"executed_revision":rev}})
        return result

    def handle(self,method,params,rid):
        if method=="record_pi_event": return super().record_pi_event(params)
        if method=="discover_functions":
            if params: raise WorkspaceError("UNKNOWN_SEMANTIC_FIELD","discover accepts no semantic arguments")
            return self.discover()
        if method=="inspect_program":
            if params: raise WorkspaceError("UNKNOWN_SEMANTIC_FIELD","inspect accepts no semantic arguments")
            return self.inspect()
        if method=="preview_conditional_edit": return self.preview(params,rid)
        if method=="commit_preview": return self.commit(params,rid)
        if method=="validate_mission": return self.validate(params,"pi_tool")
        if method=="host_validate": return self.validate(params,"host")
        if method=="get_status": return {"revision":self.ws.get_revision(self.doc),"committed":self.committed,"portable_handles":len(self.aliases),"discovered":sorted(self.discovered)}
        if method=="record_agent_status": return {"ok":True}
        if method=="finalize_session":
            from pi_lifecycle import completion_states
            life=params.get("pi_lifecycle") or {}; states=completion_states(committed=self.committed,validation=params.get("validation"),timed_out=bool(params.get("timed_out")),exit_code=params.get("pi_exit_code"),agent_end_seen=bool(life.get("agent_end_seen")),agent_settled_seen=bool(life.get("agent_settled_seen")),pending_tool_count=len(life.get("pending_tools",{})),authorization_status="authorized" if self.committed else "not_committed")
            self.write_json(self.output/"completion-states.json",{"completion_states":states,"lifecycle":life});return {"completion_states":states}
        raise WorkspaceError("UNKNOWN_TOOL",f"Unsupported tool {method}")

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--output",type=Path,required=True); ap.add_argument("--contract",type=Path,required=True); ap.add_argument("--port",type=int,default=0); a=ap.parse_args()
    g=Cycle28Gateway(a.output,a.contract)
    with Server(("127.0.0.1",a.port),g) as server:
        print(json.dumps({"ready":True,"host":"127.0.0.1","port":server.server_address[1],"revision":g.ws.get_revision(g.doc),"identity_count":len(g.aliases),"baseline_verified":True}),flush=True); server.serve_forever()
if __name__=="__main__":main()
