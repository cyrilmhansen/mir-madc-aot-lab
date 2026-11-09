#!/usr/bin/env python3
"""Cycle 29 two-phase, identity-audited conditional extraction campaign."""
from __future__ import annotations
import argparse, copy, hashlib, json, sys, tempfile, time, uuid
from pathlib import Path
from typing import Any

HERE=Path(__file__).resolve().parent; ROOT=HERE.parent
sys.path.insert(0,str(HERE)); sys.path.insert(0,str(ROOT))
from basic_workspace.model import Workspace, WorkspaceError
from basic_workspace.projection import Assignment, ForLoop, IfBlock, build_projection, projection_semantics
from basic_workspace.mir_execution import MirExecutionService
from cycle19_gateway import Cycle19Gateway, senior, PROFILE_ID
from cycle20_gateway import Cycle20Gateway
from cycle28_gateway import Cycle28Gateway
from transaction_kernel import SemanticTransactionKernel
from gateway import Server

BASE=HERE/"results/cycle28-conditional-refactor/real-agent-01"
C28_CONTRACT=HERE/"results/cycle28-conditional-refactor/contracts/mission.json"
INPUTS=[-100,-1,0,1,19,20,39,40,44,45,49,50,51,60,100,200]
HELPER="base_score_class.function"; SCORE="score_class.function"; NORMALIZER="clamp_score.function"
PATH=[{"block":"body","index":0}]

def _canonical(value:Any)->bytes:
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()

def _fingerprint(value:Any)->str:return hashlib.sha256(_canonical(value)).hexdigest()

def _edges(snapshot):return {(row["caller"],row["callee"]) for row in senior.candidate_call_edges(snapshot)}

class Cycle29Gateway(Cycle19Gateway):
    def __init__(self, output:Path):
        output=Path(output).resolve(); output.mkdir(parents=True,exist_ok=True)
        # Reuse the existing campaign object only for its established typed
        # constructor and common journal helpers. Its throwaway empty bootstrap
        # lives in a cleaned RAM-safe temporary directory.
        with tempfile.TemporaryDirectory(prefix="atlas-cycle29-init-",dir="/var/tmp") as td:
            Cycle19Gateway.__init__(self,Path(td)/"bootstrap")
        self.output=output; self.trace=age_trace(); self.lock=__import__("threading").RLock()
        self.executor=MirExecutionService(timeout=20)
        self._reconstruct_cycle28()
        self.transactions=SemanticTransactionKernel(self.ws,self.doc)
        self.base_aliases=dict(self.aliases); self.base_snapshot=self._normalized()
        self.committed_operations=copy.deepcopy(self.constructive_ops)
        self.completed_missions=[]; self.phase=1; self.committed=False; self.last_validation=None
        self.discovered=set(); self.discovered_statement_handles=set(); self.dispatched={}; self.block_pending={}; self.retired=[]
        self.pi_seen=set(); self.presentation_seq=0
        self.visual_events=output/"visual-events.jsonl"; self.visual_events.write_text("",encoding="utf-8")
        self.pi_events=output/"pi-tool-lifecycle.jsonl"; self.gateway_timings=output/"gateway-tool-timings.jsonl"
        self.session_id="cycle29-mission-a-create-helper"; self.mission_title="Mission A · create BASE_SCORE_CLASS"
        self.mission_specs={}
        self.current_contract={"mission_id":"cycle29.create-base-score-class.v1","name":"BASE_SCORE_CLASS",
            "handle":HELPER,"parameter":"X","callee":NORMALIZER,"required_callees":[NORMALIZER],
            "required_dependency_edges":[{"caller":HELPER,"callee":NORMALIZER}],
            "objective":"Extract the below-20 score classification into BASE_SCORE_CLASS(X): return 0 when NORMALIZE_SCORE(X)<20, otherwise 1.",
            "validation":{"inputs":INPUTS}}
        self.mission_specs[1]=copy.deepcopy(self.current_contract)
        self.mission_title="Mission A · create BASE_SCORE_CLASS"
        self.initial={"revision":11,"code":self.ws.render_document(self.doc),"dependencies":self._dependencies(self.base_snapshot)}
        self._write_contracts()
        self.write_json("execution-profile.json",json.loads((ROOT/"results/semantic-replay/execution-profile.json").read_text()))
        bundle={"schema":"basic-workspace.visual-source","version":1,
            "campaign":{"id":"cycle29-function-extraction","title":"Cycle 29 · semantic extraction","filename":"SCORES.bas"},
            "initial":self.initial,"snapshots":{"11":self.initial["code"]}}
        self.write_json("visual-source.json",bundle)
        self.emit_visual({"event_id":"cycle29-baseline-r11","event_type":"initial","revision":11,
            "session_id":"cycle29-host-reconstruction","mission_id":"Cycle 29 baseline",
            "provenance":"Deterministic replay of authentic Cycle 28 committed operations; not model activity",
            "title":"Verified revision-11 baseline","description":"Ten authentic Cycle 28 committed operations reconstructed into a fresh Workspace.",
            "snapshot":self.initial["code"],"dependencies":self.initial["dependencies"],
            "focus":{"handles":sorted(self.aliases),"mapping":"verified_function_boundary"}})
        self.flush_trace()
        self.write_json("baseline-reconstruction.json",self.baseline_reconstruction)
        self.write_json("mission-a-baseline.json",{"revision":11,"normalized_program":self.base_snapshot,
            "portable_handles":sorted(self.aliases),"identity_count":len(self.aliases),"captured_after_authentic_replay":True})
        self._set_mission_a_contract()

    def _write_contracts(self):
        (self.output/"contracts").mkdir(parents=True,exist_ok=True)
        mission_a={"schema":"basic-workspace.numeric-function-creation-contract","version":1,
            "mission_id":"cycle29.create-base-score-class.v1","objective":self.current_contract["objective"],
            "base_document_revision":11,"execution_profile_id":PROFILE_ID,
            "function":{"name":"BASE_SCORE_CLASS","handle":HELPER,"parameter":"X","return_type":"numeric"},
            "required_callees":[NORMALIZER],"required_dependency_edges":[{"caller_handle":HELPER,"callee_handle":NORMALIZER}],
            "unchanged_function_handles":["clamp_score.function","is_passing.function","score_class.function","is_at_cap.function"],
            "validation":{"inputs":INPUTS,"functions":[{"function_handle":HELPER,"result_key":"base_score_class"}]}}
        mission_b={"schema":"basic-workspace.typed-block-extraction-contract","version":1,
            "mission_id":"cycle29.replace-score-classification-block.v1",
            "objective":"Replace SCORE_CLASS's first IF with a result assignment calling BASE_SCORE_CLASS(X).",
            "base_document_revision":12,"execution_profile_id":PROFILE_ID,
            "target":{"function_handle":SCORE,"control_path":PATH,"allowed_anchor_handles":["score_class.statement.0","score_class.statement.1"],
                "expected_removed_statement_handles":["score_class.statement.0","score_class.statement.1"]},
            "replacement":{"kind":"assign","target":{"kind":"result"},"expression":{"kind":"call","function_handle":HELPER,"arguments":[{"kind":"local_ref","name":"X"}]}},
            "preserve_function_handles":[NORMALIZER,"is_passing.function","is_at_cap.function",HELPER,SCORE],
            "preserve_dependency_edges":"all baseline edges except SCORE_CLASS->NORMALIZE_SCORE, which is replaced by SCORE_CLASS->BASE_SCORE_CLASS; BASE_SCORE_CLASS->NORMALIZE_SCORE is required",
            "validation":{"inputs":INPUTS}}
        self.write_json("contracts/mission-a-create-helper.json",mission_a)
        self.write_json("contracts/mission-b-replace-block.json",mission_b)

    def _set_mission_a_contract(self):
        self.current_contract={"mission_id":"cycle29.create-base-score-class.v1","name":"BASE_SCORE_CLASS",
            "handle":HELPER,"parameter":"X","callee":NORMALIZER,"required_callees":[NORMALIZER],
            "required_dependency_edges":[{"caller":HELPER,"callee":NORMALIZER}],
            "objective":"Extract the below-20 score classification into BASE_SCORE_CLASS(X): return 0 when NORMALIZE_SCORE(X)<20, otherwise 1.",
            "validation":{"inputs":INPUTS}}
        self.mission_title="Mission A · create BASE_SCORE_CLASS"
        self.phase=1; self.session_id="cycle29-mission-a-create-helper"; self.committed=False

    def _reconstruct_cycle28(self):
        stream_path=BASE/"constructive-operations.json"; history_path=BASE/"history.jsonl"
        validation_path=BASE/"host-validation.json"
        stream=json.loads(stream_path.read_text()); operations=stream.get("operations",[])
        if stream.get("schema")!="basic-workspace.constructive-metafile" or len(operations)!=10:
            raise WorkspaceError("BASELINE_STREAM_INVALID","Cycle 28 requires its authentic ten-operation stream")
        if stream.get("execution_profile_id")!=PROFILE_ID or not validation_path.is_file():
            raise WorkspaceError("BASELINE_PROFILE_INVALID","Cycle 28 execution profile or host validation is missing")
        saved_validation=json.loads(validation_path.read_text())
        if saved_validation.get("mission_complete") is not True or saved_validation.get("revision")!=11:
            raise WorkspaceError("BASELINE_VALIDATION_FAILED","Authentic Cycle 28 revision 11 was not host validated")
        seed_dir=self.output/"baseline-host-reconstruction"
        seed=Cycle28Gateway(seed_dir,C28_CONTRACT)
        # Replay resolves historical call handles from the verified stream; it
        # does not pretend the current agent performed these discoveries.
        seed.discovered={h for h in seed.aliases if h.endswith(".function")}
        final=operations[-1]
        if final.get("operation")!="edit_typed_if_condition" or final.get("function_handle")!=SCORE:
            raise WorkspaceError("BASELINE_OPERATION_INVALID","Cycle 28 final committed operation is not the SCORE_CLASS condition refactor")
        fid=seed.aliases.get(SCORE); anchor=seed.aliases.get(final.get("anchor_statement_handle"))
        if fid is None or anchor is None:raise WorkspaceError("BASELINE_HANDLE_MISSING","Cycle 28 portable target handles did not resolve")
        op={"operation":"edit_typed_if_condition","function_id":fid,"control_path":final["control_path"],
            "anchor_statement_id":anchor,"expected_condition":seed._resolve_expr(final["expected_condition"],fid),
            "condition":seed._resolve_expr(final["condition"],fid)}
        applied=seed.ws.apply_transaction(seed.doc,seed.ws.get_revision(seed.doc),[op])
        if applied["revision"]!=11:raise WorkspaceError("BASELINE_REVISION_MISMATCH","Cycle 28 replay must yield revision 11")
        normalized=senior.normalized_state(projection_semantics(build_projection(seed.ws,seed.doc,11)),seed.aliases)
        prior=[json.loads(line) for line in history_path.read_text().splitlines() if line.strip()]
        commits=[row for row in prior if row.get("event")=="transaction_committed" and row.get("resulting_revision")==11]
        if len(commits)!=1 or commits[0].get("semantic_snapshot")!=normalized:
            raise WorkspaceError("BASELINE_SEMANTIC_MISMATCH","Fresh revision-11 projection differs from the authentic Cycle 28 commit snapshot")
        observed=self._observe(seed.ws,seed.doc,11,seed.aliases)
        if observed!=saved_validation.get("observed_results") or observed["interp"]!=observed["jit"]:
            raise WorkspaceError("BASELINE_BEHAVIOR_MISMATCH","Reconstructed interpreter/JIT results differ from authentic Cycle 28 validation")
        self.ws=seed.ws; self.doc=seed.doc; self.aliases=dict(seed.aliases)
        self.constructive_ops=copy.deepcopy(operations)
        self.baseline_reconstruction={"source":"Cycle 28 genuine constructive stream plus authentic committed operation",
            "operations":10,"revision":11,"portable_identities":len(self.aliases),
            "normalized_equivalence":True,"binding_equivalence":True,"behavioral_equivalence":True,
            "interpreter_jit_agree":True,"observations":observed,"passed":len(self.aliases)==23}
        if not self.baseline_reconstruction["passed"]:raise WorkspaceError("BASELINE_IDENTITY_MISMATCH","Cycle 28 baseline must have 23 portable handles")

    def _observe(self,ws,doc,revision,aliases):
        result={"interp":{},"jit":{}}
        for engine in result:
            for x in INPUTS:
                row={}
                for h,key in ((NORMALIZER,"normalize_score"),("is_passing.function","is_passing"),
                              (SCORE,"score_class"),("is_at_cap.function","is_at_cap")):
                    row[key]=self.executor.execute_function(ws,doc,revision,aliases[h],[x],engine)["result"]
                if HELPER in aliases:
                    row["base_score_class"]=self.executor.execute_function(ws,doc,revision,aliases[HELPER],[x],engine)["result"]
                result[engine][str(x)]=row
        return result

    @staticmethod
    def _expr_signature(expr):
        return (expr.kind,expr.value,tuple(Cycle29Gateway._expr_signature(c) for c in expr.children))

    @classmethod
    def _statement_signature(cls,statement,include_id=True):
        if isinstance(statement,Assignment):
            return ("assign",statement.target_symbol_id,statement.target_is_result,statement.target_is_array,
                cls._expr_signature(statement.target_index) if statement.target_index else None,
                cls._expr_signature(statement.expression),statement.statement_id if include_id else None)
        if isinstance(statement,IfBlock):
            return ("if",cls._expr_signature(statement.condition),
                tuple(cls._statement_signature(x,include_id) for x in statement.then_body),
                tuple(cls._statement_signature(x,include_id) for x in statement.else_body))
        if isinstance(statement,ForLoop):
            return ("for",statement.variable_id,statement.start,statement.end,statement.step,
                tuple(cls._statement_signature(x,include_id) for x in statement.body))
        raise WorkspaceError("UNSUPPORTED_TYPED_BLOCK","Unknown projected statement")

    def _handle_for_id(self,symbol_id):
        return next((handle for handle,value in self.aliases.items() if value==symbol_id),None)

    def _portable_expr(self,expr):
        if expr.kind=="number":return {"kind":"number","value":expr.value}
        if expr.kind in ("variable","result"):
            symbol_id=str(expr.value); handle=self._handle_for_id(symbol_id)
            if handle and handle.endswith(".parameter.id"):
                symbol=self.ws.documents[self.doc].symbols.get(symbol_id)
                return {"kind":"local_ref","name":symbol.name}
            raise WorkspaceError("UNSUPPORTED_BLOCK_REFERENCE","Selected expression contains an unportable non-parameter symbol")
        if expr.kind=="call":
            handle=self._handle_for_id(str(expr.value))
            if not handle or not handle.endswith(".function"):
                raise WorkspaceError("UNSUPPORTED_BLOCK_REFERENCE","Call has no portable function handle")
            return {"kind":"call","function_handle":handle,"arguments":[self._portable_expr(x) for x in expr.children]}
        if expr.kind in ("compare","binary"):
            return {"kind":"binary","operator":str(expr.value),"left":self._portable_expr(expr.children[0]),
                    "right":self._portable_expr(expr.children[1])}
        raise WorkspaceError("UNSUPPORTED_BLOCK_REFERENCE",f"Cannot serialize {expr.kind} as portable typed expression")

    def _portable_block(self,statement):
        if not isinstance(statement,IfBlock):raise WorkspaceError("INVALID_BLOCK_TARGET","Expected IF block")
        def children(items):
            out=[]
            for child in items:
                if isinstance(child,Assignment):
                    if not child.target_is_result:raise WorkspaceError("UNSUPPORTED_BLOCK_TARGET","Extraction currently accepts result assignments only")
                    out.append({"kind":"assign","target":{"kind":"result"},"expression":self._portable_expr(child.expression),
                        "statement_handle":self._handle_for_id(child.statement_id)})
                elif isinstance(child,IfBlock):out.append(self._portable_block(child))
                else:raise WorkspaceError("UNSUPPORTED_BLOCK_TARGET","FOR blocks are outside this bounded extraction grammar")
            return out
        return {"kind":"if","condition":self._portable_expr(statement.condition),
            "then":children(statement.then_body),"else":children(statement.else_body)}

    def _target_projection(self,aliases=None,ws=None,doc=None,revision=None):
        aliases=aliases or self.aliases; ws=ws or self.ws; doc=doc or self.doc
        revision=revision or ws.get_revision(doc)
        projection=build_projection(ws,doc,revision)
        fn=next((f for f in projection.functions if f.symbol_id==aliases.get(SCORE)),None)
        if fn is None or not fn.statements or not isinstance(fn.statements[0],IfBlock):
            raise WorkspaceError("MISSION_TARGET_DENIED","SCORE_CLASS first statement is no longer the target IF")
        target=fn.statements[0]
        portable=self._portable_block(target) if ws is self.ws else self._portable_block_for(ws,doc,target,aliases)
        removed=[]
        def collect(items):
            for item in items:
                if isinstance(item,Assignment):removed.append(item.statement_id)
                elif isinstance(item,IfBlock):collect(item.then_body);collect(item.else_body)
                elif isinstance(item,ForLoop):collect(item.body)
        collect(target.then_body);collect(target.else_body)
        portable_removed=[next((h for h,sid in aliases.items() if sid==sid2),None) for sid2 in removed]
        return fn,target,portable,_fingerprint(portable),removed,portable_removed

    def _portable_block_for(self,ws,doc,statement,aliases):
        # Replay uses another Workspace but exactly the same semantic handles.
        old_ws,old_doc,old_aliases=self.ws,self.doc,self.aliases
        self.ws,self.doc,self.aliases=ws,doc,aliases
        try:return self._portable_block(statement)
        finally:self.ws,self.doc,self.aliases=old_ws,old_doc,old_aliases

    def _resolve_expr(self,value,function_id):
        if not isinstance(value,dict):raise WorkspaceError("INVALID_EXPRESSION","Typed expression must be an object")
        kind=value.get("kind")
        if kind=="number" and set(value)=={"kind","value"}:return {"kind":"number","value":value["value"]}
        if kind=="local_ref" and set(value)=={"kind","name"}:
            fn=next((f for f in self.ws.documents[self.doc].functions if f["symbol_id"]==function_id),None)
            sid=next((sid for sid in fn["parameters"] if self.ws.documents[self.doc].symbols[sid].name.casefold()==str(value["name"]).casefold()),None) if fn else None
            if sid is None:raise WorkspaceError("UNKNOWN_LOCAL_REFERENCE","Typed local reference is not a parameter of the target function")
            return {"kind":"symbol_ref","symbol_id":sid}
        if kind=="call" and set(value)=={"kind","function_handle","arguments"}:
            callee=self.aliases.get(value["function_handle"])
            if callee is None or value["function_handle"] not in self.discovered:
                raise WorkspaceError("FUNCTION_NOT_DISCOVERED","Discover the called function before proposing the edit")
            row=next((f for f in self.ws.documents[self.doc].functions if f["symbol_id"]==callee),None)
            if row is None or len(row["parameters"])!=len(value["arguments"]):
                raise WorkspaceError("FUNCTION_SIGNATURE_MISMATCH","Typed function call arity is incompatible")
            return {"kind":"call","function_id":callee,"arguments":[self._resolve_expr(x,function_id) for x in value["arguments"]]}
        if kind=="binary" and set(value)=={"kind","operator","left","right"}:
            return {"kind":"binary","operator":value["operator"],"left":self._resolve_expr(value["left"],function_id),
                    "right":self._resolve_expr(value["right"],function_id)}
        raise WorkspaceError("INVALID_EXPRESSION","Unsupported typed replacement expression")

    def _inspect(self,rid):
        revision=self.ws.get_revision(self.doc); normalized=self._normalized(revision)
        response={"revision":revision,"structure":normalized,"dependencies":self._dependencies(normalized),
            "discovered_handles":sorted(self.discovered)}
        if self.phase==2:
            fn,target,portable,fingerprint,removed,handles=self._target_projection()
            if any(handle is None for handle in handles):raise WorkspaceError("IDENTITY_HANDLE_MISSING","Every retiring assignment needs a portable handle")
            response["extraction_target"]={"function_handle":SCORE,"function_name":"SCORE_CLASS",
                "control_path":PATH,"typed_block":portable,"expected_block_fingerprint":fingerprint,
                "anchor_statement_handles":handles,"expected_removed_statement_handles":handles,
                "statement_identity_rule":"removed assignments retire; replacement assignment receives a fresh identity"}
            self.discovered_statement_handles.update(handles)
        self.trace.emit("program_inspected",phase=f"mission-{self.phase}",actor="pi_model_tool",
            mission_id=self._mission_id(),revision=revision,discovered_handles=sorted(self.discovered))
        self.flush_trace();return response

    def _set_checkpoint_for_b(self):
        validation=self.last_validation
        normalized=self._normalized(); fingerprint=_fingerprint({"revision":self.ws.get_revision(self.doc),"profile":PROFILE_ID,"semantics":normalized})
        checkpoint={"schema":"basic-workspace.semantic-recovery-checkpoint","version":1,
            "revision":self.ws.get_revision(self.doc),"execution_profile_id":PROFILE_ID,
            "semantic_fingerprint":fingerprint,
            "functions":[{"handle":f["handle"],"name":f["name"],"parameters":f["parameters"],"return_type":f["return_type"]} for f in normalized["functions"]],
            "dependencies":self._dependencies(normalized),"portable_handles":sorted(self.aliases),
            "completed_missions":[{"mission_id":self.current_contract["mission_id"],"revision":12,"validated":True,
                "result":validation.get("mission_complete")}],
            "active_mission":"Replace SCORE_CLASS's first classification IF with a call to BASE_SCORE_CLASS(X).",
            "verified_behavior":"All four existing functions and BASE_SCORE_CLASS passed the independent 16-input host oracle on MIR interpreter and JIT.",
            "agent_authored_notes":[],"opaque_workspace_ids_included":False}
        self.write_json("checkpoint-mission-b.json",checkpoint)
        return checkpoint

    def prepare_mission_b(self,p):
        if self.phase!=1 or not self.committed or not self.last_validation or not self.last_validation.get("mission_complete"):
            return {"ok":False,"code":"MISSION_A_NOT_VALIDATED","revision":self.ws.get_revision(self.doc),"workspace_changed":False}
        current=self.ws.get_revision(self.doc); checkpoint=p.get("checkpoint")
        if not isinstance(checkpoint,dict) or checkpoint.get("revision")!=current or checkpoint.get("execution_profile_id")!=PROFILE_ID:
            return {"ok":False,"code":"CHECKPOINT_MISMATCH","revision":current,"workspace_changed":False}
        normalized=self._normalized(current); expected=_fingerprint({"revision":current,"profile":PROFILE_ID,"semantics":normalized})
        if checkpoint.get("semantic_fingerprint")!=expected or checkpoint.get("portable_handles")!=sorted(self.aliases):
            return {"ok":False,"code":"CHECKPOINT_MISMATCH","revision":current,"workspace_changed":False}
        self.phase=2; self.current_contract={"mission_id":"cycle29.replace-score-classification-block.v1",
            "objective":"Replace the first SCORE_CLASS classification IF with a call to discovered BASE_SCORE_CLASS(X).",
            "target_handle":SCORE,"helper_handle":HELPER,"control_path":PATH,
            "expected_removed_statement_handles":["score_class.statement.0","score_class.statement.1"],
            "allowed_anchor_handles":["score_class.statement.0","score_class.statement.1"],
            "replacement_statement_handle":"score_class.statement.extracted-base-call"}
        self.mission_specs[2]=copy.deepcopy(self.current_contract);self.mission_title="Mission B · replace SCORE_CLASS block"
        self.session_id="cycle29-mission-b-replace-block";self.base_snapshot=normalized;self.base_aliases=dict(self.aliases)
        self.discovered=set();self.discovered_statement_handles=set();self.transactions.clear();self.committed=False;self.last_validation=None;self.block_pending={}
        self.write_json("mission-b-baseline.json",{"revision":current,"semantic_fingerprint":expected,
            "normalized_program":normalized,"captured_after_mission_a_validation":True})
        self.trace.emit("context_reset",phase="host",actor="host_checkpoint",mission_id=self.current_contract["mission_id"],
            revision=current,verified_checkpoint=True,fresh_pi_conversation=True)
        self.emit_visual({"event_id":"cycle29-mission-boundary","event_type":"context_reset","revision":current,
            "session_id":self.session_id,"mission_id":self.mission_title,
            "provenance":"Host verified Mission A checkpoint before fresh Pi process",
            "title":"Mission boundary · new Pi conversation","description":"The committed revision-12 helper remains authoritative; the next agent session receives only the verified checkpoint and current tools.",
            "focus":{"handles":[HELPER,SCORE],"mapping":"verified_function_boundary"},"dependencies":self._dependencies(normalized)})
        self.flush_trace();return {"ok":True,"revision":current,"phase":2,"checkpoint_verified":True,
            "session_id":self.session_id,"fingerprint":expected}

    def create_mission_b_checkpoint(self):
        if self.phase!=1 or not self.last_validation or not self.last_validation.get("mission_complete"):
            return {"ok":False,"code":"MISSION_A_NOT_VALIDATED","workspace_changed":False}
        return {"ok":True,"checkpoint":self._set_checkpoint_for_b()}

    def _mission_b_authorized(self,p):
        allowed={"expected_revision","function_handle","control_path","anchor_statement_handle",
            "expected_block_fingerprint","expected_removed_statement_handles","replacement_statements"}
        if set(p)!=allowed:raise WorkspaceError("UNKNOWN_SEMANTIC_FIELD","Block replacement request has missing or unsupported fields")
        rev=self.ws.get_revision(self.doc)
        if p["expected_revision"]!=rev:raise WorkspaceError("STALE_REVISION","Block replacement revision is stale")
        if self.committed:raise WorkspaceError("MISSION_EDIT_LIMIT","Mission B permits one atomic block replacement")
        if p["function_handle"]!=SCORE or SCORE not in self.discovered:raise WorkspaceError("MISSION_TARGET_DENIED","Only discovered SCORE_CLASS may be edited")
        if p["control_path"]!=PATH:raise WorkspaceError("MISSION_TARGET_DENIED","Only the first SCORE_CLASS IF is authorized")
        if HELPER not in self.discovered or p["anchor_statement_handle"] not in self.discovered_statement_handles:
            raise WorkspaceError("FUNCTION_NOT_DISCOVERED","Discover the helper and statement anchor first")
        if not set(p.get("expected_removed_statement_handles",[])).issubset(self.discovered_statement_handles):
            raise WorkspaceError("STATEMENT_NOT_DISCOVERED","Inspect the selected block and discover every retiring statement handle")
        fn,target,portable,fingerprint,retired,retired_handles=self._target_projection()
        if not p["anchor_statement_handle"] in self.current_contract["allowed_anchor_handles"] or p["anchor_statement_handle"] not in retired_handles:
            raise WorkspaceError("MISSION_TARGET_DENIED","Anchor is not a child statement of the selected IF")
        if set(p["expected_removed_statement_handles"])!=set(self.current_contract["expected_removed_statement_handles"]) or len(p["expected_removed_statement_handles"])!=len(set(p["expected_removed_statement_handles"])):
            raise WorkspaceError("MISSION_RETIREMENT_SET_DENIED","Expected removed statement handles must exactly match the two branch assignments")
        if set(retired_handles)!=set(p["expected_removed_statement_handles"]):raise WorkspaceError("MISSION_RETIREMENT_SET_DENIED","Selected IF owns a different statement set")
        if p["expected_block_fingerprint"]!=fingerprint:raise WorkspaceError("EXPECTED_BLOCK_MISMATCH","Inspected block fingerprint is stale or incorrect")
        replacement=p["replacement_statements"]
        def call_handles(value):
            found=[]
            if isinstance(value,dict):
                if value.get("kind")=="call":found.append(value.get("function_handle"))
                for child in value.values():found.extend(call_handles(child))
            elif isinstance(value,list):
                for child in value:found.extend(call_handles(child))
            return found
        for handle in call_handles(replacement):
            if handle not in self.aliases or handle not in self.discovered:
                raise WorkspaceError("FUNCTION_NOT_DISCOVERED","Discover every referenced function handle before proposing the replacement")
        expected_call={"kind":"call","function_handle":HELPER,"arguments":[{"kind":"local_ref","name":"X"}]}
        if replacement!=[{"kind":"assign","target":{"kind":"result"},"expression":expected_call}]:
            raise WorkspaceError("MISSION_REPLACEMENT_DENIED","Mission permits one result assignment calling BASE_SCORE_CLASS(X)")
        function_id=self.aliases[SCORE]
        replacement_internal=[{"kind":"assign","target":{"kind":"result"},
            "expression":self._resolve_expr(expected_call,function_id)}]
        op={"operation":"replace_typed_if_block","function_id":function_id,"control_path":PATH,
            "anchor_statement_id":self.aliases[p["anchor_statement_handle"]],
            "expected_block_fingerprint":self.ws._typed_if_fingerprint(target)[0],
            "expected_removed_statement_ids":[self.aliases[h] for h in sorted(p["expected_removed_statement_handles"])],
            "replacement_statements":replacement_internal}
        candidate_ws=copy.deepcopy(self.ws); applied=candidate_ws.apply_transaction(self.doc,rev,[copy.deepcopy(op)])
        retired_ids=applied["retired_statement_ids"]
        if set(retired_ids)!={self.aliases[h] for h in retired_handles}:raise WorkspaceError("MISSION_RETIREMENT_SET_DENIED","Canonical candidate retired an unexpected statement identity")
        candidate_aliases=dict(self.aliases)
        for handle in retired_handles:candidate_aliases.pop(handle,None)
        created=[row for row in applied["created_statements"] if row["containing_function_id"]==function_id]
        new_handle=self.current_contract["replacement_statement_handle"]
        if len(created)!=1 or new_handle in candidate_aliases:raise WorkspaceError("MISSION_NEW_IDENTITY_INVALID","Replacement must allocate one fresh statement identity")
        candidate_aliases[new_handle]=created[0]["statement_id"]
        normalized=senior.normalized_state(projection_semantics(build_projection(candidate_ws,self.doc,applied["revision"])),candidate_aliases)
        before_norm=self.base_snapshot
        for row in before_norm["functions"]:
            if row["handle"]!=SCORE and senior.find_function(before_norm,row["handle"])!=senior.find_function(normalized,row["handle"]):
                raise WorkspaceError("MISSION_UNCHANGED_FUNCTION","Block replacement changed another function")
        before_projection=build_projection(self.ws,self.doc,rev); after_projection=build_projection(candidate_ws,self.doc,applied["revision"])
        old_fn=next(f for f in before_projection.functions if f.symbol_id==function_id)
        new_fn=next(f for f in after_projection.functions if f.symbol_id==function_id)
        if len(new_fn.statements)!=len(old_fn.statements) or new_fn.statements[1:]!=old_fn.statements[1:]:
            # Projected line numbers shift after deletion, so compare identity and
            # typed meaning while deliberately excluding source locations.
            old_tail=[self._statement_signature(x) for x in old_fn.statements[1:]]
            new_tail=[self._statement_signature(x) for x in new_fn.statements[1:]]
            if old_tail!=new_tail:raise WorkspaceError("MISSION_STATEMENT_PRESERVATION","Later SCORE_CLASS statements or identities changed")
        first=new_fn.statements[0]
        if not isinstance(first,Assignment) or not first.target_is_result or first.statement_id!=created[0]["statement_id"]:
            raise WorkspaceError("MISSION_REPLACEMENT_INVALID","Replacement is not a fresh result assignment")
        if self._expr_signature(first.expression)!=("call",self.aliases[HELPER],(("variable",self.aliases["score_class.parameter.id"],()),)):
            raise WorkspaceError("MISSION_CALL_BINDING","Replacement assignment is not bound to BASE_SCORE_CLASS(X)")
        edges_before=_edges(before_norm)
        edges_after=_edges(normalized)
        expected_edges=(edges_before-{(SCORE,NORMALIZER)})|{(SCORE,HELPER)}
        if edges_after!=expected_edges:raise WorkspaceError("MISSION_DEPENDENCY_GRAPH","Extraction dependency edges differ from the authorized direct-call replacement")
        observations=self._observe(candidate_ws,self.doc,applied["revision"],candidate_aliases)
        previous=self._observe(self.ws,self.doc,rev,self.aliases)
        if observations!=previous:raise WorkspaceError("MISSION_BEHAVIOR_CHANGED","Extraction candidate does not preserve all specified behavior")
        return [op],normalized,candidate_ws,candidate_aliases,retired_handles,new_handle,created[0],observations,portable,fingerprint

    def _preview_block(self,p,rid):
        revision=self.ws.get_revision(self.doc)
        try:
            result=self._mission_b_authorized(p)
        except WorkspaceError as exc:
            self.trace.emit("transaction_rejected",phase="mission-2",actor="mission_gateway",mission_id=self._mission_id(),
                base_revision=p.get("expected_revision"),resulting_revision=revision,code=exc.code,authoritative_state_unchanged=True)
            self.emit_visual({"event_id":f"cycle29-reject-{rid}","event_type":"rejection","revision":revision,
                "session_id":self.session_id,"mission_id":self.mission_title,"provenance":"MissionGateway denial",
                "title":"Block extraction proposal rejected","description":exc.message,
                "preview":{"status":"rejected","diagnostic":{"code":exc.code}},"outcome":{"committed":False}})
            self.flush_trace();return {"ok":False,"code":exc.code,"message":exc.message,"revision":revision,
                "revision_unchanged":True,"authoritative_workspace_changed":False}
        ops,candidate,candidate_ws,candidate_aliases,retired_handles,new_handle,created,observations,portable,fingerprint=result
        txid,raw=self.transactions.preview(operation_kind="replace_typed_if_block",base_revision=revision,
            operations=ops,candidate=candidate,metadata={"request":copy.deepcopy(p),"retired_handles":retired_handles,
                "new_handle":new_handle,"created_id":created["statement_id"]})
        self.block_pending[txid]=result
        self.trace.emit("operation_proposed",phase="mission-2",actor="pi_model_tool",mission_id=self._mission_id(),
            request_id=rid,transaction_id=txid,operation="replace_typed_if_block",arguments=p)
        self.trace.emit("preview_accepted",phase="mission-2",actor="mission_gateway",mission_id=self._mission_id(),
            transaction_id=txid,base_revision=revision,resulting_revision=revision+1,retired_statement_handles=retired_handles,
            new_statement_handle=new_handle)
        self.emit_visual({"event_id":f"cycle29-preview-{rid}","event_type":"preview","revision":revision,
            "session_id":self.session_id,"mission_id":self.mission_title,
            "provenance":"Genuine Pi typed proposal · accepted MissionGateway preview",
            "title":"BASE_SCORE_CLASS extraction preview","description":"The candidate replaces the first IF and retires its two branch assignments. Committed BASIC remains at revision 12.",
            "focus":{"handles":[SCORE,HELPER]+retired_handles,"mapping":"verified_function_boundary"},
            "preview":{"status":"accepted","diff":raw.get("diff"),"candidate_revision":revision+1,
                "retired_statement_handles":retired_handles,"new_statement_handle":new_handle,
                "replacement":p["replacement_statements"]},"dependencies":self._dependencies(),
            "outcome":{"authorized":True,"committed":False}})
        self.flush_trace()
        return {"ok":True,"accepted":True,"transaction_id":txid,"base_revision":revision,
            "expected_result_revision":revision+1,"candidate_is_preview_only":True,"diff":raw.get("diff"),
            "retired_statement_handles":retired_handles,"new_statement_handle":new_handle,
            "identity_migration":{"preserved":sorted(set(self.aliases)-set(retired_handles)),"retired":retired_handles,
                "newly_allocated":[new_handle]}}

    def _commit_block(self,p,rid):
        if set(p)!={"transaction_id"}:return {"ok":False,"committed":False,"code":"UNKNOWN_SEMANTIC_FIELD"}
        txid=p["transaction_id"]
        pending_result=self.block_pending.get(txid)
        if pending_result is None:return {"ok":False,"committed":False,"code":"PREVIEW_NOT_FOUND","revision":self.ws.get_revision(self.doc)}
        def revalidate(record,revision):
            result=self._mission_b_authorized(record["metadata"]["request"])
            ops,candidate,*tail=result
            if candidate!=record["candidate"]:raise WorkspaceError("CANDIDATE_CHANGED","Candidate differs from accepted preview")
            return ops,candidate,{"identity_migration":tail[2:6]}
        try:receipt=self.transactions.commit(txid,revalidate)
        except WorkspaceError as exc:return {"ok":False,"committed":False,"code":exc.code,"message":exc.message,
            "revision":self.ws.get_revision(self.doc),"authoritative_workspace_changed":False}
        meta=self.transactions.get(txid)["metadata"]; retired_handles=meta["retired_handles"]; new_handle=meta["new_handle"]
        old_aliases=dict(self.aliases); old_ids={h:old_aliases[h] for h in retired_handles}
        self.aliases={h:sid for h,sid in self.aliases.items() if h not in retired_handles}
        created=receipt.applied["created_statements"]
        new_rows=[row for row in created if row["containing_function_id"]==self.aliases[SCORE]]
        if len(new_rows)!=1:raise RuntimeError("committed replacement statement identity missing")
        self.aliases[new_handle]=new_rows[0]["statement_id"];self.retired.extend(
            {"portable_handle":h,"workspace_id":old_ids[h],"retired_at_revision":receipt.revision,"reason":"removed IF branch assignment during extraction"} for h in retired_handles)
        self.revision=receipt.revision;self.committed=True
        request=self.transactions.get(txid)["metadata"]["request"]
        portable_block=pending_result[8]
        constructive={"operation":"replace_typed_if_block","function_handle":SCORE,"control_path":PATH,
            "anchor_statement_handle":request["anchor_statement_handle"],"expected_block":portable_block,
            "expected_block_fingerprint":_fingerprint(portable_block),
            "expected_removed_statement_handles":retired_handles,"replacement_statements":request["replacement_statements"],
            "created_statement_handle":new_handle}
        self.committed_operations.append(constructive)
        self.block_pending.pop(txid,None)
        stream={"schema":"basic-workspace.constructive-metafile","version":1,"execution_profile_id":PROFILE_ID,
            "portable_handles":sorted(self.aliases),"retired_handles":[row["portable_handle"] for row in self.retired],
            "operations":self.committed_operations}
        self.write_json("constructive-operations.json",stream)
        self.write_json("identity-migration.json",self._identity_report())
        code=self.ws.render_document(self.doc)
        bundle=json.loads((self.output/"visual-source.json").read_text());bundle["snapshots"][str(self.revision)]=code
        bundle["dependencies"]=self._dependencies(self._normalized());self.write_json("visual-source.json",bundle)
        self.trace.emit("transaction_committed",phase="mission-2",actor="workspace_atomic_transaction",mission_id=self._mission_id(),
            transaction_id=txid,base_revision=12,resulting_revision=self.revision,operation="replace_typed_if_block",
            retired_statement_handles=retired_handles,new_statement_handle=new_handle,retired_workspace_ids=list(old_ids.values()),
            created_statement_id=self.aliases[new_handle])
        self.emit_visual({"event_id":f"cycle29-commit-{txid}","event_type":"commit","revision":self.revision,
            "snapshot":code,"session_id":self.session_id,"mission_id":self.mission_title,
            "provenance":"Workspace atomic semantic transaction · genuine Pi commit request",
            "title":"SCORE_CLASS block extracted","description":"The first IF was replaced by BASE_SCORE_CLASS(X). Its two branch assignments retired; the replacement has a fresh statement identity.",
            "focus":{"handles":[SCORE,HELPER,new_handle]+retired_handles,"mapping":"verified_function_boundary"},
            "dependencies":self._dependencies(self._normalized()),"outcome":{"committed":True,"workspace_revision":self.revision,
                "retired_statement_handles":retired_handles,"new_statement_handle":new_handle}})
        self.flush_trace()
        return {"ok":True,"committed":True,"revision":self.revision,"retired_statement_handles":retired_handles,
            "new_statement_handle":new_handle,"preserved_portable_identity_count":len(set(old_aliases)-set(retired_handles))}

    def _identity_report(self):
        return {"schema":"basic-workspace.identity-migration","version":1,"baseline_revision":11,
            "final_revision":self.ws.get_revision(self.doc),"initial_active_count":23,
            "preserved_unchanged":sorted(set(self.base_aliases)-{x["portable_handle"] for x in self.retired}),
            "preserved_with_new_references":[HELPER],"retired":self.retired,
            "newly_allocated":[{"portable_handle":h,"workspace_id":self.aliases.get(h),"created_revision":12 if h.startswith("base_score_class") else 13}
                for h in sorted(self.aliases) if h.startswith("base_score_class") or h=="score_class.statement.extracted-base-call"],
            "live_handles":sorted(self.aliases),"no_retired_handle_reuse":not any(row["portable_handle"] in self.aliases for row in self.retired)}

    def validate_current(self,requested_revision,actor="host"):
        revision=self.ws.get_revision(self.doc)
        if requested_revision!=revision:return {"reliable":False,"mission_complete":False,"code":"STALE_VALIDATION_REVISION","executed_revision":None}
        normalized=self._normalized(revision);observed=self._observe(self.ws,self.doc,revision,self.aliases)
        expected={engine:{} for engine in ("interp","jit")}
        for engine in expected:
            for x in INPUTS:
                normalized_score=max(0,min(50,x));expected_class=0 if normalized_score<20 else 1 if normalized_score<45 else 2 if normalized_score<50 else 3
                expected[engine][str(x)]={"normalize_score":float(normalized_score),"is_passing":float(normalized_score>=45),
                    "score_class":float(expected_class),"is_at_cap":float(normalized_score>=50)}
                if HELPER in self.aliases:expected[engine][str(x)]["base_score_class"]=float(0 if normalized_score<20 else 1)
        values_match=observed==expected;engines_agree=observed["interp"]==observed["jit"]
        if self.phase==1:
            prior_ok=all(senior.find_function(self.base_snapshot,h)==senior.find_function(normalized,h)
                for h in (NORMALIZER,"is_passing.function",SCORE,"is_at_cap.function"))
            edges=_edges(normalized)
            baseline_edges=_edges(self.base_snapshot)
            dependency_ok=edges==baseline_edges|{(HELPER,NORMALIZER)}
            added=senior.find_function(normalized,HELPER);signature=added["name"]=="BASE_SCORE_CLASS" and added["parameters"]==["base_score_class.parameter.id"]
        else:
            prior_ok=all(senior.find_function(self.base_snapshot,h)==senior.find_function(normalized,h)
                for h in (NORMALIZER,"is_passing.function","is_at_cap.function",HELPER))
            edges=_edges(normalized)
            baseline_edges=_edges(self.base_snapshot)
            dependency_ok=edges==(baseline_edges-{(SCORE,NORMALIZER)})|{(SCORE,HELPER)}
            score=senior.find_function(normalized,SCORE)
            dependency_ok=dependency_ok and len(score["statements"])==4 and score["statements"][0]["kind"]=="assignment" and score["statements"][0].get("statement_handle")=="score_class.statement.extracted-base-call"
            signature=True
        replay=self._replay_all()
        replay_ok=replay["structural_equivalence"] and replay["binding_equivalence"] and replay["behavioral_equivalence"] and replay["engines_agree"]
        complete=bool(self.committed and values_match and engines_agree and prior_ok and dependency_ok and signature and replay_ok)
        result={"schema":"basic-workspace.cycle29-mission-validation","version":1,"mission_id":self._mission_id(),
            "actor":actor,"reliable":True,"revision":revision,"executed_revision":revision,
            "observed_results":observed,"expected_results":expected,"values_match":values_match,"engines_agree":engines_agree,
            "preserved_program_invariants":prior_ok,"dependencies_match":dependency_ok,"new_function_signature_valid":signature,
            "mission_complete":complete,"replay":replay,"identity_migration":self._identity_report(),
            "diagnostics":[] if complete else ["Behavior, dependency, identity, preservation, or replay validation failed"]}
        self.last_validation=result; self.write_json(f"mission-{self.phase}-validation-{actor}.json",result)
        self.append_log(self.output/"validation.jsonl",result)
        self.trace.emit("program_validated",phase=f"mission-{self.phase}",actor="independent_host_validation" if actor=="host" else "pi_validation_tool",
            mission_id=self._mission_id(),revision=revision,executed_revision=revision,passed=complete,engines_agree=engines_agree,
            replay_passed=replay_ok,identity_migration=self._identity_report())
        self.emit_visual({"event_id":f"cycle29-validation-{self.phase}-{revision}-{actor}","event_type":"validation",
            "revision":revision,"session_id":self.session_id,"mission_id":self.mission_title,
            "provenance":"Independent host MIR interpreter/JIT and portable replay oracle" if actor=="host" else "Pi-requested host validation",
            "title":f"{actor.title()} validation {'passed' if complete else 'failed'} · revision {revision}",
            "description":"The finite behavior oracle, dependency graph, preservation invariants, identity migration, and full fresh-workspace replay were checked.",
            "validation":{"passed":complete,"engines_agree":engines_agree,"replay_passed":replay_ok},
            "observation":{"function":"BASE_SCORE_CLASS and SCORE_CLASS","arguments":INPUTS,"engine_results":observed,"revision":revision,"agreement":engines_agree},
            "dependencies":self._dependencies(normalized)})
        self.flush_trace();return result

    def _replay_all(self):
        # Fresh empty Workspace replay: Cycle28Gateway authenticates/rebuilds
        # the first nine ops; we then apply Cycle28's exact commit and Cycle29's
        # committed portable operations in order.
        with tempfile.TemporaryDirectory(prefix="atlas-cycle29-replay-",dir="/var/tmp") as td:
            seed=Cycle28Gateway(Path(td)/"seed",C28_CONTRACT)
            seed.discovered={h for h in seed.aliases if h.endswith(".function")}
            stream=json.loads((BASE/"constructive-operations.json").read_text()); ops=copy.deepcopy(stream["operations"])
            cond=ops[9];fid=seed.aliases[cond["function_handle"]]
            internal={"operation":"edit_typed_if_condition","function_id":fid,"control_path":cond["control_path"],
                "anchor_statement_id":seed.aliases[cond["anchor_statement_handle"]],
                "expected_condition":seed._resolve_expr(cond["expected_condition"],fid),"condition":seed._resolve_expr(cond["condition"],fid)}
            seed.ws.apply_transaction(seed.doc,seed.ws.get_revision(seed.doc),[internal]);aliases=dict(seed.aliases)
            added=self.committed_operations[len(ops):]
            replay_ops=copy.deepcopy(ops)
            for item in added:
                if item["operation"]=="create_numeric_function":
                    refs={call.get("function_handle") for call in self._calls(item["arguments"]) if call.get("function_handle")}
                    if not refs.issubset(aliases):raise WorkspaceError("REPLAY_HANDLE_MISSING","Creation replay references an unavailable portable function")
                    args=senior.resolve_function_handles(item["arguments"],aliases,refs)
                    applied=seed.ws.apply_transaction(seed.doc,seed.ws.get_revision(seed.doc),[{"operation":"create_numeric_function",**args}])
                    raw=projection_semantics(build_projection(seed.ws,seed.doc,applied["revision"]))
                    aliases=senior.aliases_for_new_function(raw,aliases,args["name"],item["portable_handle"])
                    replay_ops.append(copy.deepcopy(item))
                elif item["operation"]=="replace_typed_if_block":
                    function_id=aliases.get(item["function_handle"])
                    anchor=aliases.get(item["anchor_statement_handle"])
                    projection=build_projection(seed.ws,seed.doc,seed.ws.get_revision(seed.doc))
                    fn=next(f for f in projection.functions if f.symbol_id==function_id)
                    selected=fn.statements[item["control_path"][0]["index"]]
                    portable=self._portable_block_for(seed.ws,seed.doc,selected,aliases)
                    if portable!=item["expected_block"] or _fingerprint(portable)!=item["expected_block_fingerprint"]:
                        raise WorkspaceError("REPLAY_BLOCK_MISMATCH","Portable expected block differs during fresh replay")
                    retired=item["expected_removed_statement_handles"]
                    local_op={"operation":"replace_typed_if_block","function_id":function_id,"control_path":item["control_path"],
                        "anchor_statement_id":anchor,"expected_block_fingerprint":seed.ws._typed_if_fingerprint(selected)[0],
                        "expected_removed_statement_ids":[aliases[h] for h in retired],
                        "replacement_statements":[{"kind":"assign","target":{"kind":"result"},
                            "expression":self._resolve_expr_for(seed.ws,seed.doc,aliases,function_id,row["expression"])} for row in item["replacement_statements"]]}
                    applied=seed.ws.apply_transaction(seed.doc,seed.ws.get_revision(seed.doc),[local_op])
                    aliases={h:sid for h,sid in aliases.items() if h not in retired}
                    new_rows=[row for row in applied["created_statements"] if row["containing_function_id"]==function_id]
                    if len(new_rows)!=1:raise WorkspaceError("REPLAY_NEW_IDENTITY","Expected exactly one extracted assignment identity")
                    aliases[item["created_statement_handle"]]=new_rows[0]["statement_id"]
                    replay_ops.append(copy.deepcopy(item))
                else:raise WorkspaceError("REPLAY_OPERATION_UNSUPPORTED",f"Unsupported Cycle29 replay op: {item['operation']}")
            revision=seed.ws.get_revision(seed.doc);replay_norm=senior.normalized_state(projection_semantics(build_projection(seed.ws,seed.doc,revision)),aliases)
            live_norm=self._normalized()
            replay_observed=self._observe(seed.ws,seed.doc,revision,aliases);live_observed=self._observe(self.ws,self.doc,self.ws.get_revision(self.doc),self.aliases)
            map_rows=[{"portable_handle":h,"live_workspace_id":self.aliases[h],"replay_workspace_id":aliases[h],
                "remapped":self.aliases[h]!=aliases[h]} for h in sorted(self.aliases)]
            return {"revision":revision,"operation_count":len(replay_ops),"structural_equivalence":live_norm==replay_norm,
                "binding_equivalence":_edges(live_norm)==_edges(replay_norm),
                "behavioral_equivalence":live_observed==replay_observed,"engines_agree":replay_observed["interp"]==replay_observed["jit"],
                "identity_remappings":sum(row["remapped"] for row in map_rows),"identity_mapping":map_rows,
                "retired_handles_not_reused":all(row["portable_handle"] not in aliases for row in self.retired),
                "retired_identities":copy.deepcopy(self.retired),"replay_active_handles":sorted(aliases),
                "observations":replay_observed,"passed":live_norm==replay_norm and live_observed==replay_observed and replay_observed["interp"]==replay_observed["jit"]}

    def _resolve_expr_for(self,ws,doc,aliases,function_id,value):
        old_ws,old_doc,old_aliases,old_discovered=self.ws,self.doc,self.aliases,self.discovered
        self.ws,self.doc,self.aliases,self.discovered=ws,doc,aliases,set(aliases)
        try:return self._resolve_expr(value,function_id)
        finally:self.ws,self.doc,self.aliases,self.discovered=old_ws,old_doc,old_aliases,old_discovered

    def handle(self,method,p,rid):
        if method=="prepare_mission_b":return self.prepare_mission_b(p)
        if method=="create_mission_b_checkpoint":return self.create_mission_b_checkpoint()
        if method=="get_status":return {"revision":self.ws.get_revision(self.doc),"phase":self.phase,
            "mission_id":self._mission_id(),"committed":self.committed,"handles":sorted(self.aliases),
            "host_validation_passed":bool(self.last_validation and self.last_validation.get("mission_complete"))}
        if method=="inspect_program":return self._inspect(rid)
        if method=="commit_preview" and self.phase==1:
            result=Cycle19Gateway.handle(self,method,p,rid)
            if result.get("committed"):
                bundle=json.loads((self.output/"visual-source.json").read_text())
                bundle["snapshots"][str(result["revision"])]=self.ws.render_document(self.doc)
                bundle["dependencies"]=self._dependencies(self._normalized())
                self.write_json("visual-source.json",bundle)
            return result
        if method=="preview_block_replacement":
            return self._preview_block(p,rid)
        if method=="commit_preview" and self.phase==2:
            return self._commit_block(p,rid)
        if method in ("validate_mission","host_validate"):
            return self.validate_current(p.get("expected_revision"),"host" if method=="host_validate" else "pi_tool")
        return Cycle19Gateway.handle(self,method,p,rid)

    def record_gateway_timing(self,request,elapsed_ms):
        params=request.get("params") or {};transport=request.get("transport") or {};method=request.get("method")
        self.append_log(self.gateway_timings,{"request_id":request.get("request_id"),"tool_call_id":transport.get("tool_call_id"),
            "method":method,"mission_id":self._mission_id(),"phase":self.phase,"elapsed_ms":round(elapsed_ms,3),
            "agent_tool":method in {"discover_functions","inspect_program","preview_create_function","preview_block_replacement","commit_preview","validate_mission"}})

def age_trace():
    from cycle19_gateway import age
    return age.Trace()

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--output",type=Path,required=True);ap.add_argument("--port",type=int,default=0)
    args=ap.parse_args();service=Cycle29Gateway(args.output)
    with Server(("127.0.0.1",args.port),service) as server:
        print(json.dumps({"ready":True,"host":"127.0.0.1","port":server.server_address[1],
            "revision":service.ws.get_revision(service.doc),"identity_count":len(service.aliases)},separators=(",",":")),flush=True)
        server.serve_forever()
if __name__=="__main__":main()
