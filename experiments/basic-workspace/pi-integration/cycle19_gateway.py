#!/usr/bin/env python3
"""Two-mission, empty-document semantic gateway for Cycle 19."""
from __future__ import annotations
import argparse, copy, hashlib, importlib.util, json, math, sys, threading, time, uuid
from pathlib import Path
from typing import Any

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(HERE))
from basic_workspace.model import Workspace, WorkspaceError
from basic_workspace.projection import build_projection, projection_semantics
from basic_workspace.mir_execution import MirExecutionService
from basic_workspace.portable_replay import replay_constructive_stream
from pi_lifecycle import completion_states
from gateway import Cycle16Gateway, Server
from transaction_kernel import SemanticTransactionKernel

spec=importlib.util.spec_from_file_location("cycle19_senior",ROOT/"scripts/is-senior-campaign.py")
senior=importlib.util.module_from_spec(spec); assert spec and spec.loader; sys.modules[spec.name]=senior; spec.loader.exec_module(senior)
age_spec=importlib.util.spec_from_file_location("cycle19_age",ROOT/"scripts/age-by-id-campaign.py")
age=importlib.util.module_from_spec(age_spec); assert age_spec and age_spec.loader; sys.modules[age_spec.name]=age; age_spec.loader.exec_module(age)
PROFILE_ID="basic-workspace.numeric-composition.v1"
INPUTS=(-100,-1,0,1,59,60,99,100,101,200)

class Cycle19Gateway:
    def __init__(self, output:Path, resume_from:Path|None=None, *, creation_contract_path:Path|None=None,
                 seed_contract_path:Path|None=None, baseline_stream_path:Path|None=None,
                 baseline_history_path:Path|None=None, baseline_validation_path:Path|None=None,
                 creation_sequence_path:Path|None=None, sequence_stream_path:Path|None=None,
                 sequence_checkpoint_path:Path|None=None):
        self.output=output; output.mkdir(parents=True,exist_ok=True); self.sequence_mode=False
        if creation_sequence_path is not None:
            self._init_creation_sequence(creation_sequence_path, sequence_stream_path, sequence_checkpoint_path)
            return
        if creation_contract_path is not None:
            self._init_from_verified_stream(creation_contract_path,seed_contract_path,
                baseline_stream_path,baseline_history_path,baseline_validation_path)
            return
        self.ws=Workspace(); self.doc=self.ws.create_empty_document("memory://cycle19/empty.bas")["document_id"]
        self.aliases:dict[str,str]={}; self.trace=age.Trace(); self.lock=threading.RLock()
        self.revision=self.ws.get_revision(self.doc); self.phase=1; self.transactions=SemanticTransactionKernel(self.ws,self.doc); self.dispatched={}
        self.resume_verification=None
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
        (output/"MISSION-1.json").write_text(json.dumps(self.mission_contract(1),indent=2)+"\n")
        (output/"MISSION-2.json").write_text(json.dumps(self.mission_contract(2,base_revision=2),indent=2)+"\n")
        profile=json.loads((ROOT/"results/semantic-replay/execution-profile.json").read_text())
        self.write_json("execution-profile.json",profile)
        self.append_log(output/"setup.jsonl",{"kind":"empty_workspace_created","revision":self.revision,
            "document_token_count":0,"functions":[],"host_inserted_program_logic":False,"execution_profile_id":PROFILE_ID})
        if resume_from is None:
            bundle={"schema":"basic-workspace.visual-source","version":1,
                "campaign":{"id":"cycle19-empty-workspace","title":"Cycle 19 · agent-built BASIC from an empty Workspace","filename":"SCORES.bas"},
                "initial":self.initial,"snapshots":{str(self.revision):""}}
            self.write_json("visual-source.json",bundle)
            self.emit_visual({"event_id":"cycle19-empty-start","event_type":"initial","revision":self.revision,
                "session_id":"cycle19-mission-1","mission_id":self.mission_title,"provenance":"Workspace.create_empty_document",
                "title":"Empty Workspace","description":"Canonical document created with zero tokens and no functions. No BASIC seed was inserted.",
                "mission_status":"Mission 1 pending · empty committed revision 1","dependencies":[]})
        else:
            self._resume_from_cycle19(resume_from)

    @staticmethod
    def _validate_creation_sequence(contract):
        required={"schema","version","sequence_id","objective","execution_profile_id","starting_revision","maximum_steps","steps"}
        if not isinstance(contract,dict) or set(contract)!=required:
            raise WorkspaceError("SEQUENCE_CONTRACT_INVALID","Creation sequence has missing or unsupported fields")
        version=contract["version"]
        if isinstance(version,bool) or not isinstance(version,int) or version!=1 or contract["schema"]!="basic-workspace.numeric-function-creation-sequence":
            raise WorkspaceError("SEQUENCE_CONTRACT_VERSION","Unsupported numeric function creation sequence")
        if not isinstance(contract["sequence_id"],str) or not contract["sequence_id"] or not isinstance(contract["objective"],str) or not contract["objective"]:
            raise WorkspaceError("SEQUENCE_CONTRACT_INVALID","Sequence identifier and objective are required")
        if (contract["execution_profile_id"]!=PROFILE_ID or isinstance(contract["starting_revision"],bool)
                or not isinstance(contract["starting_revision"],int) or contract["starting_revision"]!=1):
            raise WorkspaceError("SEQUENCE_CONTRACT_PROFILE","Creation sequences must start from an empty revision-1 Workspace using the configured profile")
        if isinstance(contract["maximum_steps"],bool) or not isinstance(contract["maximum_steps"],int) or not 1<=contract["maximum_steps"]<=8:
            raise WorkspaceError("SEQUENCE_CONTRACT_LIMIT","maximum_steps must be an integer from 1 through 8")
        steps=contract["steps"]
        if not isinstance(steps,list) or not 1<=len(steps)<=contract["maximum_steps"]:
            raise WorkspaceError("SEQUENCE_CONTRACT_STEPS","Sequence must contain a bounded nonempty ordered step list")
        step_fields={"step_id","mission_id","expected_base_revision","function","required_callees",
            "required_dependency_edges","required_existing_function_handles_unchanged","validation"}
        step_ids=set(); mission_ids=set(); function_handles=set(); function_names=set(); all_names=[]
        for index,step in enumerate(steps):
            if not isinstance(step,dict) or set(step)!=step_fields:
                raise WorkspaceError("SEQUENCE_STEP_INVALID",f"Step {index} has missing or unsupported fields")
            if not isinstance(step["step_id"],str) or not step["step_id"] or step["step_id"] in step_ids:
                raise WorkspaceError("SEQUENCE_STEP_ID","Step IDs must be unique nonempty strings")
            if not isinstance(step["mission_id"],str) or not step["mission_id"] or step["mission_id"] in mission_ids:
                raise WorkspaceError("SEQUENCE_MISSION_ID","Mission IDs must be unique nonempty strings")
            step_ids.add(step["step_id"]); mission_ids.add(step["mission_id"])
            revision=step["expected_base_revision"]
            if isinstance(revision,bool) or not isinstance(revision,int) or revision!=contract["starting_revision"]+index:
                raise WorkspaceError("SEQUENCE_REVISION_ORDER",f"Step {step['step_id']} must start at revision {contract['starting_revision']+index}")
            fn=step["function"]
            if not isinstance(fn,dict) or set(fn)!={"name","portable_handle","parameters","return_type"}:
                raise WorkspaceError("SEQUENCE_FUNCTION_INVALID","Each step requires name, portable handle, parameters and return type")
            name,handle,parameters=fn["name"],fn["portable_handle"],fn["parameters"]
            if not isinstance(name,str) or not name.isidentifier() or name.casefold() in function_names:
                raise WorkspaceError("SEQUENCE_FUNCTION_NAME","Function names must be unique nonempty strings")
            if (not isinstance(handle,str) or not handle.endswith(".function") or
                    not handle[:-9].isidentifier() or handle in function_handles):
                raise WorkspaceError("SEQUENCE_FUNCTION_HANDLE","Each function requires a unique portable .function handle")
            if (fn["return_type"]!="numeric" or not isinstance(parameters,list) or len(parameters)!=1 or
                    not isinstance(parameters[0],str) or not parameters[0].isidentifier()):
                raise WorkspaceError("SEQUENCE_FUNCTION_SIGNATURE","Only one-parameter numeric functions are supported")
            if parameters[0].endswith("$"):
                raise WorkspaceError("SEQUENCE_FUNCTION_SIGNATURE","Function parameters must be numeric")
            function_names.add(name.casefold()); function_handles.add(handle); all_names.append(name.casefold())
            callees=step["required_callees"]
            if (not isinstance(callees,list) or any(not isinstance(x,str) for x in callees) or
                    len(callees)!=len(set(callees)) or any(x not in function_handles-{handle} for x in callees)):
                raise WorkspaceError("SEQUENCE_DEPENDENCY_ORDER","Required callees must be unique functions created by earlier steps")
            edges=step["required_dependency_edges"]
            if not isinstance(edges,list):
                raise WorkspaceError("SEQUENCE_DEPENDENCY_INVALID","required_dependency_edges must be an array")
            edge_set=set()
            for edge in edges:
                if (not isinstance(edge,dict) or set(edge)!={"caller_handle","callee_handle"} or
                        edge["caller_handle"]!=handle or not isinstance(edge["callee_handle"],str) or edge["callee_handle"] not in callees):
                    raise WorkspaceError("SEQUENCE_DEPENDENCY_INVALID","Each declared edge must originate at this new function and target a required earlier callee")
                edge_set.add((edge["caller_handle"],edge["callee_handle"]))
            if edge_set!={(handle,callee) for callee in callees}:
                raise WorkspaceError("SEQUENCE_DEPENDENCY_INVALID","Every required callee needs exactly one declared dependency edge")
            unchanged=step["required_existing_function_handles_unchanged"]
            expected_prior=[row["function"]["portable_handle"] for row in steps[:index]]
            if unchanged!=expected_prior:
                raise WorkspaceError("SEQUENCE_INVARIANT_INVALID","Each step must preserve every function from the completed prefix in order")
            validation=step["validation"]
            if not isinstance(validation,dict) or set(validation)!={"inputs","expected_results"}:
                raise WorkspaceError("SEQUENCE_VALIDATION_INVALID","Each step requires finite inputs and independent expected results")
            inputs=validation["inputs"]
            if not isinstance(inputs,list) or not inputs:
                raise WorkspaceError("SEQUENCE_VALIDATION_INVALID","Validation inputs must be a nonempty array")
            input_keys=[]
            for value in inputs:
                if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(float(value)):
                    raise WorkspaceError("SEQUENCE_VALIDATION_INVALID","Validation inputs must be finite numbers")
                input_keys.append(str(value))
            if len(set(input_keys))!=len(input_keys):
                raise WorkspaceError("SEQUENCE_VALIDATION_INVALID","Validation inputs must be unique")
            expected=validation["expected_results"]
            if not isinstance(expected,dict) or set(expected)!=set(input_keys):
                raise WorkspaceError("SEQUENCE_VALIDATION_INVALID","Expected result rows must match the exact input corpus")
            expected_names=set(all_names)
            for row in expected.values():
                if not isinstance(row,dict) or set(row)!=expected_names:
                    raise WorkspaceError("SEQUENCE_VALIDATION_INVALID","Every oracle row must report every function present at this revision")
                for value in row.values():
                    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(float(value)):
                        raise WorkspaceError("SEQUENCE_VALIDATION_INVALID","Expected results must be finite numbers")
        return copy.deepcopy(contract)

    @staticmethod
    def _sequence_fingerprint(contract):
        payload=json.dumps(contract,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
        return hashlib.sha256(payload).hexdigest()

    def _init_creation_sequence(self,sequence_path,stream_path=None,checkpoint_path=None):
        sequence_path=Path(sequence_path).resolve()
        self.sequence_contract=self._validate_creation_sequence(json.loads(sequence_path.read_text(encoding="utf-8")))
        self.sequence_path=sequence_path
        self.sequence_fingerprint=self._sequence_fingerprint(self.sequence_contract)
        self.sequence_mode=True; self.sequence_cursor=0; self.sequence_complete=False
        self.sequence_completed=[]; self.sequence_checkpoints=[]; self.last_sequence_checkpoint=None
        self.ws=Workspace(); self.doc=self.ws.create_empty_document("memory://cycle35/empty.bas")["document_id"]
        self.aliases={}; self.trace=age.Trace(); self.lock=threading.RLock()
        self.transactions=SemanticTransactionKernel(self.ws,self.doc); self.dispatched={}
        self.revision=self.ws.get_revision(self.doc); self.phase=3; self.resume_verification=None
        self.pi_seen=set(); self.presentation_seq=0; self.committed_operations=[]; self.completed_missions=[]
        self.last_validation=None; self.session_id=f"{self.sequence_contract['sequence_id']}-step-01"
        self.base_snapshot={"functions":[]}; self.base_aliases={}; self.discovered=set(); self.committed=False
        self.current_contract=None; self.current_step=None; self.mission_specs={}
        self.mission_title=self.sequence_contract["objective"]
        self.visual_events=self.output/"visual-events.jsonl"; self.gateway_timings=self.output/"gateway-tool-timings.jsonl"
        self.pi_events=self.output/"pi-tool-lifecycle.jsonl"
        self.initial={"revision":1,"code":"","dependencies":[]}
        self.write_json("execution-profile.json",json.loads((ROOT/"results/semantic-replay/execution-profile.json").read_text()))
        self.write_json("creation-sequence.json",self.sequence_contract)
        if stream_path is not None or checkpoint_path is not None:
            if stream_path is None or checkpoint_path is None:
                raise WorkspaceError("SEQUENCE_RECOVERY_EVIDENCE","Resume requires both a constructive prefix and a checkpoint")
            self._reconstruct_creation_sequence_prefix(Path(stream_path),Path(checkpoint_path))
        else:
            self._activate_creation_step(0)
            (self.output/"setup.jsonl").write_text(json.dumps({"kind":"empty_workspace_created","revision":1,
                "function_count":0,"host_inserted_program_logic":False,"sequence_id":self.sequence_contract["sequence_id"]},separators=(",",":"))+"\n")
        self.write_json("visual-source.json",{"schema":"basic-workspace.visual-source","version":1,
            "campaign":{"id":self.sequence_contract["sequence_id"],"title":self.sequence_contract["objective"],"filename":"PROGRAM.bas"},
            "initial":self.initial,"snapshots":{str(self.ws.get_revision(self.doc)):self.code()}})

    def _activate_creation_step(self,index):
        if index<0 or index>=len(self.sequence_contract["steps"]):
            self.sequence_cursor=len(self.sequence_contract["steps"]); self.sequence_complete=True
            self.current_step=None; self.current_contract=None; self.committed=True
            return
        step=self.sequence_contract["steps"][index]; fn=step["function"]
        self.sequence_cursor=index; self.sequence_complete=False; self.phase=3+index
        self.current_step=step
        self.current_contract={"mission_id":step["mission_id"],"name":fn["name"],"handle":fn["portable_handle"],
            "parameter":fn["parameters"][0],"parameters":list(fn["parameters"]),"return_type":fn["return_type"],
            "callee":step["required_callees"][0] if len(step["required_callees"])==1 else None,
            "required_callees":list(step["required_callees"]),"required_dependency_edges":[
                {"caller":edge["caller_handle"],"callee":edge["callee_handle"]}
                for edge in step["required_dependency_edges"]],
            "required_existing_function_handles_unchanged":list(step["required_existing_function_handles_unchanged"]),
            "objective":self.sequence_contract["objective"],"validation":copy.deepcopy(step["validation"])}
        self.mission_specs[self.phase]=self.current_contract
        self.mission_title=f"Creation sequence · {index+1}/{len(self.sequence_contract['steps'])} · {fn['name']}"
        self.session_id=f"{self.sequence_contract['sequence_id']}-step-{index+1:02d}"
        self.revision=self.ws.get_revision(self.doc)
        if self.revision!=step["expected_base_revision"]:
            raise WorkspaceError("SEQUENCE_REVISION_MISMATCH",f"Step {step['step_id']} expected revision {step['expected_base_revision']}, current revision is {self.revision}")
        self.base_snapshot=self._normalized() if self.aliases else {"functions":[]}
        self.base_aliases=dict(self.aliases); self.discovered=set(); self.transactions.clear(); self.committed=False
        self.last_validation=None; self.last_sequence_checkpoint=None

    def _reconstruct_creation_sequence_prefix(self,stream_path,checkpoint_path):
        stream=json.loads(stream_path.read_text(encoding="utf-8")); checkpoint=json.loads(checkpoint_path.read_text(encoding="utf-8"))
        if not isinstance(stream,dict) or set(stream)!={"schema","version","execution_profile_id","portable_handles","operations"}:
            raise WorkspaceError("SEQUENCE_RECOVERY_STREAM","Prefix stream has missing or unsupported fields")
        if stream["schema"]!="basic-workspace.constructive-metafile" or stream["version"]!=1 or stream["execution_profile_id"]!=PROFILE_ID:
            raise WorkspaceError("SEQUENCE_RECOVERY_STREAM","Prefix stream uses an unsupported schema or execution profile")
        completed=checkpoint.get("completed_steps") if isinstance(checkpoint,dict) else None
        if not isinstance(completed,list) or not 1<=len(completed)<len(self.sequence_contract["steps"]):
            raise WorkspaceError("SEQUENCE_RECOVERY_CHECKPOINT","Resume checkpoint must identify a nonempty incomplete sequence prefix")
        prefix_length=len(completed); operations=stream["operations"]
        if not isinstance(operations,list) or len(operations)!=prefix_length:
            raise WorkspaceError("SEQUENCE_RECOVERY_PREFIX","Operation count does not match the claimed completed prefix")
        for index,(operation,step,completion) in enumerate(zip(operations,self.sequence_contract["steps"],completed)):
            if (not isinstance(completion,dict) or set(completion)!={"step_id","mission_id","revision","validated"}
                    or completion!={"step_id":step["step_id"],"mission_id":step["mission_id"],
                        "revision":step["expected_base_revision"]+1,"validated":True}):
                raise WorkspaceError("SEQUENCE_RECOVERY_CHECKPOINT",f"Checkpoint completion row {index} does not match the ordered contract prefix")
            if not isinstance(operation,dict) or operation.get("operation")!="create_numeric_function" or operation.get("portable_handle")!=step["function"]["portable_handle"]:
                raise WorkspaceError("SEQUENCE_RECOVERY_ORDER","Constructive prefix does not follow the configured step order")
            args=operation.get("arguments")
            if not isinstance(args,dict) or args.get("name")!=step["function"]["name"] or args.get("parameters")!=step["function"]["parameters"]:
                raise WorkspaceError("SEQUENCE_RECOVERY_SIGNATURE","Recorded constructor differs from the configured step signature")
        expected_handles=set(stream.get("portable_handles",[]))
        if len(expected_handles)!=len(stream.get("portable_handles",[])) or stream.get("retired_handles",[]) not in (None,[]):
            raise WorkspaceError("SEQUENCE_RECOVERY_IDENTITIES","Creation-only prefix has duplicate or retired portable identities")
        replay=replay_constructive_stream(self.ws,self.doc,operations,expected_final_handles=sorted(expected_handles),
            expected_start_revision=1)
        expected_function_handles={step["function"]["portable_handle"] for step in self.sequence_contract["steps"][:prefix_length]}
        actual_function_handles={handle for handle in replay.live_handles if handle.endswith(".function")}
        if actual_function_handles!=expected_function_handles or replay.revision!=1+prefix_length:
            raise WorkspaceError("SEQUENCE_RECOVERY_IDENTITIES","Replayed prefix function handles or revision differ from contract")
        self.aliases=dict(replay.live_handles); self.committed_operations=copy.deepcopy(operations)
        self.sequence_completed=copy.deepcopy(completed); self.completed_missions=copy.deepcopy(completed)
        for index in range(prefix_length):
            self._verify_sequence_revision(index,index)
        normalized=self._normalized()
        if set(checkpoint)!={"schema","version","sequence_id","sequence_fingerprint","completed_steps","active_step_id",
                "revision","semantic_fingerprint","portable_handles","function_signatures","dependencies","last_validation"}:
            raise WorkspaceError("SEQUENCE_RECOVERY_CHECKPOINT","Checkpoint contains missing or unsupported fields")
        if checkpoint["schema"]!="basic-workspace.creation-sequence-checkpoint" or checkpoint["version"]!=1:
            raise WorkspaceError("SEQUENCE_RECOVERY_CHECKPOINT","Unsupported creation sequence checkpoint")
        next_step=self.sequence_contract["steps"][prefix_length]
        if (checkpoint["sequence_id"]!=self.sequence_contract["sequence_id"] or checkpoint["sequence_fingerprint"]!=self.sequence_fingerprint
                or checkpoint["active_step_id"]!=next_step["step_id"] or checkpoint["revision"]!=replay.revision
                or checkpoint["semantic_fingerprint"]!=self._program_fingerprint(normalized)
                or checkpoint["portable_handles"]!=sorted(self.aliases)
                or checkpoint["function_signatures"]!=self._sequence_signatures(normalized)
                or checkpoint["dependencies"]!=self._dependencies(normalized)
                or not isinstance(checkpoint["last_validation"],dict)
                or set(checkpoint["last_validation"])!={"actor","mission_complete","revision","engines_agree","replay_passed"}
                or checkpoint["last_validation"]!={"actor":"host","mission_complete":True,"revision":replay.revision,
                    "engines_agree":True,"replay_passed":True}):
            raise WorkspaceError("SEQUENCE_RECOVERY_FINGERPRINT","Checkpoint does not attest the replayed committed prefix")
        self.resume_verification={"passed":True,"revision":replay.revision,"completed_steps":prefix_length,
            "semantic_fingerprint":checkpoint["semantic_fingerprint"],"portable_handle_count":len(self.aliases),
            "source":"shared portable constructive replay plus independent step validations"}
        self.initial={"revision":1,"code":"","dependencies":[]}
        self.write_json("sequence-reconstruction-verification.json",self.resume_verification)
        self._activate_creation_step(prefix_length)
        self.append_log(self.output/"setup.jsonl",{"kind":"validated_sequence_prefix_reconstructed","revision":replay.revision,
            "completed_steps":prefix_length,"active_step":self.current_step["step_id"],"replay_actor":"host_deterministic_replay"})

    def _sequence_signatures(self,normalized):
        return [{"handle":row["handle"],"name":row["name"],"parameters":row["parameters"],"return_type":row["return_type"]}
            for row in normalized["functions"]]

    def _sequence_checkpoint(self):
        normalized=self._normalized(); revision=self.ws.get_revision(self.doc)
        completed=[*self.sequence_completed,{
            "step_id":self.current_step["step_id"],"mission_id":self.current_step["mission_id"],
            "revision":revision,"validated":True}]
        next_index=self.sequence_cursor+1
        return {"schema":"basic-workspace.creation-sequence-checkpoint","version":1,
            "sequence_id":self.sequence_contract["sequence_id"],"sequence_fingerprint":self.sequence_fingerprint,
            "completed_steps":completed,
            "active_step_id":self.sequence_contract["steps"][next_index]["step_id"] if next_index<len(self.sequence_contract["steps"]) else None,
            "revision":revision,"semantic_fingerprint":self._program_fingerprint(normalized),
            "portable_handles":sorted(self.aliases),"function_signatures":self._sequence_signatures(normalized),
            "dependencies":self._dependencies(normalized),
            "last_validation":{"actor":"host","mission_complete":True,"revision":revision,
                "engines_agree":self.last_validation.get("engines_agree"),
                "replay_passed":self.last_validation.get("replay",{}).get("passed")}}

    def _advance_creation_sequence(self,checkpoint):
        revision=self.ws.get_revision(self.doc)
        if (not self.sequence_mode or self.sequence_complete or not self.committed or not self.last_validation
                or self.last_validation.get("actor")!="host" or not self.last_validation.get("mission_complete")):
            return {"ok":False,"code":"SEQUENCE_STEP_NOT_VALIDATED","revision":revision,"progress_advanced":False}
        if self.last_sequence_checkpoint is None:
            return {"ok":False,"code":"SEQUENCE_CHECKPOINT_REQUIRED","revision":revision,"progress_advanced":False}
        if checkpoint!=self.last_sequence_checkpoint:
            return {"ok":False,"code":"SEQUENCE_CHECKPOINT_MISMATCH","revision":revision,"progress_advanced":False}
        expected=self._sequence_checkpoint()
        if checkpoint!=expected or checkpoint["revision"]!=revision or checkpoint["sequence_fingerprint"]!=self.sequence_fingerprint:
            return {"ok":False,"code":"SEQUENCE_CHECKPOINT_STALE","revision":revision,"progress_advanced":False}
        self.sequence_completed=copy.deepcopy(checkpoint["completed_steps"])
        next_index=self.sequence_cursor+1
        if next_index==len(self.sequence_contract["steps"]):
            self.sequence_cursor=next_index; self.sequence_complete=True; self.committed=True
            self.current_step=None; self.current_contract=None
            self.append_log(self.output/"creation-sequence-history.jsonl",{"event":"sequence_completed",
                "revision":revision,"completed_steps":len(self.sequence_completed),"sequence_id":self.sequence_contract["sequence_id"]})
            return {"ok":True,"sequence_completed":True,"revision":revision,"progress_advanced":True}
        self._activate_creation_step(next_index)
        self.append_log(self.output/"creation-sequence-history.jsonl",{"event":"step_advanced",
            "revision":revision,"completed_step":checkpoint["completed_steps"][-1]["step_id"],
            "active_step":self.current_step["step_id"],"sequence_id":self.sequence_contract["sequence_id"]})
        return {"ok":True,"sequence_completed":False,"revision":revision,
            "active_step_id":self.current_step["step_id"],"mission_id":self.current_step["mission_id"],
            "function_handles":self._function_handles(),"progress_advanced":True}

    def _verify_sequence_revision(self,step_index,revision_offset):
        revision=2+revision_offset
        step=self.sequence_contract["steps"][step_index]
        prefix_ws=Workspace(); prefix_doc=prefix_ws.create_empty_document("memory://cycle35/prefix-check.bas")["document_id"]
        prefix_ops=self.committed_operations[:revision_offset+1]
        prefix_replay=replay_constructive_stream(prefix_ws,prefix_doc,prefix_ops,expected_start_revision=1)
        if prefix_replay.revision!=revision:
            raise WorkspaceError("SEQUENCE_RECOVERY_REVISION","Prefix replay did not produce the completed step revision")
        prefix_aliases=prefix_replay.live_handles
        normalized=senior.normalized_state(projection_semantics(build_projection(prefix_ws,prefix_doc,revision)),prefix_aliases)
        expected_handles={row["function"]["portable_handle"] for row in self.sequence_contract["steps"][:step_index+1]}
        if {row["handle"] for row in normalized["functions"]}!=expected_handles:
            raise WorkspaceError("SEQUENCE_RECOVERY_FUNCTION_SET","Replay prefix has an unexpected function set")
        edge_set={(row["caller"],row["callee"]) for row in senior.candidate_call_edges(normalized)}
        expected_edge_set={(edge["caller_handle"],edge["callee_handle"])
            for row in self.sequence_contract["steps"][:step_index+1] for edge in row["required_dependency_edges"]}
        if edge_set!=expected_edge_set:
            raise WorkspaceError("SEQUENCE_RECOVERY_BINDING","Replay prefix dependency graph differs from sequence contract")
        expected=step["validation"]["expected_results"]
        observed=self._observe_sequence_results(revision,step["validation"]["inputs"],prefix_ws,prefix_doc,prefix_aliases)
        if observed!={engine:expected for engine in ("interp","jit")} or observed["interp"]!=observed["jit"]:
            raise WorkspaceError("SEQUENCE_RECOVERY_ORACLE",f"Replayed revision {revision} differs from its independent sequence oracle")

    def _observe_sequence_results(self,revision,inputs,workspace=None,document_id=None,aliases=None):
        workspace=workspace or self.ws; document_id=document_id or self.doc; aliases=aliases or self.aliases
        executor=MirExecutionService(timeout=15); functions={fn["symbol_id"] for fn in workspace.documents[document_id].functions}
        result={engine:{} for engine in ("interp","jit")}
        for engine in result:
            for value in inputs:
                row={}
                for handle,symbol_id in aliases.items():
                    if handle.endswith(".function") and symbol_id in functions:
                        row[workspace.documents[document_id].symbols[symbol_id].name.casefold()]=executor.execute_function(
                            workspace,document_id,revision,symbol_id,[value],engine)["result"]
                result[engine][str(value)]=row
        return result

    def _init_from_verified_stream(self,creation_contract_path,seed_contract_path,stream_path,history_path,validation_path):
        """Start a creation mission on a fresh replay of an authenticated stream."""
        paths=(seed_contract_path,stream_path,history_path,validation_path)
        if any(path is None or not Path(path).is_file() for path in paths):
            raise WorkspaceError("BASELINE_EVIDENCE_MISSING","Creation mission requires the seed contract, stream, history, and host validation")
        mission=json.loads(Path(creation_contract_path).read_text(encoding="utf-8"))
        if mission.get("schema")!="basic-workspace.numeric-function-creation-contract" or mission.get("version")!=1:
            raise WorkspaceError("MISSION_CONTRACT_VERSION","Unsupported numeric function creation contract")
        required={"schema","version","mission_id","objective","base_document_revision","execution_profile_id",
            "function","required_callees","required_dependency_edges","unchanged_function_handles","validation"}
        if set(mission)!=required or not isinstance(mission.get("required_callees"),list) or not mission["required_callees"]:
            raise WorkspaceError("MISSION_CONTRACT_INVALID","Creation contract fields or dependency set are invalid")
        if mission["execution_profile_id"]!=PROFILE_ID:
            raise WorkspaceError("BASELINE_PROFILE_MISMATCH","Creation contract uses another execution profile")
        from cycle20_gateway import Cycle20Gateway
        seed=Cycle20Gateway(self.output/"baseline-reconstruction",contract_path=Path(seed_contract_path),
            baseline_stream_path=Path(stream_path),baseline_history_path=Path(history_path),
            baseline_validation_path=Path(validation_path))
        if seed.base_revision!=mission["base_document_revision"]:
            raise WorkspaceError("BASELINE_REVISION_MISMATCH","Verified stream revision does not match the creation contract")
        self.ws=seed.ws; self.doc=seed.doc; self.aliases=dict(seed.aliases)
        self.transactions=SemanticTransactionKernel(self.ws,self.doc)
        self.output.mkdir(parents=True,exist_ok=True)
        self.trace=age.Trace(); self.lock=threading.RLock(); self.phase=3
        self.revision=self.ws.get_revision(self.doc); self.dispatched={}; self.pi_seen=set(); self.presentation_seq=0
        self.committed_operations=copy.deepcopy(seed.constructive_ops); self.completed_missions=[]
        self.last_validation=None; self.session_id=f"{mission['mission_id']}-agent-01"
        self.resume_verification={"passed":True,"revision":self.revision,"source":"verified_portable_constructive_stream"}
        fn=mission["function"]
        if set(fn)!={"name","handle","parameter","return_type"} or fn["return_type"]!="numeric":
            raise WorkspaceError("MISSION_CONTRACT_FUNCTION","Creation mission must describe one numeric function and parameter")
        if not isinstance(mission["required_callees"],list) or len(set(mission["required_callees"]))!=len(mission["required_callees"]):
            raise WorkspaceError("MISSION_CONTRACT_DEPENDENCIES","Required callees must be unique portable handles")
        self.current_contract={"mission_id":mission["mission_id"],"name":fn["name"],"handle":fn["handle"],
            "parameter":fn["parameter"],"return_type":fn["return_type"],"callee":None,
            "required_callees":list(mission["required_callees"]),"required_dependency_edges":mission["required_dependency_edges"],
            "objective":mission["objective"],"validation":mission["validation"]}
        self.mission_specs={3:self.current_contract}; self.mission_title=f"Mission · {fn['name']}"
        self.base_snapshot=copy.deepcopy(seed.baseline); self.base_aliases=dict(self.aliases)
        self.discovered=set(); self.committed=False
        self.visual_events=self.output/"visual-events.jsonl"; self.gateway_timings=self.output/"gateway-tool-timings.jsonl"
        self.pi_events=self.output/"pi-tool-lifecycle.jsonl"
        self.initial={"revision":self.revision,"code":self.code(),"dependencies":self._dependencies(self.base_snapshot)}
        profile=json.loads((ROOT/"results/semantic-replay/execution-profile.json").read_text())
        self.write_json("execution-profile.json",profile); self.write_json("MISSION-3.json",mission)
        baseline_report=json.loads((seed.output/"baseline-reconstruction.json").read_text())
        baseline_observed=self._run_functions(self.revision)
        baseline_expected_one=mission["validation"].get("baseline_expected_results")
        if baseline_expected_one is None:
            baseline_expected_one={str(x):{"clamp_score":float(min(50,max(0,x))),
                "is_passing":float(min(50,max(0,x))>=40)} for x in mission["validation"]["inputs"]}
        baseline_expected={engine:baseline_expected_one for engine in ("interp","jit")}
        baseline_ok=(baseline_observed==baseline_expected and baseline_observed["interp"]==baseline_observed["jit"])
        if not baseline_ok:
            raise WorkspaceError("BASELINE_BEHAVIOR_MISMATCH","Reconstructed Cycle 21 baseline does not match cap-50/threshold-40 MIR oracle")
        baseline_report.update({"behavior_oracle_passed":True,"baseline_observed_results":baseline_observed,
            "baseline_expected_results":baseline_expected,"baseline_expectation_source":"independent host-owned mission oracle"})
        self.write_json("baseline-behavior-verification.json",baseline_report)
        self.write_json("visual-source.json",{"schema":"basic-workspace.visual-source","version":1,
            "campaign":{"id":mission["mission_id"],"title":f"Semantic function creation · {fn['name']}","filename":"SCORES.bas"},
            "initial":self.initial,"snapshots":{str(self.revision):self.code()}})
        self.append_log(self.output/"setup.jsonl",{"kind":"verified_constructive_stream_reconstructed","revision":self.revision,
            "source_stream":str(stream_path),"function_names":[f["name"] for f in self.base_snapshot["functions"]],
            "host_replay":True,"recorded_validation_verified":True,"portable_handles":len(self.aliases)})
        self.emit_visual({"event_id":f"verified-baseline-{mission['mission_id']}","event_type":"initial","revision":self.revision,
            "session_id":self.session_id,"mission_id":self.mission_title,
            "provenance":"Host deterministic replay of the supplied authentic committed stream",
            "title":f"Verified semantic baseline · revision {self.revision}",
            "description":"The committed portable operation stream was reconstructed in an empty Workspace and checked against its saved semantic, binding, and MIR evidence.",
            "snapshot":self.code(),"dependencies":self._dependencies(self.base_snapshot),
            "focus":{"handles":["clamp_score.function","is_passing.function"],"mapping":"verified_function_boundary"}})

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
    def _mission_id(self):
        if self.current_contract is None and getattr(self,"sequence_mode",False):return self.sequence_contract["sequence_id"]
        return self.current_contract["mission_id"]
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
        edges={ (edge["caller"],edge["callee"]) for edge in senior.candidate_call_edges(norm) }
        return [{"caller":names.get(caller,caller),"callee":names.get(callee,callee)}
            for caller,callee in sorted(edges)]
    def mission_contract(self,phase:int,base_revision:int|None=None):
        spec=self.mission_specs[phase]
        if self.sequence_mode or phase==3:
            return {"schema":"basic-workspace.mission-contract","version":1,
                "mission_id":spec["mission_id"],"objective":spec["objective"],
                "execution_profile":PROFILE_ID,"base_document_revision":base_revision or self.ws.get_revision(self.doc),
                "allowed_operations":["create_numeric_function"],"allowed_function":{
                    "name":spec["name"],"parameters":[spec["parameter"]],"return_type":"numeric"},
                "required_discovered_dependencies":list(spec["required_callees"]),
                "required_dependency_edges":copy.deepcopy(spec["required_dependency_edges"]),
                "preserved_program_invariants":["every pre-existing function remains structurally unchanged",
                    "all required call targets must be discovered and bound", "exactly one function is added"],
                "required_validation":{"engines":["interp","jit"],"expected_outputs":"independent host-owned finite corpus"},
                "trust_boundary":"Enforced only through the controlled loopback MissionGateway."}
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
        if spec is None or getattr(self,"sequence_complete",False):
            raise WorkspaceError("SEQUENCE_COMPLETE","No function-creation step is active")
        if expected_revision!=now:raise WorkspaceError("STALE_REVISION",f"Expected revision {expected_revision}, current revision {now}")
        if self.committed:raise WorkspaceError("MISSION_EDIT_LIMIT","Mission permits exactly one function commit")
        if set(request)!={"name","parameters","body"}:raise WorkspaceError("MISSION_OPERATION_FORBIDDEN","Only typed create_numeric_function is allowed")
        if request["name"].casefold()!=spec["name"].casefold() or request["parameters"]!=[spec["parameter"]]:
            raise WorkspaceError("MISSION_SIGNATURE",f"Mission permits only {spec['name']}({spec['parameter']})")
        calls=list(self._calls(request["body"]))
        required_callees=list(spec.get("required_callees",[spec["callee"]] if spec.get("callee") else []))
        supplied_calls={call.get("function_handle") for call in calls}
        discovered_calls=set()
        if not required_callees:
            if calls or callee_handle not in (None,""):
                raise WorkspaceError("MISSION_DEPENDENCY_FORBIDDEN","This function must be self-contained")
        else:
            if not set(required_callees).issubset(self.discovered):
                raise WorkspaceError("FUNCTION_NOT_DISCOVERED","Discover every required function dependency before construction")
            if supplied_calls!=set(required_callees):
                raise WorkspaceError("MISSION_DEPENDENCY_REQUIRED","Calls must bind to every required discovered function and no others")
            if callee_handle is not None and (len(required_callees)!=1 or callee_handle!=required_callees[0]):
                raise WorkspaceError("MISSION_DEPENDENCY_FORBIDDEN","Top-level callee_handle is only valid for a single dependency")
            current_functions={row["symbol_id"] for row in self.ws.documents[self.doc].functions}
            state=self._normalized()
            for required in required_callees:
                if required not in self.aliases or self.aliases[required] not in current_functions:
                    raise WorkspaceError("UNKNOWN_FUNCTION_HANDLE",f"Required discovered handle {required} no longer resolves")
                callable_row=senior.find_function(state,required)
                if callable_row.get("return_type")!="numeric":
                    raise WorkspaceError("FUNCTION_SIGNATURE_MISMATCH",f"{required} must return numeric")
                function_symbol=self.ws.documents[self.doc].symbols.get(self.aliases[required])
                parameter_symbols=[self.ws.documents[self.doc].symbols.get(symbol_id)
                    for symbol_id in next(row for row in self.ws.documents[self.doc].functions
                        if row["symbol_id"]==self.aliases[required])["parameters"]]
                if (function_symbol is None or function_symbol.name.endswith("$") or
                        len(parameter_symbols)!=len(callable_row.get("parameters",[])) or
                        any(symbol is None or symbol.name.endswith("$") for symbol in parameter_symbols)):
                    raise WorkspaceError("FUNCTION_SIGNATURE_MISMATCH",f"{required} must have a compatible numeric signature")
                for call in calls:
                    if call.get("function_handle")==required:
                        args=call.get("arguments")
                        if not isinstance(args,list) or len(args)!=len(callable_row.get("parameters",[])):
                            raise WorkspaceError("FUNCTION_SIGNATURE_MISMATCH",f"Call argument count does not match {required}")
            discovered_calls=set(required_callees)
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
        bound_calls={row.get("value") for row in call_refs}
        if bound_calls!=set(required_callees):
            raise WorkspaceError("MISSION_DEPENDENCY_REQUIRED","Candidate call bindings do not match the authorized dependency set")
        expected_edges=spec.get("required_dependency_edges")
        if expected_edges is not None:
            actual_edges={(edge["caller"],edge["callee"]) for edge in senior.candidate_call_edges(normalized)
                if edge["caller"]==spec["handle"]}
            expected_edge_set={(edge["caller"],edge["callee"]) for edge in expected_edges}
            if actual_edges!=expected_edge_set:
                raise WorkspaceError("MISSION_DEPENDENCY_REQUIRED","Candidate must bind exactly the authorized dependency edges")
        return operation,normalized,candidate_aliases

    def _program_fingerprint(self,normalized):
        payload=json.dumps({"profile":PROFILE_ID,"revision":self.ws.get_revision(self.doc),"semantics":normalized},
            sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
        import hashlib
        return hashlib.sha256(payload).hexdigest()
    def _resume_from_cycle19(self,source_dir:Path):
        """Rebuild revision 2 from the exact committed operation and verify its checkpoint."""
        source_dir=source_dir.resolve()
        stream=json.loads((source_dir/"mission-1-constructive-operations-partial.json").read_text(encoding="utf-8"))
        checkpoint=json.loads((source_dir/"checkpoint.json").read_text(encoding="utf-8"))
        prior_validation=json.loads((source_dir/"mission-1-host-validation.json").read_text(encoding="utf-8"))
        prior_trace=[json.loads(line) for line in (source_dir/"history.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        source_bundle=json.loads((source_dir/"visual-source.json").read_text(encoding="utf-8"))
        source_events=[json.loads(line) for line in (source_dir/"visual-events.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        if stream.get("schema")!="basic-workspace.constructive-metafile" or stream.get("version")!=1:
            raise WorkspaceError("RESUME_STREAM_SCHEMA","Unsupported original Mission 1 operation stream")
        if stream.get("execution_profile_id")!=PROFILE_ID or checkpoint.get("execution_profile_id")!=PROFILE_ID:
            raise WorkspaceError("RESUME_PROFILE_MISMATCH","Original operation and checkpoint must use the current execution profile")
        operations=stream.get("operations")
        if not isinstance(operations,list) or len(operations)!=1:
            raise WorkspaceError("RESUME_OPERATION_COUNT","Mission 1 recovery requires exactly its one committed construction operation")
        item=operations[0]
        if item.get("operation")!="create_numeric_function" or item.get("portable_handle")!="clamp_score.function":
            raise WorkspaceError("RESUME_OPERATION_MISMATCH","The original committed CLAMP_SCORE operation is required")
        commit_events=[row for row in prior_trace if row.get("event")=="transaction_committed"
                       and row.get("mission_id")=="cycle19.normalize-score.v1"]
        proposal_events=[row for row in prior_trace if row.get("event")=="operation_proposed"
                         and row.get("mission_id")=="cycle19.normalize-score.v1"]
        if len(commit_events)!=1 or len(proposal_events)!=1:
            raise WorkspaceError("RESUME_HISTORY_INCOMPLETE","Original mission must have one proposal and one authoritative commit")
        committed=commit_events[0]
        if item.get("arguments")!=proposal_events[0].get("arguments"):
            raise WorkspaceError("RESUME_STREAM_MISMATCH","Portable operation differs from the genuine committed proposal")
        if committed.get("resulting_revision")!=2 or committed.get("portable_handle")!="clamp_score.function":
            raise WorkspaceError("RESUME_COMMIT_MISMATCH","Original commit evidence does not identify CLAMP_SCORE at revision 2")
        if prior_validation.get("mission_complete") is not True or prior_validation.get("revision")!=2:
            raise WorkspaceError("RESUME_VALIDATION_MISSING","Original Mission 1 host validation did not pass at revision 2")
        if checkpoint.get("revision")!=2 or not isinstance(checkpoint.get("semantic_fingerprint"),str):
            raise WorkspaceError("RESUME_CHECKPOINT_REVISION","Recovery checkpoint is not bound to revision 2")
        old_entities=committed.get("created_entities",[])
        old_function=next((row.get("symbol_id") for row in old_entities if row.get("kind")=="function" and row.get("name")=="CLAMP_SCORE"),None)
        old_parameter=next((row.get("symbol_id") for row in old_entities if row.get("kind")=="parameter" and row.get("name")=="X"),None)
        old_statements=[row.get("statement_id") for row in committed.get("created_statements",[])]
        if not old_function or not old_parameter or len(old_statements)!=4 or any(not sid for sid in old_statements):
            raise WorkspaceError("RESUME_IDENTITY_PROVENANCE","Original commit lacks the semantic identity provenance required for remapping")

        # Apply the exact portable semantic operation to this new empty document.
        args=senior.resolve_function_handles(item["arguments"],self.aliases,set())
        applied=self.ws.apply_transaction(self.doc,1,[{"operation":"create_numeric_function",**args}])
        if applied.get("revision")!=2:
            raise WorkspaceError("RESUME_REVISION_MISMATCH","Reconstruction did not produce revision 2")
        raw=projection_semantics(build_projection(self.ws,self.doc,2))
        self.aliases=senior.aliases_for_new_function(raw,{},"CLAMP_SCORE","clamp_score.function")
        normalized=senior.normalized_state(raw,self.aliases)
        if normalized!=committed.get("semantic_snapshot"):
            raise WorkspaceError("RESUME_SEMANTIC_MISMATCH","Reconstructed normalized semantics differ from the original committed snapshot")
        fingerprint=self._program_fingerprint(normalized)
        if fingerprint!=checkpoint.get("semantic_fingerprint"):
            raise WorkspaceError("RESUME_FINGERPRINT_MISMATCH","Reconstructed definition does not match the original checkpoint fingerprint")
        checkpoint_fn=(checkpoint.get("workspace_facts") or {}).get("functions")
        expected_fn=[{"handle":"clamp_score.function","name":"CLAMP_SCORE","parameters":["clamp_score.parameter.id"],"return_type":"numeric"}]
        if checkpoint_fn!=expected_fn:
            raise WorkspaceError("RESUME_CHECKPOINT_FACTS","Checkpoint callable signature facts do not match reconstructed program")
        observed=self._run_functions(2)
        prior_results=checkpoint["workspace_facts"].get("validated_results")
        if observed!=prior_results or observed!=prior_validation.get("observed_results"):
            raise WorkspaceError("RESUME_BEHAVIOR_MISMATCH","Reconstructed MIR results differ from recorded independent validation")
        if observed["interp"]!=observed["jit"]:
            raise WorkspaceError("RESUME_ENGINE_MISMATCH","Reconstructed interpreter and JIT results disagree")
        original_ids={"clamp_score.function":old_function,"clamp_score.parameter.id":old_parameter,
            **{f"clamp_score.statement.{i}":sid for i,sid in enumerate(old_statements)}}
        identity_mapping=[{"portable_handle":handle,"original_workspace_id":original_ids[handle],
            "reconstructed_workspace_id":self.aliases[handle],"remapped":original_ids[handle]!=self.aliases[handle]}
            for handle in sorted(self.aliases)]

        self.revision=2; self.base_snapshot=normalized; self.base_aliases=dict(self.aliases)
        self.phase=2; self.current_contract=self.mission_specs[2]; self.mission_title="Mission 2 · IS_PASSING"
        self.session_id="cycle19b-mission-2"; self.discovered=set(); self.transactions.clear(); self.committed=False
        self.last_validation=None; self.committed_operations=[item]
        self.write_json("checkpoint.json",checkpoint)
        self.write_json("reconstruction-verification.json",{"schema":"basic-workspace.cycle19b-reconstruction","version":1,
            "source_campaign":"Cycle 19 genuine Mission 1","source_operation":"mission-1-constructive-operations-partial.json",
            "starting_document_empty":True,"replay_actor":"host_deterministic_replay","resulting_revision":2,
            "normalized_semantics_match_original_commit":True,"checkpoint_fingerprint_match":True,
            "semantic_fingerprint":fingerprint,"checkpoint_document_id_reused":False,
            "checkpoint_profile_match":True,"interpreter_jit_agree":True,"recorded_behavior_matches":True,
            "observed_results":observed,
            "identity_mapping":identity_mapping,
            "new_workspace_handles":sorted(self.aliases),"portable_identity_count":len(self.aliases),
            "identity_remappings":len(self.aliases),"passed":True})
        # Reuse the original campaign's source snapshots and events, then append
        # a clearly host-labelled reconstruction and fresh-session boundary.
        original_code=next((row.get("snapshot") for row in source_events if row.get("event_type")=="commit" and row.get("revision")==2),None)
        current_code=self.code()
        if original_code is None or original_code!=current_code:
            raise WorkspaceError("RESUME_SOURCE_MISMATCH","Reconstructed rendering does not match the original committed snapshot")
        self.initial=source_bundle["initial"]
        snapshots=dict(source_bundle.get("snapshots",{})); snapshots["2"]=current_code
        self.write_json("visual-source.json",{"schema":"basic-workspace.visual-source","version":1,
            "campaign":{"id":"cycle19b-recovery","title":"Cycle 19B · verified semantic recovery and continuation","filename":"SCORES.bas"},
            "initial":self.initial,"snapshots":snapshots})
        for event in source_events:
            self.append_log(self.visual_events,event)
            self.presentation_seq=max(self.presentation_seq,int(event.get("presentation_sequence",0)))
        self.trace.emit("replay_completed",phase="cycle19b-reconstruction",actor="host_deterministic_replay",
            mission_id=self.mission_specs[2]["mission_id"],revision=2,portable_operation_count=1,
            normalized_semantics_match=True,fingerprint_match=True,behavior_match=True)
        self.emit_visual({"event_id":"cycle19b-host-reconstruction","event_type":"reconstruction","revision":2,
            "snapshot":current_code,"session_id":self.session_id,"mission_id":self.mission_title,
            "provenance":"Host deterministic replay of the original genuine Mission 1 committed operation",
            "title":"Revision 2 reconstructed from semantic operation","description":"The original CLAMP_SCORE operation was replayed into a new empty Workspace; checkpoint fingerprint, normalized semantics, interpreter and JIT results all match.",
            "focus":{"handles":["clamp_score.function"],"mapping":"verified_function_boundary",
                "spans":{"function_lines":self._function_span(self.aliases["clamp_score.function"])["spans"]["function_lines"]}},
            "dependencies":self._dependencies(),"outcome":{"committed":True,"workspace_revision":2,"model_activity":False}})
        self.emit_visual({"event_id":"cycle19b-checkpoint-verified","event_type":"checkpoint","revision":2,
            "session_id":self.session_id,"mission_id":self.mission_title,
            "provenance":"Host validation of revision-bound recovery checkpoint","title":"Verified checkpoint · fresh Pi context",
            "description":"The checkpoint matches the reconstructed definition and recorded MIR observations. The new Pi conversation receives portable facts without prior transcripts or opaque document IDs.",
            "focus":{"handles":["clamp_score.function"],"mapping":"verified_function_boundary",
                "spans":{"function_lines":self._function_span(self.aliases["clamp_score.function"])["spans"]["function_lines"]}},
            "outcome":{"revision":2,"semantic_fingerprint":fingerprint},"dependencies":self._dependencies()})
        self.emit_visual({"event_id":"cycle19b-context-reset","event_type":"context_reset","revision":2,
            "session_id":self.session_id,"mission_id":self.mission_title,
            "provenance":"Host starts a fresh Pi conversation after deterministic reconstruction","title":"Fresh agent session · Mission 2",
            "description":"Mission 2 starts from reconstructed revision 2. The earlier Cycle 19 Mission 2 transcript is not included.",
            "focus":{"handles":["clamp_score.function"],"mapping":"verified_function_boundary"},
            "dependencies":self._dependencies()})
        self.append_log(self.output/"setup.jsonl",{"kind":"cycle19b_mission1_reconstructed_and_checkpoint_verified",
            "revision":2,"semantic_fingerprint":fingerprint,"source_campaign":"Cycle 19 real-agent-01",
            "source_visual_events":len(source_events),"fresh_model_conversation":True})
        self.write_json("MISSION-2.json",self.mission_contract(2,base_revision=2))
        self.write_json("mission-2-baseline.json",{"revision":2,"normalized_program":normalized,
            "semantic_fingerprint":fingerprint,"captured_after_verified_reconstruction":True})
        self.flush_trace()
        self.resume_verification={"passed":True,"revision":2,"semantic_fingerprint":fingerprint,
            "normalized_semantics_match_original_commit":True,"mir_results_match_checkpoint":True,
            "interpreter_jit_agree":True,"portable_identity_count":len(self.aliases)}
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
        self.base_snapshot=normalized; self.base_aliases=dict(self.aliases); self.discovered=set(); self.transactions.clear(); self.committed=False
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
        if getattr(self,"sequence_mode",False):
            if (self.sequence_complete or not self.committed or not self.last_validation or self.last_validation.get("actor")!="host"
                    or not self.last_validation.get("mission_complete")):
                return {"ok":False,"code":"SEQUENCE_STEP_NOT_VALIDATED","revision":self.ws.get_revision(self.doc)}
            checkpoint=self._sequence_checkpoint(); self.last_sequence_checkpoint=copy.deepcopy(checkpoint)
            index=self.sequence_cursor+1; self.write_json(f"checkpoint-step-{index:02d}.json",checkpoint)
            self.append_log(self.output/"creation-sequence-history.jsonl",{"event":"checkpoint_created",
                "step_id":self.current_step["step_id"],"mission_id":self.current_step["mission_id"],
                "revision":checkpoint["revision"],"semantic_fingerprint":checkpoint["semantic_fingerprint"],
                "portable_handle_count":len(checkpoint["portable_handles"])})
            return {"ok":True,"checkpoint":checkpoint}
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
        functions={fn["symbol_id"] for fn in self.ws.documents[self.doc].functions}
        inputs=(self.current_contract.get("validation",{}).get("inputs",INPUTS)
            if self.phase>=3 else INPUTS)
        for engine in ("interp","jit"):
            for value in inputs:
                row={}
                for handle,symbol_id in self.aliases.items():
                    if not handle.endswith(".function") or symbol_id not in functions:continue
                    key=self.ws.documents[self.doc].symbols[symbol_id].name.casefold()
                    row[key]=executor.execute_function(self.ws,self.doc,revision,symbol_id,[value],engine)["result"]
                result[engine][str(value)]=row
        return result
    @staticmethod
    def _expected():
        return {str(x):{"clamp_score":float(min(100,max(0,x))),"is_passing":1.0 if min(100,max(0,x))>=60 else 0.0} for x in INPUTS}
    def _replay(self):
        stream={"schema":"basic-workspace.constructive-metafile","version":1,"execution_profile_id":PROFILE_ID,
            "portable_handles":sorted(self.aliases.keys()),"operations":self.committed_operations}
        ws=Workspace();doc=ws.create_empty_document("memory://cycle19/replay.bas")["document_id"]
        replay=replay_constructive_stream(ws,doc,stream["operations"],expected_final_handles=stream["portable_handles"],
            expected_start_revision=1)
        aliases=replay.live_handles;revision=replay.revision
        norm=senior.normalized_state(projection_semantics(build_projection(ws,doc,revision)),aliases)
        executor=MirExecutionService(timeout=15);obs={engine:{} for engine in ("interp","jit")}
        inputs=((self.current_contract or {"validation":self.sequence_contract["steps"][-1]["validation"]})
            .get("validation",{}).get("inputs",INPUTS) if self.phase>=3 else INPUTS)
        for engine in obs:
            for x in inputs:
                row={}
                for function in norm["functions"]:
                    handle=function["handle"];symbol_id=aliases.get(handle)
                    if symbol_id is None:raise WorkspaceError("REPLAY_HANDLE_MISSING",f"Function handle {handle} did not resolve")
                    row[function["name"].casefold()]=executor.execute_function(ws,doc,revision,symbol_id,[x],engine)["result"]
                obs[engine][str(x)]=row
        remapped=sum(self.aliases.get(h)!=aliases.get(h) for h in self.aliases)
        identity_mapping=[{"portable_handle":handle,"committed_workspace_id":self.aliases[handle],
            "replay_workspace_id":aliases[handle],"remapped":self.aliases[handle]!=aliases[handle]}
            for handle in sorted(self.aliases)]
        return stream,norm,obs,remapped,identity_mapping

    def validate_current(self,requested_revision:int,actor="host"):
        revision=self.ws.get_revision(self.doc)
        if requested_revision!=revision:return {"reliable":False,"code":"STALE_VALIDATION_REVISION","mission_complete":False,
            "requested_revision":requested_revision,"workspace_revision":revision,"executed_revision":None}
        if getattr(self,"sequence_complete",False) and self.last_validation:
            return copy.deepcopy(self.last_validation)
        if not self.committed:return {"reliable":True,"mission_complete":False,"phase":"pre-create","executed_revision":revision,
            "diagnostics":[f"{self.current_contract['name']} is not committed"]}
        if self.phase>=3:
            observed=self._run_functions(revision)
            expected_one=self.current_contract["validation"]["expected_results"]
            expected={engine:expected_one for engine in ("interp","jit")}
            values_match=observed==expected
            engines_agree=observed["interp"]==observed["jit"]
            norm=self._normalized()
            unchanged=all(senior.find_function(self.base_snapshot,row["handle"])==
                senior.find_function(norm,row["handle"]) for row in self.base_snapshot["functions"])
            actual_edge_set={(e["caller"],e["callee"]) for e in senior.candidate_call_edges(norm)}
            expected_edge_set={(e["caller"],e["callee"]) for e in senior.candidate_call_edges(self.base_snapshot)+
                self.current_contract["required_dependency_edges"]}
            actual_edges=[{"caller":a,"callee":b} for a,b in sorted(actual_edge_set)]
            expected_edges=[{"caller":a,"callee":b} for a,b in sorted(expected_edge_set)]
            dependency_ok=actual_edges==expected_edges
            added=senior.find_function(norm,self.current_contract["handle"])
            signature_ok=(added["name"]==self.current_contract["name"] and
                added["parameters"]==[f"{self.current_contract['handle'].rsplit('.',1)[0]}.parameter.id"] and
                added["return_type"]=="numeric")
            stream,replay_norm,replay_obs,remapped,identity_mapping=self._replay()
            replay_structural=norm==replay_norm
            replay_behavioral=observed==replay_obs
            replay_binding={(edge["caller"],edge["callee"]) for edge in senior.candidate_call_edges(replay_norm)}==expected_edge_set
            replay_ok=replay_structural and replay_behavioral and replay_binding and replay_obs["interp"]==replay_obs["jit"]
            complete=bool(values_match and engines_agree and unchanged and dependency_ok and signature_ok and replay_ok)
            result={"schema":"basic-workspace.creation-sequence-validation" if self.sequence_mode else "basic-workspace.cycle24-creation-validation","version":1,
                "mission_id":self._mission_id(),"actor":actor,"reliable":True,"revision":revision,
                "requested_revision":requested_revision,"executed_revision":revision,
                "observed_results":observed,"expected_results":expected,
                "expectation_source":"independent host-owned creation-sequence finite oracle" if self.sequence_mode else "independent host-owned Cycle 24 finite oracle",
                "values_match":values_match,"engines_agree":engines_agree,
                "existing_functions_unchanged":unchanged,"dependency_edges":actual_edges,
                "required_dependency_edges":expected_edges,"dependencies_match":dependency_ok,
                "new_function_signature_valid":signature_ok,"mission_complete":complete,
                "replay":{"structural_equivalence":replay_structural,"binding_equivalence":replay_binding,
                    "behavioral_equivalence":replay_behavioral,"engine_agreement":replay_obs["interp"]==replay_obs["jit"],
                    "identity_remappings":remapped,"identity_mapping":identity_mapping,"passed":replay_ok},
                "diagnostics":[] if complete else ["Function behavior, dependency, preservation, or replay invariant failed"]}
            if complete:
                self.write_json("constructive-operations.json",stream)
                self.write_json("equivalence.json",result)
            self.write_json(f"mission-{self.phase}-validation-{actor}.json",result)
            self.append_log(self.output/"validation.jsonl",result)
            self.trace.emit("program_validated",phase=f"creation-step-{self.sequence_cursor+1}" if self.sequence_mode else "mission-3",actor=actor,mission_id=self._mission_id(),
                revision=revision,executed_revision=revision,passed=complete,engines_agree=engines_agree,
                replay_passed=replay_ok,dependencies_match=dependency_ok)
            self.emit_visual({"event_id":f"cycle24-validation-{actor}-{revision}","event_type":"validation",
                "revision":revision,"session_id":self.session_id,"mission_id":self.mission_title,
                "provenance":"Independent host MIR interpreter/JIT and portable replay oracle" if actor=="host" else "Pi-requested mission validator",
                "title":f"{actor.title()} validation {'passed' if complete else 'failed'} · revision {revision}",
                "description":"Finite host-owned behavior, dependency edges, unchanged definitions, and empty-workspace replay were checked.",
                "validation":{"passed":complete,"engines_agree":engines_agree,"replay_passed":replay_ok},
                "observation":{"function":self.current_contract["name"],"arguments":self.current_contract["validation"]["inputs"],
                    "engine_results":observed,"revision":revision,"agreement":engines_agree},
                "dependencies":self._dependencies(norm)})
            self.flush_trace(); self.last_validation=result
            return result
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
        stream,replay_norm,replay_obs,remapped,identity_mapping=self._replay()
        replay_ok=(norm==replay_norm and observed==replay_obs and replay_obs["interp"]==replay_obs["jit"])
        result["replay"]={"structural_equivalence":norm==replay_norm,"behavioral_equivalence":observed==replay_obs,
            "engine_agreement":replay_obs["interp"]==replay_obs["jit"],"identity_remappings":remapped,
            "identity_mapping":identity_mapping,"passed":replay_ok}
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
        if getattr(self,"sequence_complete",False) or self.current_contract is None:
            return {"ok":False,"reliable":True,"code":"SEQUENCE_COMPLETE","revision":self.ws.get_revision(self.doc),
                "revision_unchanged":True,"authoritative_workspace_changed":False}
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
        txid,preview=self.transactions.preview(operation_kind="create_numeric_function",
            base_revision=p["expected_revision"],operations=[operation],candidate=candidate,
            metadata={"request":request,"candidate_aliases":candidate_aliases,"callee_handle":effective_callee})
        self.dispatched[txid]=rid
        self.trace.emit("operation_proposed",phase=f"mission-{self.phase}",actor="pi_model_tool",mission_id=self._mission_id(),
            transaction_id=txid,base_revision=revision,operation="create_numeric_function",arguments=request)
        self.trace.emit("preview_accepted",phase=f"mission-{self.phase}",actor="mission_gateway",mission_id=self._mission_id(),
            transaction_id=txid,base_revision=revision,resulting_revision=preview["expected_result_revision"],
            portable_handle=self.current_contract["handle"],bound_callee=effective_callee,candidate=candidate)
        additions=[line[1:] for line in preview.get("diff","").splitlines() if line.startswith("+") and not line.startswith("+++")]
        focus={"handles":[self.current_contract["handle"]],"mapping":"verified_function_boundary"}
        if self.current_contract.get("required_callees"):
            focus["call_targets"]=list(self.current_contract["required_callees"])
        elif self.current_contract.get("callee"):
            focus["call_target"]=self.current_contract["callee"]
        self.emit_visual({"event_id":f"cycle19-preview-{rid}","event_type":"preview","revision":revision,
            "session_id":self.session_id,"mission_id":self.mission_title,"provenance":"Genuine Pi typed proposal · accepted MissionContract preview",
            "source_event_ref":rid,"title":f"{self.current_contract['name']} proposal","description":"Candidate accepted; committed BASIC remains unchanged until atomic commit.",
            "focus":focus,"preview":{"status":"accepted","append_lines":additions,"function":self.current_contract["name"],
                "bound_callee":effective_callee,"bound_callees":list(self.current_contract.get("required_callees",[]))},
            "outcome":{"authorized":True,"committed":False}})
        self.flush_trace()
        return {"ok":True,"transaction_id":txid,"base_revision":revision,"expected_result_revision":revision+1,
            "portable_handle":self.current_contract["handle"],"bound_callee_handle":effective_callee,
            "bound_callee_handles":list(self.current_contract.get("required_callees",[])),
            "diagnostics":preview["diagnostics"],"candidate_is_preview_only":True}
    def _commit(self,p,rid):
        txid=p.get("transaction_id"); current=self.ws.get_revision(self.doc)
        pending=self.transactions.get(txid) if isinstance(txid,str) else None
        if pending is None:return {"ok":False,"committed":False,"code":"PREVIEW_NOT_FOUND","revision":current,"authoritative_workspace_changed":False}
        try:
            def revalidate(record,base_revision):
                meta=record["metadata"]
                op,candidate,candidate_aliases=self._candidate(meta["request"],base_revision,meta["callee_handle"])
                if candidate_aliases.keys()!=meta["candidate_aliases"].keys():
                    raise WorkspaceError("PREVIEW_BINDINGS_CHANGED","Candidate symbol bindings changed since preview")
                return [op],candidate,{"candidate_aliases":candidate_aliases}
            receipt=self.transactions.commit(txid,revalidate)
            applied=receipt.applied; candidate=receipt.candidate
            pending={**receipt.metadata,"request":pending["metadata"]["request"],
                "callee_handle":pending["metadata"]["callee_handle"]}
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
            portable_handle=self.current_contract["handle"],bound_callee=self.current_contract.get("callee"),
            bound_callees=list(self.current_contract.get("required_callees",[])),
            semantic_snapshot=norm,created_entities=applied["created_entities"],created_statements=applied["created_statements"])
        self.emit_visual({"event_id":f"cycle19-commit-{self.phase}-{txid}","event_type":"commit","revision":self.revision,"snapshot":source,
            "session_id":self.session_id,"mission_id":self.mission_title,"provenance":"Workspace atomic transaction · genuine Pi commit request",
            "source_event_ref":self.dispatched.get(txid,rid),"title":f"{self.current_contract['name']} committed",
            "description":f"Committed at revision {self.revision}; dependencies: {', '.join(self.current_contract.get('required_callees', [])) or 'none'}.",
            "focus":{"handles":[self.current_contract["handle"]]+list(self.current_contract.get("required_callees",[])),**span},
            "dependencies":self._dependencies(norm),"outcome":{"committed":True,"transaction_id":txid,
                "bound_callees":list(self.current_contract.get("required_callees",[]))}})
        self.flush_trace()
        return {"ok":True,"committed":True,"revision":self.revision,"portable_handle":self.current_contract["handle"],
            "bound_callee_handle":self.current_contract.get("callee"),
            "bound_callee_handles":list(self.current_contract.get("required_callees",[])),"created_entities":applied["created_entities"]}

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
        params=request.get("params") or {}; transport=request.get("transport") or {}; method=request.get("method")
        self.append_log(self.gateway_timings,{"request_id":request.get("request_id"),"tool_call_id":transport.get("tool_call_id"),
            "method":method,"mission_id":self._mission_id(),"phase":self.phase,"elapsed_ms":round(elapsed_ms,3),
            "agent_tool":method in {"discover_functions","inspect_program","preview_create_function","commit_preview","validate_mission"}})
    def flush_trace(self):self.trace.write(self.output/"history.jsonl")
    def handle(self,method,p,rid):
        if method=="record_pi_event":return self.record_pi(p)
        if method=="record_agent_status":
            self._record_status(str(p.get("state","unknown")),p.get("info") if isinstance(p.get("info"),dict) else {})
            return {"ok":True,"revision":self.ws.get_revision(self.doc)}
        if method=="get_status":
            status={"revision":self.ws.get_revision(self.doc),"phase":self.phase,
                "mission_id":self._mission_id(),"document_id":self.doc,"function_handles":self._function_handles(),
                "committed":self.committed,"resume_verification":self.resume_verification}
            if getattr(self,"sequence_mode",False):
                status.update({"sequence_id":self.sequence_contract["sequence_id"],
                    "sequence_step_index":self.sequence_cursor,"sequence_step_count":len(self.sequence_contract["steps"]),
                    "active_step_id":self.current_step["step_id"] if self.current_step else None,
                    "sequence_complete":self.sequence_complete})
            return status
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
        if method=="host_advance_creation_sequence":return self._advance_creation_sequence(p.get("checkpoint",{}))
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
    ap=argparse.ArgumentParser();ap.add_argument("--output",type=Path,required=True);ap.add_argument("--port",type=int,default=0)
    ap.add_argument("--resume-from",type=Path)
    ap.add_argument("--creation-contract",type=Path);ap.add_argument("--seed-contract",type=Path)
    ap.add_argument("--baseline-stream",type=Path);ap.add_argument("--baseline-history",type=Path)
    ap.add_argument("--baseline-validation",type=Path)
    ap.add_argument("--creation-sequence",type=Path);ap.add_argument("--sequence-stream",type=Path)
    ap.add_argument("--sequence-checkpoint",type=Path);a=ap.parse_args()
    service=Cycle19Gateway(a.output,a.resume_from,creation_contract_path=a.creation_contract,
        seed_contract_path=a.seed_contract,baseline_stream_path=a.baseline_stream,
        baseline_history_path=a.baseline_history,baseline_validation_path=a.baseline_validation,
        creation_sequence_path=a.creation_sequence,sequence_stream_path=a.sequence_stream,
        sequence_checkpoint_path=a.sequence_checkpoint)
    with Server(("127.0.0.1",a.port),service) as server:
        print(json.dumps({"ready":True,"host":"127.0.0.1","port":server.server_address[1],"revision":service.revision,
            "phase":service.phase,"resume_verification":service.resume_verification},separators=(",",":")),flush=True)
        server.serve_forever()
if __name__=="__main__":main()
