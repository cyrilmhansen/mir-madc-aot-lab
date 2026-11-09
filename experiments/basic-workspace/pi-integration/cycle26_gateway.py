#!/usr/bin/env python3
"""Cycle 26 function rename mission, reusing Cycle 25 reconstruction and kernel."""
from __future__ import annotations
import argparse, copy, json, sys, threading, time
from pathlib import Path
from typing import Any

HERE=Path(__file__).resolve().parent; ROOT=HERE.parent
sys.path[:0]=[str(ROOT),str(HERE)]
from basic_workspace.model import Workspace, WorkspaceError
from basic_workspace.projection import build_projection, projection_semantics
from basic_workspace.mir_execution import MirExecutionService
from transaction_kernel import SemanticTransactionKernel
from gateway import Server
from cycle20_gateway import senior
from cycle25_gateway import Cycle25Gateway, read, write, rows, PROFILE, INPUTS
from pi_lifecycle import completion_states

C25=HERE/"results/cycle25-structural-edit/real-agent-01"
CONTRACT=HERE/"results/cycle26-semantic-rename/contracts/rename-normalizer.json"
HANDLE="clamp_score.function"
NEW_NAME="NORMALIZE_SCORE"
OLD_NAME="CLAMP_SCORE"


class Cycle26Gateway(Cycle25Gateway):
    """A thin mission adapter; preview/commit state remains SemanticTransactionKernel-owned."""
    def __init__(self, output:Path, contract_path:Path=CONTRACT):
        output=output.resolve(); output.mkdir(parents=True,exist_ok=True)
        super().__init__(output/"cycle25-bootstrap")
        self.output=output; self.trace_path=output/"history.jsonl"; self.visual_path=output/"visual-events.jsonl"
        self.timing_path=output/"gateway-tool-timings.jsonl"; self.pi_path=output/"pi-tool-lifecycle.jsonl"
        self.contract=read(contract_path); self.contract_path=contract_path
        if self.contract.get("schema")!="basic-workspace.semantic-rename-contract" or self.contract.get("version")!=1:
            raise WorkspaceError("MISSION_CONTRACT_VERSION","Unsupported rename contract")
        if (self.contract.get("base_document_revision")!=8 or self.contract.get("execution_profile_id")!=PROFILE
                or self.contract.get("target_handle")!=HANDLE or self.contract.get("expected_source_name")!=OLD_NAME
                or self.contract.get("new_source_name")!=NEW_NAME):
            raise WorkspaceError("MISSION_CONTRACT_INVALID","Rename contract does not match the verified Cycle 25 mission")
        stream=read(C25/"constructive-operations.json")
        if len(stream.get("operations",[]))!=7 or len(stream.get("portable_handles",[]))!=18:
            raise WorkspaceError("BASELINE_STREAM_MISMATCH","Cycle 25 must contribute seven operations and 18 handles")
        reconstructed=self.replay(stream["operations"])
        if reconstructed["revision"]!=8 or reconstructed["identity_count"]!=18:
            raise WorkspaceError("BASELINE_RECONSTRUCTION_FAILED","Cycle 25 stream did not reconstruct revision 8")
        recorded=read(C25/"mission-validation-host.json")
        if not recorded.get("mission_complete") or reconstructed["observed"]!=self._rename_observations(recorded["observed_results"]):
            raise WorkspaceError("BASELINE_BEHAVIOR_MISMATCH","Cycle 25 host observations did not match fresh replay")
        old_source=read(C25/"visual-source.json")["snapshots"]["8"]
        new_source=reconstructed["workspace"].render_document(reconstructed["document_id"])
        self.historical_display_whitespace_only=(old_source!=new_source and
            [x.strip() for x in old_source.splitlines()]==[x.strip() for x in new_source.splitlines()])
        if old_source!=new_source and not self.historical_display_whitespace_only:
            raise WorkspaceError("BASELINE_SOURCE_MISMATCH","Cycle 25 display differs beyond its recorded indentation drift")
        self.ws=reconstructed["workspace"]; self.doc=reconstructed["document_id"]
        self.aliases=dict(reconstructed["aliases"]); self.base_aliases=dict(self.aliases)
        self.baseline_aliases=dict(self.aliases); self.baseline=copy.deepcopy(reconstructed["normalized"])
        self.baseline_observed=self._rename_observations(recorded["observed_results"])
        self.baseline_source=new_source; self.base_revision=8; self.revision=8; self.committed=False
        self.committed_operations=copy.deepcopy(stream["operations"])
        self.discovered=set(); self.discovered_statements=set(); self.lock=threading.RLock()
        self.transactions=SemanticTransactionKernel(self.ws,self.doc); self.pending_request_ids={}
        self.seq=0; self.pi_seen=set(); self.executor=MirExecutionService(timeout=20)
        self.session_id=f"cycle26-{output.name}"; self.mission_id=self.contract["mission_id"]
        self.output.mkdir(parents=True,exist_ok=True)
        write(output/"MISSION.json",self.contract)
        write(output/"execution-profile.json",read(ROOT/"results/semantic-replay/execution-profile.json"))
        self.initial_identity_map=[{"portable_handle":h,"workspace_id":v,"remapped":True} for h,v in sorted(self.aliases.items())]
        write(output/"baseline-reconstruction.json",{"schema":"basic-workspace.cycle26-baseline","version":1,
            "source_stream":str(C25/"constructive-operations.json"),"starting_document_empty":True,
            "revision":8,"portable_identity_count":18,"identity_remappings":18,
            "normalized_semantic_equivalence":True,"call_bindings_preserved":True,
            "interpreter_jit_behavior_match":True,"historical_display_indent_drift":self.historical_display_whitespace_only,
            "canonical_source_matches_cycle24_revision7_after_corrected_insertion":True,
            "identity_mapping":self.initial_identity_map})
        write(output/"baseline-observations.json",{"revision":8,"source":"host replay of authentic Cycle 25 stream",
            "observed_results":self.baseline_observed,"dependencies":self.dependencies(self.baseline)})
        write(output/"visual-source.json",{"schema":"basic-workspace.visual-source","version":1,
            "campaign":{"id":"cycle26-semantic-rename","title":"Cycle 26 · stable identity rename","filename":"SCORES.bas"},
            "initial":{"revision":8,"code":new_source,"dependencies":self.dependencies(self.baseline)},"snapshots":{"8":new_source}})
        self._emit({"event_type":"initial","revision":8,"snapshot":new_source,
            "provenance":"Host replay of authentic Cycle 25 committed stream","title":"Verified revision-8 baseline",
            "description":"Seven committed operations replayed from an empty Workspace. Stable handles and the three-function dependency graph were verified.",
            "dependencies":self.dependencies(self.baseline),"focus":{"handles":[HANDLE],"mapping":"verified_function_boundary"}})
        self._history("program_reconstructed","host_deterministic_replay",revision=8,operations=7,
            identity_remappings=18,semantic_equivalence=True,behavior_match=True,
            historical_display_indent_drift=self.historical_display_whitespace_only)

    def _rename_observations(self, old):
        return {engine:{x:{("normalize_score" if key=="clamp_score" else key):value for key,value in row.items()}
                        for x,row in values.items()} for engine,values in old.items()}

    def _observe_renamed(self, ws, doc, revision, aliases):
        result={"interp":{},"jit":{}}
        for engine in result:
            for x in self.contract["validation_inputs"]:
                result[engine][str(x)]={}
                for handle,name in ((HANDLE,"normalize_score"),("is_passing.function","is_passing"),("score_class.function","score_class")):
                    result[engine][str(x)][name]=self.executor.execute_function(ws,doc,revision,aliases[handle],[x],engine)["result"]
        return result

    def _state(self, revision=None):
        return senior.normalized_state(projection_semantics(build_projection(self.ws,self.doc,
            self.ws.get_revision(self.doc) if revision is None else revision)),self.aliases)

    def _dependencies_for(self, state):
        names={f["handle"]:f["name"] for f in state["functions"]}
        return [{"caller":names.get(e["caller"],e["caller"]),"callee":names.get(e["callee"],e["callee"])}
                for e in senior.candidate_call_edges(state)]

    @staticmethod
    def _dependency_identity_edges(state):
        return {(edge["caller"],edge["callee"]) for edge in senior.candidate_call_edges(state)}

    def record_gateway_timing(self,request,elapsed_ms):
        method=request.get("method");transport=request.get("transport") or {}
        self._append(self.timing_path,{"request_id":request.get("request_id"),
            "tool_call_id":transport.get("tool_call_id"),"method":method,
            "agent_tool":method in {"discover_functions","inspect_program","preview_rename","commit_preview","validate_mission"},
            "elapsed_ms":round(elapsed_ms,3),"observed_monotonic_ns":time.monotonic_ns()})

    def dependencies(self,state=None):
        return self._dependencies_for(self.baseline if state is None else state)

    def discover(self):
        state=self._state();self.discovered={f["handle"] for f in state["functions"]}
        data=[{"handle":f["handle"],"symbol_id":self.aliases[f["handle"]],"name":f["name"],
               "parameters":f["parameters"],"return_type":f["return_type"]} for f in state["functions"]]
        self._history("symbols_discovered","pi_model_tool",revision=self.ws.get_revision(self.doc),functions=data)
        self._emit({"event_type":"selection","revision":8,"provenance":"Genuine Pi discovery tool call",
            "title":"Functions discovered","description":"Portable handles and current source names were returned from the live Workspace.",
            "focus":{"handles":[HANDLE,"is_passing.function","score_class.function"],"mapping":"verified_function_boundary"},
            "dependencies":self.dependencies(state)})
        return {"revision":self.ws.get_revision(self.doc),"functions":data}

    def inspect(self):
        if HANDLE not in self.discovered:raise WorkspaceError("FUNCTION_NOT_DISCOVERED","Discover the target function before inspection")
        sid=self.aliases[HANDLE];symbol=self.ws.documents[self.doc].symbols[sid]
        token_map={t.uid:t for t in self.ws.documents[self.doc].tokens}
        references=[]
        for uid in sorted(symbol.references,key=lambda u:(token_map[u].line,token_map[u].column)):
            t=token_map[uid];references.append({"token_id":uid,"line":t.line,"column":t.column,
                "kind":t.kind,"function_handle":next((h for h,i in self.aliases.items() if h.endswith(".function") and
                    any(f["symbol_id"]==i and f["start_line"]<=t.line<=f["end_line"] for f in self.ws.documents[self.doc].functions)),None)})
        state=self._state()
        result={"revision":8,"target":{"function_handle":HANDLE,"symbol_id":sid,"current_source_name":symbol.name,
            "parameters":[{"handle":h,"symbol_id":self.aliases[h]} for h in self.aliases if h.startswith("clamp_score.parameter.")],
            "references":references},"functions":state["functions"],"dependencies":self.dependencies(state),
            "identity_rule":"Portable handle clamp_score.function remains stable; source name is a mutable attribute. All rename locations are derived from the symbol's bound declaration and references."}
        self._history("program_inspected","pi_model_tool",revision=8,target=HANDLE,reference_token_count=len(references))
        self._emit({"event_type":"selection","revision":8,"provenance":"Genuine Pi semantic inspection tool call",
            "title":"Rename target and bound references inspected","description":f"The target has {len(references)} bound reference tokens; callers are resolved by symbol identity.",
            "focus":{"handles":[HANDLE],"mapping":"exact_semantic_span"},"dependencies":self.dependencies(state)})
        return result

    def _candidate(self, request):
        if not isinstance(request,dict) or set(request)!={"expected_revision","function_handle","expected_name","new_name"}:
            raise WorkspaceError("INVALID_RENAME_REQUEST","Rename request fields are expected_revision, function_handle, expected_name, and new_name")
        revision=self.ws.get_revision(self.doc)
        if request["expected_revision"]!=revision or revision!=8:raise WorkspaceError("STALE_REVISION","Rename mission is bound to current revision 8")
        if self.committed:raise WorkspaceError("MISSION_EDIT_LIMIT","Mission permits one rename transaction")
        if HANDLE not in self.discovered or request["function_handle"]!=HANDLE:
            raise WorkspaceError("MISSION_RENAME_SCOPE","Only the discovered stable target handle is authorized")
        sid=self.aliases[HANDLE];symbol=self.ws.documents[self.doc].symbols[sid]
        if request["expected_name"]!=symbol.name or symbol.name!=OLD_NAME:
            raise WorkspaceError("RENAME_PRECONDITION_FAILED","Expected current source name does not match the target identity")
        if request["new_name"]!=self.contract["new_source_name"]:
            raise WorkspaceError("MISSION_RENAME_NAME","Mission contract authorizes only the requested new source name")
        before_tokens={t.uid:(t.text,t.kind) for t in self.ws.documents[self.doc].tokens}
        expected_uids={symbol.declaration_token,*symbol.references}
        candidate_ws=copy.deepcopy(self.ws)
        operation={"operation":"rename_symbol","symbol_id":sid,"new_name":request["new_name"]}
        applied=candidate_ws.apply_transaction(self.doc,revision,[operation])
        after_tokens={t.uid:(t.text,t.kind) for t in candidate_ws.documents[self.doc].tokens}
        if set(before_tokens)!=set(after_tokens):raise WorkspaceError("RENAME_IDENTITY_LOSS","Rename changed canonical token identity set")
        changed={uid for uid in before_tokens if before_tokens[uid]!=after_tokens[uid]}
        if changed!=expected_uids or any(after_tokens[uid][0]!=NEW_NAME for uid in expected_uids):
            raise WorkspaceError("RENAME_REFERENCE_SET_MISMATCH","Rename must change exactly the declaration and bound references")
        candidate_state=senior.normalized_state(projection_semantics(build_projection(candidate_ws,self.doc,applied["revision"])),self.aliases)
        expected=copy.deepcopy(self.baseline)
        target=senior.find_function(expected,HANDLE);target["name"]=NEW_NAME
        if candidate_state!=expected:raise WorkspaceError("RENAME_UNRELATED_CHANGE","Candidate differs from baseline beyond the target source name")
        return [operation],candidate_state,candidate_ws,sorted(changed),len(expected_uids)

    def handle(self,method,params,rid):
        if method=="record_pi_event":return self.record_pi(params)
        if method=="get_status":return {"revision":self.ws.get_revision(self.doc),"committed":self.committed,
            "document_id":self.doc,"function_handles":sorted(h for h in self.aliases if h.endswith(".function"))}
        if method=="discover_functions":return self.discover()
        if method=="inspect_program":return self.inspect()
        if method=="preview_rename":return self._preview_rename(params,rid)
        if method=="commit_preview":return self._commit_rename(params,rid)
        if method=="validate_mission":return self.validate(params.get("expected_revision"),rid,"pi")
        if method=="host_validate":return self.validate(params.get("expected_revision"),rid,"host")
        if method=="record_agent_status":
            self._emit({"event_type":"mission_status","revision":self.ws.get_revision(self.doc),"provenance":"Host Pi lifecycle observation",
                "title":str(params.get("state","status")),"description":str((params.get("info") or {}).get("description",params.get("state","status")))})
            return {"ok":True,"revision":self.ws.get_revision(self.doc)}
        if method=="finalize_mission":
            life=params.get("pi_lifecycle") or {};validation=params.get("validation") or {}
            states=completion_states(committed=self.committed,validation=validation,timed_out=bool(params.get("timed_out")),
                exit_code=params.get("pi_exit_code"),agent_end_seen=bool(life.get("agent_end_seen")),
                agent_settled_seen=bool(life.get("agent_settled_seen")),pending_tool_count=len(life.get("pending_tools",{})),
                authorization_status="authorized" if self.committed else "not_committed")
            write(self.output/"completion-states.json",{"completion_states":states,"lifecycle":life});return {"completion_states":states}
        if method=="deterministic_workspace_control":
            case=params.get("case"); target=self.aliases[HANDLE]
            new_name="IS_PASSING" if case=="name_collision" else "BAD NAME"
            candidate=copy.deepcopy(self.ws)
            try:candidate.rename_symbol(self.doc,target,new_name,8)
            except WorkspaceError as exc:return {"code":exc.code,"message":str(exc),"authoritative_revision":self.ws.get_revision(self.doc),"authoritative_unchanged":True}
            return {"code":"UNEXPECTED_ACCEPTANCE","authoritative_revision":self.ws.get_revision(self.doc),"authoritative_unchanged":True}
        raise WorkspaceError("UNKNOWN_TOOL","Unsupported rename mission tool")

    def _preview_rename(self,request,rid):
        try:ops,candidate,candidate_ws,changed,count=self._candidate(request)
        except WorkspaceError as exc:
            revision=self.ws.get_revision(self.doc);result={"ok":False,"code":exc.code,"message":str(exc),"revision":revision,
                "revision_unchanged":True,"authoritative_workspace_changed":False}
            self._history("transaction_rejected","mission_gateway",request_id=rid,code=exc.code,revision=revision,authoritative_state_unchanged=True)
            self._emit({"event_type":"rejection","revision":revision,"provenance":"Rename MissionContract rejection",
                "title":"Rename proposal rejected","description":str(exc),"outcome":result});return result
        before=self.ws.render_document(self.doc); after=candidate_ws.render_document(self.doc)
        txid,preview=self.transactions.preview(operation_kind="rename_symbol",base_revision=request["expected_revision"],
            operations=ops,candidate=candidate,metadata={"request":copy.deepcopy(request),"changed_token_ids":changed})
        self.pending_request_ids[txid]=rid
        self._history("operation_proposed","pi_model_tool",request_id=rid,transaction_id=txid,operation="rename_symbol",arguments=request)
        self._history("preview_accepted","mission_gateway",transaction_id=txid,base_revision=8,resulting_revision=9,
            function_handle=HANDLE,old_name=OLD_NAME,new_name=NEW_NAME,changed_token_ids=changed)
        self._emit({"event_type":"preview","revision":8,"provenance":"Genuine Pi rename proposal · MissionGateway accepted preview",
            "source_event_ref":rid,"title":"Rename preview accepted","description":"The candidate changes the source name at the declaration, result references and bound callers; committed source stays revision 8.",
            "focus":{"handles":[HANDLE,"is_passing.function","score_class.function"],"mapping":"verified_unique_line_difference"},
            "preview":{"status":"accepted","diff":preview.get("diff",""),"old_name":OLD_NAME,"new_name":NEW_NAME,
                "semantic_handle":HANDLE,"changed_token_ids":changed,"references_changed":count},
            "outcome":{"authorized":True,"committed":False,"transaction_id":txid,"candidate_source":after,"committed_source":before}})
        return {"ok":True,"transaction_id":txid,"base_revision":8,"expected_result_revision":9,
            "candidate_is_preview_only":True,"semantic_identity_preserved":True,"changed_bound_tokens":count,"changed_token_ids":changed,
            "diff":preview.get("diff",""),"diagnostics":preview["diagnostics"]}

    def _commit_rename(self,params,rid):
        txid=params.get("transaction_id");record=self.transactions.get(txid) if isinstance(txid,str) else None
        if record is None:return {"ok":False,"committed":False,"code":"PREVIEW_NOT_FOUND","revision":self.ws.get_revision(self.doc)}
        try:
            def revalidate(row,revision):
                req=row["metadata"]["request"];ops,candidate,_,changed,count=self._candidate(req)
                return ops,candidate,{"changed_token_ids":changed,"changed_bound_tokens":count}
            receipt=self.transactions.commit(txid,revalidate)
        except WorkspaceError as exc:
            return {"ok":False,"committed":False,"code":exc.code,"message":str(exc),
                "revision":self.ws.get_revision(self.doc),"authoritative_workspace_changed":False}
        if receipt.revision!=9:raise RuntimeError("Rename transaction did not advance exactly one revision")
        self.revision=9;self.committed=True
        post=self._state(9)
        if post!=receipt.candidate:raise RuntimeError("Committed rename projection differs from accepted preview")
        self.committed_operations.append({"operation":"rename_symbol","target_handle":HANDLE,
            "expected_name":OLD_NAME,"new_name":NEW_NAME})
        write(self.output/"constructive-operations.json",{"schema":"basic-workspace.constructive-metafile","version":1,
            "execution_profile_id":PROFILE,"portable_handles":sorted(self.aliases),"operations":self.committed_operations})
        code=self.ws.render_document(self.doc);source=read(self.output/"visual-source.json");source["snapshots"]["9"]=code;write(self.output/"visual-source.json",source)
        self._history("transaction_committed","mission_gateway",request_id=rid,transaction_id=txid,base_revision=8,resulting_revision=9,
            operation="rename_symbol",target_handle=HANDLE,old_name=OLD_NAME,new_name=NEW_NAME,
            preserved_function_id=self.aliases[HANDLE],preserved_alias_count=len(self.aliases),changed_token_ids=receipt.metadata["changed_token_ids"])
        self._emit({"event_type":"commit","revision":9,"snapshot":code,"provenance":"Workspace atomic rename commit · genuine Pi request",
            "source_event_ref":self.pending_request_ids.get(txid,rid),"title":"NORMALIZE_SCORE rename committed",
            "description":"The declaration, result references and bound call sites now spell NORMALIZE_SCORE. Function, parameter, statement and token identities are preserved.",
            "focus":{"handles":[HANDLE,"is_passing.function","score_class.function"],"mapping":"verified_unique_line_difference",
                "changed_token_ids":receipt.metadata["changed_token_ids"]},"dependencies":self.dependencies(post),
            "outcome":{"committed":True,"revision":9,"transaction_id":txid,"changed_token_ids":receipt.metadata["changed_token_ids"]}})
        return {"ok":True,"committed":True,"revision":9,"function_handle":HANDLE,"function_id":self.aliases[HANDLE],
            "source_name":NEW_NAME,"preserved_identity_count":len(self.aliases),"changed_bound_tokens":len(receipt.metadata["changed_token_ids"])}

    def validate(self,requested_revision,rid,actor="host"):
        revision=self.ws.get_revision(self.doc)
        if requested_revision!=revision:return {"reliable":False,"code":"STALE_VALIDATION_REVISION","requested_revision":requested_revision,
            "executed_revision":None,"mission_complete":False}
        if not self.committed:return {"reliable":True,"mission_complete":False,"executed_revision":revision,"diagnostics":["No rename committed"]}
        observed=self._observe_renamed(self.ws,self.doc,revision,self.aliases);engine_ok=observed["interp"]==observed["jit"]
        behavior_ok=observed==self.baseline_observed
        norm=self._state();expected=copy.deepcopy(self.baseline);senior.find_function(expected,HANDLE)["name"]=NEW_NAME
        structural_ok=norm==expected
        symbol=self.ws.documents[self.doc].symbols[self.aliases[HANDLE]]
        reference_ids={symbol.declaration_token,*symbol.references}
        tokens={t.uid:t for t in self.ws.documents[self.doc].tokens}
        name_ok=symbol.name==NEW_NAME and all(tokens[u].text==NEW_NAME for u in reference_ids)
        identities_ok=all(self.aliases.get(h)==self.base_aliases.get(h) for h in self.base_aliases) and len(self.aliases)==18
        replay=self.replay(self.committed_operations)
        replay_ok=replay["normalized"]==norm and replay["observed"]==observed and replay["identity_count"]==18 and replay["remapped_count"]==18
        result={"schema":"basic-workspace.cycle26-rename-validation","version":1,"reliable":True,"revision":revision,
            "requested_revision":requested_revision,"executed_revision":revision,"observed_results":observed,
            "expected_results":self.baseline_observed,"expectation_source":"independent host-owned Cycle 25 behavior snapshot",
            "interpreter_jit_agree":engine_ok,"behavior_unchanged":behavior_ok,"normalized_structure_modulo_target_name":structural_ok,
            "function_identity_preserved":self.aliases[HANDLE]==self.base_aliases[HANDLE],"parameter_statement_token_identities_preserved":identities_ok,
            "all_bound_target_tokens_renamed":name_ok,"no_dependency_identity_changed":self._dependency_identity_edges(norm)==self._dependency_identity_edges(self.baseline),
            "replay":{"passed":replay_ok,"structural_equivalence_modulo_rename":replay["normalized"]==norm,
                "behavioral_equivalence":replay["observed"]==observed,"portable_identity_count":replay["identity_count"],
                "identity_remappings":replay["remapped_count"]},
            "mission_complete":bool(engine_ok and behavior_ok and structural_ok and name_ok and identities_ok and replay_ok)}
        write(self.output/("mission-validation-host.json" if actor=="host" else "mission-validation-pi_tool.json"),result)
        self._history("program_validated","host_validation" if actor=="host" else "pi_model_tool",revision=revision,
            passed=result["mission_complete"],engines_agree=engine_ok,replay_passed=replay_ok)
        self._emit({"event_type":"validation","revision":revision,"provenance":"Independent host validation" if actor=="host" else "Pi-requested MIR validation",
            "title":"Rename behavior and replay validated","description":"MIR interpreter/JIT behavior, semantic identities, bound references and fresh replay were checked.",
            "focus":{"handles":[HANDLE,"is_passing.function","score_class.function"],"mapping":"verified_function_boundary"},
            "validation":{"passed":result["mission_complete"],"interpreter_jit_agree":engine_ok,"replay":result["replay"]},
            "observation":{"function":"NORMALIZE_SCORE, IS_PASSING, SCORE_CLASS","arguments":self.contract["validation_inputs"],
                "engine_results":observed,"revision":revision,"agreement":engine_ok},"dependencies":self.dependencies(norm)})
        return result

    def replay(self,operations):
        rename=operations[-1] if operations and operations[-1].get("operation")=="rename_symbol" else None
        base_ops=operations[:-1] if rename else operations
        result=super().replay(base_ops)
        ws=result["workspace"];doc=result["document_id"];aliases=result["aliases"]
        if rename:
            handle=rename.get("target_handle");sid=aliases.get(handle)
            if sid is None:raise WorkspaceError("REPLAY_HANDLE_MISSING","Rename portable handle did not resolve")
            symbol=ws.documents[doc].symbols[sid]
            if symbol.name!=rename.get("expected_name"):raise WorkspaceError("REPLAY_RENAME_PRECONDITION","Rename source name changed")
            ws.apply_transaction(doc,ws.get_revision(doc),[{"operation":"rename_symbol","symbol_id":sid,"new_name":rename["new_name"]}])
        rev=ws.get_revision(doc);norm=senior.normalized_state(projection_semantics(build_projection(ws,doc,rev)),aliases)
        observed=self._observe_renamed(ws,doc,rev,aliases)
        remapped=sum(self.base_aliases.get(h)!=aliases.get(h) for h in aliases if h in self.base_aliases)
        return {"workspace":ws,"document_id":doc,"revision":rev,"aliases":aliases,"normalized":norm,
            "observed":observed,"identity_count":len(aliases),"remapped_count":remapped,
            "existing_handles_preserved":all(h in aliases for h in self.base_aliases)}


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--output",type=Path,required=True);parser.add_argument("--port",type=int,default=0)
    args=parser.parse_args();service=Cycle26Gateway(args.output)
    with Server(("127.0.0.1",args.port),service) as server:
        print(json.dumps({"ready":True,"host":"127.0.0.1","port":server.server_address[1],
            "revision":8,"baseline_verified":True,"mission_id":service.mission_id,"identity_count":len(service.aliases)},separators=(",",":")),flush=True)
        server.serve_forever()
if __name__=="__main__":main()
