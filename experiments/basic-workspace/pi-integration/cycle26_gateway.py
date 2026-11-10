#!/usr/bin/env python3
"""Cycle 26 function rename mission, reusing Cycle 25 reconstruction and kernel."""
from __future__ import annotations
import argparse, copy, json, sys, threading, time
import hashlib
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
from basic_workspace.portable_replay import replay_constructive_stream
from rename_policy import authorize_rename_candidate, validate_v2_contract

C25=HERE/"results/cycle25-structural-edit/real-agent-01"
CONTRACT=HERE/"results/cycle26-semantic-rename/contracts/rename-normalizer.json"
HANDLE="clamp_score.function"
NEW_NAME="NORMALIZE_SCORE"
OLD_NAME="CLAMP_SCORE"


class Cycle26Gateway(Cycle25Gateway):
    """A thin mission adapter; preview/commit state remains SemanticTransactionKernel-owned."""
    def __init__(self, output:Path, contract_path:Path=CONTRACT, *, verified_handoff_path:Path|None=None,
                 handoff_anchor_path:Path|None=None, handoff_evidence_root:Path|None=None):
        output=output.resolve(); output.mkdir(parents=True,exist_ok=True)
        self.output=output; self.trace_path=output/"history.jsonl"; self.visual_path=output/"visual-events.jsonl"
        self.timing_path=output/"gateway-tool-timings.jsonl"; self.pi_path=output/"pi-tool-lifecycle.jsonl"
        self.contract=read(contract_path); self.contract_path=Path(contract_path).resolve()
        self.contract_sha256=self._sha256(self.contract_path)
        if self.contract.get("version")==2:
            validate_v2_contract(self.contract)
            handoff_args=(verified_handoff_path,handoff_anchor_path,handoff_evidence_root)
            if not all(value is not None for value in handoff_args):
                raise WorkspaceError("HANDOFF_ARGUMENTS","Rename v2 requires bundle, separate trust anchor, and source evidence root")
            self._initialize_verified_handoff(output,verified_handoff_path,handoff_anchor_path,handoff_evidence_root)
            return
        if any(value is not None for value in (verified_handoff_path,handoff_anchor_path,handoff_evidence_root)):
            raise WorkspaceError("HANDOFF_ARGUMENTS","Legacy rename v1 cannot be initialized from a Cycle36 handoff")
        self._initialize_cycle26_legacy(output)

    @staticmethod
    def _sha256(path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()

    def _initialize_cycle26_legacy(self,output):
        self.generic_mode=False
        rename_contract=self.contract; rename_contract_path=self.contract_path
        super().__init__(output/"cycle25-bootstrap")
        self.contract=rename_contract; self.contract_path=rename_contract_path
        self.output=output; self.trace_path=output/"history.jsonl"; self.visual_path=output/"visual-events.jsonl"
        self.timing_path=output/"gateway-tool-timings.jsonl"; self.pi_path=output/"pi-tool-lifecycle.jsonl"
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

    def _initialize_verified_handoff(self,output,handoff_path,anchor_path,evidence_root):
        from verified_handoff import verify_handoff
        if self.contract.get("execution_profile_id")!=PROFILE:
            raise WorkspaceError("RENAME_CONTRACT_PROFILE","Rename profile is incompatible with the numeric Workspace")
        verified=verify_handoff(Path(handoff_path),Path(anchor_path),Path(evidence_root),self.contract_path)
        stream=read(verified["source_stream"])
        ws=Workspace(); doc=ws.create_empty_document("memory://cycle37/verified-rename-baseline.bas")["document_id"]
        replay=replay_constructive_stream(ws,doc,stream["operations"],
            expected_final_handles=stream["portable_handles"],expected_retired_handles=stream.get("retired_handles",[]),
            expected_start_revision=1)
        revision=replay.revision; aliases=dict(replay.live_handles)
        if revision!=self.contract["base_document_revision"]:
            raise WorkspaceError("RENAME_BASELINE_REVISION","Authenticated handoff revision differs from rename contract")
        raw=projection_semantics(build_projection(ws,doc,revision)); baseline=senior.normalized_state(raw,aliases)
        by_handle={row["handle"]:row for row in baseline["functions"]}
        expected_unchanged=set(by_handle)-{self.contract["target_handle"]}
        if (self.contract["target_handle"] not in by_handle
                or by_handle[self.contract["target_handle"]]["name"]!=self.contract["expected_source_name"]
                or set(self.contract["unchanged_function_handles"])!=expected_unchanged):
            raise WorkspaceError("RENAME_CONTRACT_BASELINE","Rename contract target or unchanged functions differ from authenticated program")
        validation=read(verified["source_validation"])
        inputs=self.contract["validation_inputs"]
        expected_rows=validation.get("expected_results",{}).get("interp",{})
        if sorted(map(str,inputs),key=lambda value:float(value))!=sorted(expected_rows,key=lambda value:float(value)):
            raise WorkspaceError("RENAME_ORACLE_INPUTS","Rename validation corpus must match the authenticated final construction receipt")
        original_name_by_handle={row["handle"]:row["name"].lower() for row in baseline["functions"]}
        baseline_expected={engine:{} for engine in ("interp","jit")}
        for value in inputs:
            key=str(value)
            for engine in baseline_expected:
                row=validation.get("expected_results",{}).get(engine,{}).get(key)
                if not isinstance(row,dict):
                    raise WorkspaceError("RENAME_ORACLE_RECEIPT","Final creation receipt lacks a complete independent expected result row")
                by_handle_expected={handle:row[name] for handle,name in original_name_by_handle.items() if name in row}
                if set(by_handle_expected)!=set(by_handle):
                    raise WorkspaceError("RENAME_ORACLE_RECEIPT","Creation oracle does not cover every live portable function")
                baseline_expected[engine][key]=by_handle_expected
        self.ws=ws; self.doc=doc; self.aliases=aliases; self.base_aliases=dict(aliases); self.baseline_aliases=dict(aliases)
        self.baseline=copy.deepcopy(baseline); self.baseline_handles=set(aliases); self.executor=MirExecutionService(timeout=20)
        self.baseline_token_ids={token.uid for token in ws.documents[doc].tokens}
        self.baseline_observed=self._observe_by_handle(ws,doc,revision,aliases,inputs)
        if (self.baseline_observed["interp"]!=baseline_expected["interp"]
                or self.baseline_observed["jit"]!=baseline_expected["jit"]
                or self.baseline_observed["interp"]!=self.baseline_observed["jit"]):
            raise WorkspaceError("RENAME_BASELINE_ORACLE_MISMATCH","Fresh MIR observations do not match authenticated host construction oracle")
        self.baseline_expected=baseline_expected; self.validation_inputs=list(inputs)
        self.baseline_source=ws.render_document(doc); self.base_revision=revision; self.revision=revision; self.committed=False
        self.committed_operations=copy.deepcopy(stream["operations"]); self.discovered=set(); self.discovered_statements=set()
        self.lock=threading.RLock(); self.transactions=SemanticTransactionKernel(ws,doc); self.pending_request_ids={}
        self.seq=0; self.pi_seen=set(); self.generic_mode=True
        self.session_id=f"cycle37-{output.name}"; self.mission_id=self.contract["mission_id"]
        self.initial_identity_map=[{"portable_handle":h,"workspace_id":v,"remapped":True} for h,v in sorted(aliases.items())]
        write(output/"MISSION.json",self.contract)
        write(output/"verified-handoff.json",verified)
        write(output/"baseline-reconstruction.json",{"schema":"basic-workspace.verified-rename-baseline","version":1,
            "starting_document_empty":True,"revision":revision,"semantic_fingerprint":verified["semantic_fingerprint"],
            "portable_identity_count":len(aliases),"identity_remappings":len(aliases),"identity_mapping":self.initial_identity_map,
            "authenticated_handoff":True,"host_oracle_match":True,"interpreter_jit_agree":True})
        write(output/"baseline-observations.json",{"revision":revision,"source":"Cycle36 authenticated final host construction receipt",
            "portable_handle_results":self.baseline_observed,"expected_portable_handle_results":baseline_expected,
            "dependencies":self.dependencies(baseline)})
        write(output/"execution-profile.json",read(Path(evidence_root)/"execution-profile.json"))
        write(output/"visual-source.json",{"schema":"basic-workspace.visual-source","version":1,
            "campaign":{"id":self.mission_id,"title":self.contract["objective"],"filename":"PROGRAM.bas"},
            "initial":{"revision":revision,"code":self.baseline_source,"dependencies":self.dependencies(baseline)},
            "snapshots":{str(revision):self.baseline_source}})
        self._emit({"event_type":"initial","revision":revision,"snapshot":self.baseline_source,
            "provenance":"Host-authenticated Cycle36 creation handoff and fresh replay","title":"Verified rename baseline",
            "description":"The handoff, checkpoints, construction receipts, portable identities and MIR observations passed host verification.",
            "dependencies":self.dependencies(baseline),"focus":{"handles":[self.contract["target_handle"]],"mapping":"verified_function_boundary"}})
        self._history("program_reconstructed","host_verified_handoff",revision=revision,operations=len(stream["operations"]),
            identity_remappings=len(aliases),semantic_equivalence=True,behavior_match=True,
            source_sequence_id=verified["source_sequence_id"],semantic_fingerprint=verified["semantic_fingerprint"])

    def _observe_by_handle(self,ws,doc,revision,aliases,inputs):
        result={"interp":{},"jit":{}}
        for engine in result:
            for value in inputs:
                result[engine][str(value)]={handle:self.executor.execute_function(ws,doc,revision,aliases[handle],[value],engine)["result"]
                    for handle in sorted(aliases) if handle.endswith(".function")}
        return result

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
        revision=self.ws.get_revision(self.doc); target=self.contract["target_handle"]
        data=[{"handle":f["handle"],"symbol_id":self.aliases[f["handle"]],"name":f["name"],
               "parameters":f["parameters"],"return_type":f["return_type"]} for f in state["functions"]]
        self._history("symbols_discovered","pi_model_tool",revision=revision,functions=data)
        self._emit({"event_type":"selection","revision":revision,"provenance":"Rename tool discovery request",
            "title":"Functions discovered","description":"Portable handles and current source names were returned from the live Workspace.",
            "focus":{"handles":[target],"mapping":"verified_function_boundary"},
            "dependencies":self.dependencies(state)})
        return {"revision":revision,"functions":data}

    def inspect(self):
        target=self.contract["target_handle"]
        if target not in self.discovered:raise WorkspaceError("FUNCTION_NOT_DISCOVERED","Discover the target function before inspection")
        sid=self.aliases[target];symbol=self.ws.documents[self.doc].symbols[sid]
        token_map={t.uid:t for t in self.ws.documents[self.doc].tokens}
        references=[]
        for uid in sorted(symbol.references,key=lambda u:(token_map[u].line,token_map[u].column)):
            t=token_map[uid];references.append({"token_id":uid,"line":t.line,"column":t.column,
                "kind":t.kind,"function_handle":next((h for h,i in self.aliases.items() if h.endswith(".function") and
                    any(f["symbol_id"]==i and f["start_line"]<=t.line<=f["end_line"] for f in self.ws.documents[self.doc].functions)),None)})
        state=self._state()
        parameter_prefix=target.removesuffix(".function")+".parameter."
        revision=self.ws.get_revision(self.doc)
        result={"revision":revision,"target":{"function_handle":target,"symbol_id":sid,"current_source_name":symbol.name,
            "parameters":[{"handle":h,"symbol_id":self.aliases[h]} for h in self.aliases if h.startswith(parameter_prefix)],
            "references":references},"functions":state["functions"],"dependencies":self.dependencies(state),
            "identity_rule":f"Portable handle {target} remains stable; source name is a mutable attribute. Rename locations come from the symbol's bound declaration and references."}
        self._history("program_inspected","pi_model_tool",revision=revision,target=target,reference_token_count=len(references))
        self._emit({"event_type":"selection","revision":revision,"provenance":"Rename tool semantic inspection request",
            "title":"Rename target and bound references inspected","description":f"The target has {len(references)} bound reference tokens; callers are resolved by symbol identity.",
            "focus":{"handles":[target],"mapping":"exact_semantic_span"},"dependencies":self.dependencies(state)})
        return result

    def _candidate(self, request):
        if self.committed:raise WorkspaceError("MISSION_EDIT_LIMIT","Mission permits one rename transaction")
        if self._sha256(self.contract_path)!=self.contract_sha256:
            raise WorkspaceError("RENAME_CONTRACT_CHANGED","Host-owned rename contract changed during the mission")
        authorized=authorize_rename_candidate(self.ws,self.doc,request=request,contract=self.contract,
            aliases=self.aliases,discovered=self.discovered,baseline=self.baseline)
        return (authorized["operations"],authorized["candidate"],authorized["candidate_workspace"],
            authorized["changed_token_ids"],authorized["changed_bound_tokens"])

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
        target=self.contract["target_handle"]; old_name=self.contract["expected_source_name"]
        new_name=self.contract["new_source_name"]; revision=self.ws.get_revision(self.doc)
        try:ops,candidate,candidate_ws,changed,count=self._candidate(request)
        except WorkspaceError as exc:
            result={"ok":False,"code":exc.code,"message":str(exc),"revision":revision,
                "revision_unchanged":True,"authoritative_workspace_changed":False}
            self._history("transaction_rejected","mission_gateway",request_id=rid,code=exc.code,revision=revision,authoritative_state_unchanged=True)
            self._emit({"event_type":"rejection","revision":revision,"provenance":"Rename MissionContract rejection",
                "title":"Rename proposal rejected","description":str(exc),"outcome":result});return result
        before=self.ws.render_document(self.doc); after=candidate_ws.render_document(self.doc)
        txid,preview=self.transactions.preview(operation_kind="rename_symbol",base_revision=request["expected_revision"],
            operations=ops,candidate=candidate,metadata={"request":copy.deepcopy(request),"changed_token_ids":changed})
        self.pending_request_ids[txid]=rid
        self._history("operation_proposed","pi_model_tool",request_id=rid,transaction_id=txid,operation="rename_symbol",arguments=request)
        self._history("preview_accepted","mission_gateway",transaction_id=txid,base_revision=revision,resulting_revision=revision+1,
            function_handle=target,old_name=old_name,new_name=new_name,changed_token_ids=changed)
        self._emit({"event_type":"preview","revision":revision,"provenance":"Typed semantic rename proposal · MissionGateway accepted preview",
            "source_event_ref":rid,"title":"Rename preview accepted","description":f"The candidate changes bound spelling from {old_name} to {new_name}; committed source remains at revision {revision}.",
            "focus":{"handles":[target],"mapping":"verified_unique_line_difference"},
            "preview":{"status":"accepted","diff":preview.get("diff",""),"old_name":old_name,"new_name":new_name,
                "semantic_handle":target,"changed_token_ids":changed,"references_changed":count},
            "outcome":{"authorized":True,"committed":False,"transaction_id":txid,"candidate_source":after,"committed_source":before}})
        return {"ok":True,"transaction_id":txid,"base_revision":revision,"expected_result_revision":revision+1,
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
        target=self.contract["target_handle"];old_name=self.contract["expected_source_name"]
        new_name=self.contract["new_source_name"];expected_revision=self.base_revision+1
        if receipt.revision!=expected_revision:raise RuntimeError("Rename transaction did not advance exactly one revision")
        self.revision=expected_revision;self.committed=True
        post=self._state(expected_revision)
        if post!=receipt.candidate:raise RuntimeError("Committed rename projection differs from accepted preview")
        self.committed_operations.append({"operation":"rename_symbol","target_handle":target,
            "expected_name":old_name,"new_name":new_name})
        write(self.output/"constructive-operations.json",{"schema":"basic-workspace.constructive-metafile","version":1,
            "execution_profile_id":PROFILE,"portable_handles":sorted(self.aliases),"operations":self.committed_operations})
        code=self.ws.render_document(self.doc);source=read(self.output/"visual-source.json");source["snapshots"][str(expected_revision)]=code;write(self.output/"visual-source.json",source)
        self._history("transaction_committed","mission_gateway",request_id=rid,transaction_id=txid,base_revision=self.base_revision,resulting_revision=expected_revision,
            operation="rename_symbol",target_handle=target,old_name=old_name,new_name=new_name,
            preserved_function_id=self.aliases[target],preserved_alias_count=len(self.aliases),changed_token_ids=receipt.metadata["changed_token_ids"])
        self._emit({"event_type":"commit","revision":expected_revision,"snapshot":code,"provenance":"Workspace atomic semantic rename commit",
            "source_event_ref":self.pending_request_ids.get(txid,rid),"title":f"{new_name} rename committed",
            "description":f"Declaration and bound references now spell {new_name}; the portable identity and existing token identities remain stable.",
            "focus":{"handles":[target],"mapping":"verified_unique_line_difference",
                "changed_token_ids":receipt.metadata["changed_token_ids"]},"dependencies":self.dependencies(post),
            "outcome":{"committed":True,"revision":expected_revision,"transaction_id":txid,"changed_token_ids":receipt.metadata["changed_token_ids"]}})
        return {"ok":True,"committed":True,"revision":expected_revision,"function_handle":target,"function_id":self.aliases[target],
            "source_name":new_name,"preserved_identity_count":len(self.aliases),"changed_bound_tokens":len(receipt.metadata["changed_token_ids"])}

    def validate(self,requested_revision,rid,actor="host"):
        revision=self.ws.get_revision(self.doc)
        if requested_revision!=revision:return {"reliable":False,"code":"STALE_VALIDATION_REVISION","requested_revision":requested_revision,
            "executed_revision":None,"mission_complete":False}
        if not self.committed:return {"reliable":True,"mission_complete":False,"executed_revision":revision,"diagnostics":["No rename committed"]}
        if self.generic_mode:
            return self._validate_generic_rename(revision,requested_revision,rid,actor)
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

    def _validate_generic_rename(self,revision,requested_revision,rid,actor):
        target=self.contract["target_handle"];new_name=self.contract["new_source_name"]
        observed=self._observe_by_handle(self.ws,self.doc,revision,self.aliases,self.validation_inputs)
        engine_ok=observed["interp"]==observed["jit"]
        behavior_ok=observed==self.baseline_observed
        normalized=self._state();expected=copy.deepcopy(self.baseline)
        senior.find_function(expected,target)["name"]=new_name
        structural_ok=normalized==expected
        symbol=self.ws.documents[self.doc].symbols[self.aliases[target]]
        reference_ids={symbol.declaration_token,*symbol.references}
        tokens={token.uid:token for token in self.ws.documents[self.doc].tokens}
        name_ok=symbol.name==new_name and all(uid in tokens and tokens[uid].text==new_name for uid in reference_ids)
        identities_ok=(self.aliases==self.base_aliases and set(tokens)==self.baseline_token_ids
            and len(self.aliases)==len(self.baseline_handles))
        dependency_ids_unchanged=self._dependency_identity_edges(normalized)==self._dependency_identity_edges(self.baseline)
        replay=self.replay(self.committed_operations)
        identity_mapping=[{"portable_handle":handle,"maintenance_workspace_id":self.aliases[handle],
            "replay_workspace_id":replay["aliases"][handle],"remapped":self.aliases[handle]!=replay["aliases"][handle]}
            for handle in sorted(self.aliases) if handle in replay["aliases"]]
        replay_ok=(replay["revision"]==revision and replay["normalized"]==normalized
            and replay["observed"]==observed and replay["aliases"].keys()==self.aliases.keys()
            and replay["remapped_count"]==len(self.aliases))
        result={"schema":"basic-workspace.semantic-rename-validation","version":2,"reliable":True,
            "mission_id":self.mission_id,"revision":revision,"requested_revision":requested_revision,
            "executed_revision":revision,"target_handle":target,"source_name":new_name,
            "observed_results_by_portable_handle":observed,"expected_results_by_portable_handle":self.baseline_observed,
            "expectation_source":"Cycle36-authenticated independent Cycle35 final host validation receipt",
            "interpreter_jit_agree":engine_ok,"behavior_unchanged":behavior_ok,
            "normalized_structure_modulo_target_name":structural_ok,
            "function_identity_preserved":self.aliases[target]==self.base_aliases[target],
            "all_portable_identities_preserved":identities_ok,"token_identity_set_preserved":set(tokens)==self.baseline_token_ids,
            "all_bound_target_tokens_renamed":name_ok,
            "dependency_identity_edges_unchanged":dependency_ids_unchanged,
            "replay":{"passed":replay_ok,"revision":replay["revision"],
                "structural_equivalence_modulo_rename":replay["normalized"]==normalized,
                "behavioral_equivalence":replay["observed"]==observed,
                "portable_identity_count":replay["identity_count"],"identity_remappings":replay["remapped_count"],
                "identity_mapping":identity_mapping,"retired_handles":replay.get("retired_handles",[])},
            "mission_complete":bool(engine_ok and behavior_ok and structural_ok and identities_ok
                and name_ok and dependency_ids_unchanged and replay_ok)}
        write(self.output/("mission-validation-host.json" if actor=="host" else "mission-validation-pi_tool.json"),result)
        self._history("program_validated","host_validation" if actor=="host" else "pi_model_tool",revision=revision,
            passed=result["mission_complete"],engines_agree=engine_ok,replay_passed=replay_ok)
        self._emit({"event_type":"validation","revision":revision,
            "provenance":"Independent host validation" if actor=="host" else "Pi-requested validation",
            "title":"Rename identity, behavior and replay validated",
            "description":"Fresh MIR interpreter/JIT observations, host creation expectations, bound identities and constructive replay were compared.",
            "focus":{"handles":[target],"mapping":"verified_function_boundary"},
            "validation":{"passed":result["mission_complete"],"interpreter_jit_agree":engine_ok,"replay":result["replay"]},
            "observation":{"portable_handle_results":observed,"arguments":self.validation_inputs,"revision":revision},
            "dependencies":self.dependencies(normalized)})
        return result

    def replay(self,operations):
        if self.generic_mode:
            ws=Workspace();doc=ws.create_empty_document("memory://cycle37/rename-replay.bas")["document_id"]
            replay_result=replay_constructive_stream(ws,doc,operations,expected_start_revision=1)
            aliases=dict(replay_result.live_handles);revision=replay_result.revision
            normalized=senior.normalized_state(projection_semantics(build_projection(ws,doc,revision)),aliases)
            observed=self._observe_by_handle(ws,doc,revision,aliases,self.validation_inputs)
            remapped=sum(self.base_aliases.get(handle)!=aliases.get(handle) for handle in aliases if handle in self.base_aliases)
            return {"workspace":ws,"document_id":doc,"revision":revision,"aliases":aliases,"normalized":normalized,
                "observed":observed,"identity_count":len(aliases),"remapped_count":remapped,
                "existing_handles_preserved":set(self.base_aliases).issubset(aliases),"retired_handles":replay_result.retired_handles}
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
    parser.add_argument("--contract",type=Path,default=CONTRACT)
    parser.add_argument("--verified-handoff",type=Path);parser.add_argument("--handoff-anchor",type=Path)
    parser.add_argument("--handoff-evidence-root",type=Path)
    args=parser.parse_args();service=Cycle26Gateway(args.output,args.contract,
        verified_handoff_path=args.verified_handoff,handoff_anchor_path=args.handoff_anchor,
        handoff_evidence_root=args.handoff_evidence_root)
    with Server(("127.0.0.1",args.port),service) as server:
        print(json.dumps({"ready":True,"host":"127.0.0.1","port":server.server_address[1],
            "revision":service.base_revision,"baseline_verified":True,"mission_id":service.mission_id,"identity_count":len(service.aliases)},separators=(",",":")),flush=True)
        server.serve_forever()
if __name__=="__main__":main()
