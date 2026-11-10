#!/usr/bin/env python3
"""No-inference Cycle35 sequence validation through production TypeScript/JSONL tools."""
from __future__ import annotations
import argparse, json, os, pathlib, subprocess, sys, time
HERE=pathlib.Path(__file__).resolve().parent
ROOT=HERE.parent
sys.path.insert(0,str(HERE))
from run_cycle16 import gateway_call
ATOMIC_TOOLS={"workspace_discover_functions","workspace_inspect_program","workspace_preview_function",
    "workspace_commit_preview","workspace_validate_mission"}

def read(path):return json.loads(path.read_text(encoding="utf-8"))
def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
def fn_request(name):
    ref=lambda:{"kind":"local_ref","name":"X"}; number=lambda value:{"kind":"number","value":value}
    assign=lambda expr:{"kind":"assign","target":{"kind":"result"},"expression":expr}
    binary=lambda op,left,right:{"kind":"binary","operator":op,"left":left,"right":right}
    call=lambda handle:{"kind":"call","function_handle":handle,"arguments":[ref()]}
    branch=lambda cond,value:{"kind":"if","condition":cond,"then":[assign(number(value))]}
    if name=="BOUNDED_SCORE":body=[assign(ref()),branch(binary("<",ref(),number(0)),0),branch(binary(">",ref(),number(100)),100)]
    elif name in {"IS_PASSING","IS_EXCELLENT"}:
        threshold=60 if name=="IS_PASSING" else 90
        body=[assign(number(0)),branch(binary(">=",call("bounded_score.function"),number(threshold)),1)]
    elif name=="HIGH_PRIORITY":body=[assign(number(0)),branch(binary(">=",call("is_excellent.function"),number(1)),1)]
    elif name=="HAS_CREDIT":body=[assign(number(0)),branch(binary(">=",ref(),number(0)),1)]
    elif name=="IS_MINOR":body=[assign(number(0)),branch(binary("<",ref(),number(18)),1)]
    elif name=="CAN_APPLY":body=[assign(number(0)),branch(binary(">=",call("has_credit.function"),number(1)),1),
        branch(binary(">=",call("is_minor.function"),number(1)),0)]
    elif name=="APPROVAL_FLAG":body=[assign(number(0)),branch(binary(">=",call("can_apply.function"),number(1)),1)]
    else:raise ValueError(name)
    return {"name":name,"parameters":["X"],"body":body}
def oracle(sequence_id,x):
    if sequence_id=="cycle35.score-evaluation.v1":
        bounded=min(100,max(0,x)); excellent=int(bounded>=90)
        return {"bounded_score":float(bounded),"is_passing":float(bounded>=60),
            "is_excellent":float(excellent),"high_priority":float(excellent)}
    credit=int(x>=0); minor=int(x<18); can_apply=int(credit and not minor)
    return {"has_credit":float(credit),"is_minor":float(minor),"can_apply":float(can_apply),"approval_flag":float(can_apply)}
def stop(proc):
    if proc and proc.poll() is None:
        proc.terminate()
        try:proc.wait(timeout=5)
        except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=5)
def dispatch(ready,request,outdir):
    inp=outdir/"dispatch-input.json";result=outdir/"dispatch-output.json";write(inp,request)
    env=os.environ.copy();env.update({"BASIC_WS_AUTHORING_MODE":"atomic_create",
        "BASIC_WS_PI_GATEWAY":f"127.0.0.1:{ready['port']}","BASIC_WS_DISPATCH_PROBE_INPUT":str(inp),
        "BASIC_WS_DISPATCH_PROBE_OUTPUT":str(result),
        "NODE_PATH":"/usr/lib/node_modules/@earendil-works/pi-coding-agent/node_modules"})
    proc=subprocess.run(["bun",str(HERE/"cycle20b_dispatch_probe.ts")],env=env,capture_output=True,text=True,timeout=90)
    (outdir/"dispatch.stdout.log").write_text(proc.stdout,encoding="utf-8")
    (outdir/"dispatch.stderr.log").write_text(proc.stderr,encoding="utf-8")
    if proc.returncode or not result.is_file():raise RuntimeError(f"real extension/JSONL dispatch failed: {proc.stderr[-2000:]}")
    return read(result)
def run_mission(label,contract_path,out):
    arm=out/label;arm.mkdir(parents=True)
    evidence=arm/"gateway-evidence";error=(arm/"gateway.stderr.log").open("w",encoding="utf-8")
    env=os.environ.copy();env["PYTHONPATH"]=str(ROOT)+os.pathsep+str(HERE)+os.pathsep+env.get("PYTHONPATH","")
    gateway=subprocess.Popen([sys.executable,str(HERE/"cycle19_gateway.py"),"--output",str(evidence),"--port","0",
        "--creation-sequence",str(contract_path)],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=error,text=True,env=env)
    try:
        line=gateway.stdout.readline()
        if not line:raise RuntimeError(f"gateway failed to start: {error.name}")
        ready=json.loads(line);contract=read(contract_path)
        if not ready.get("ready") or ready.get("revision")!=1 or ready.get("phase")!=3:raise RuntimeError(f"bad sequence start: {ready}")
        premature=gateway_call("127.0.0.1",ready["port"],"host_advance_creation_sequence",{"checkpoint":{}})
        if premature.get("code")!="SEQUENCE_STEP_NOT_VALIDATED" or premature.get("progress_advanced"):
            raise RuntimeError(f"host progression advanced without a validated creation: {premature}")
        steps=[];observations={};schemas=None
        for index,step in enumerate(contract["steps"]):
            step_dir=arm/f"step-{index+1:02d}";step_dir.mkdir()
            name=step["function"]["name"];args={"expected_revision":step["expected_base_revision"],**fn_request(name)}
            unauthorized=dict(args);unauthorized["name"]="UNAUTHORIZED_FUNCTION"
            stale=dict(args);stale["expected_revision"]-=1
            controls=[unauthorized,stale]
            if step["required_callees"]:
                wrong_dependency=json.loads(json.dumps(args))
                def replace_first_call(value):
                    if isinstance(value,list):
                        for child in value:
                            if replace_first_call(child):return True
                    elif isinstance(value,dict):
                        if value.get("kind")=="call":value["function_handle"]="invented.function";return True
                        for child in value.values():
                            if replace_first_call(child):return True
                    return False
                if not replace_first_call(wrong_dependency["body"]):raise RuntimeError("contract expected a call but constructor fixture had none")
                controls.append(wrong_dependency)
            unknown_field=dict(args);unknown_field["unrecognized_semantic_field"]=True
            controls.append(unknown_field)
            probe=dispatch(ready,{"authoring_mode":"atomic_create","correlation_id":f"cycle35-{label}-{index}-{time.time_ns()}",
                "preview_args":args,"controls":controls,"commit":True},step_dir)
            if set(probe.get("active_tools",[]))!=ATOMIC_TOOLS or not probe.get("schema_ok"):
                raise RuntimeError(f"active tool inventory/schema mismatch at {label} step {index+1}")
            if schemas is None:schemas=probe.get("schemas")
            control_codes=[row.get("code") for row in probe.get("controls",[])]
            schema_reject_fields={key for row in probe.get("schema_rejections",[]) for key in row.get("arguments",{})}
            if control_codes[:2]!=["MISSION_SIGNATURE","STALE_REVISION"]:
                raise RuntimeError(f"unauthorized/stale requests did not fail at {label} step {index+1}: {control_codes}")
            if step["required_callees"] and control_codes[2]!="MISSION_DEPENDENCY_REQUIRED":
                raise RuntimeError(f"invented dependency did not fail at {label} step {index+1}: {control_codes}")
            if "unrecognized_semantic_field" not in schema_reject_fields:
                raise RuntimeError("TypeBox did not reject an unknown constructor field")
            if not probe.get("preview",{}).get("candidate_is_preview_only") or probe["preview"].get("base_revision")!=step["expected_base_revision"]:
                raise RuntimeError("preview mutated state or used an unexpected revision")
            committed=probe.get("committed") or {}
            expected_revision=step["expected_base_revision"]+1
            if not committed.get("committed") or committed.get("revision")!=expected_revision:
                raise RuntimeError(f"constructor did not commit exactly one revision: {committed}")
            validation=probe.get("validation") or {}
            host_validation=gateway_call("127.0.0.1",ready["port"],"host_validate",{"expected_revision":expected_revision})
            if not validation.get("mission_complete") or not host_validation.get("mission_complete"):
                raise RuntimeError(f"step validation failed: {validation.get('diagnostics')} / {host_validation.get('diagnostics')}")
            expected_names=set(next(iter(step["validation"]["expected_results"].values())))
            rows={str(x):{name:value for name,value in oracle(contract["sequence_id"],x).items() if name in expected_names}
                for x in step["validation"]["inputs"]}
            if rows!=step["validation"]["expected_results"]:raise RuntimeError("Independent arithmetic oracle differs from the frozen contract")
            for engine in ("interp","jit"):
                if host_validation["observed_results"][engine]!=rows:
                    raise RuntimeError(f"{label} {name} {engine} differs from independent oracle")
            checkpoint_result=gateway_call("127.0.0.1",ready["port"],"create_checkpoint",{})
            if not checkpoint_result.get("ok"):raise RuntimeError("validated step did not produce a checkpoint")
            checkpoint=checkpoint_result["checkpoint"]
            progression=gateway_call("127.0.0.1",ready["port"],"host_advance_creation_sequence",{"checkpoint":checkpoint})
            if not progression.get("ok"):raise RuntimeError(f"host progression failed: {progression}")
            step_observation={"revision":expected_revision,"expected":rows,
                "mir_interpreter":host_validation["observed_results"]["interp"],
                "mir_jit":host_validation["observed_results"]["jit"],
                "interpreter_jit_agree":host_validation["observed_results"]["interp"]==host_validation["observed_results"]["jit"],
                "mission_complete":host_validation["mission_complete"]}
            observations[str(expected_revision)]=step_observation
            steps.append({"step_id":step["step_id"],"mission_id":step["mission_id"],"revision":expected_revision,
                "function":name,"portable_handle":committed["portable_handle"],"bound_callees":committed["bound_callee_handles"],
                "active_tools":sorted(probe["active_tools"]),"schema_bytes_compact":len(json.dumps(probe["schemas"],separators=(",",":"),ensure_ascii=False).encode()),
                "preview_non_mutating":True,"unauthorized_name_rejected":probe["controls"][0]["code"],
                "rejected_control_codes":control_codes,"unknown_field_schema_rejected":True,
                "validation_passed":host_validation["mission_complete"],"checkpoint_fingerprint":checkpoint["semantic_fingerprint"],
                "progression":progression})
        state=gateway_call("127.0.0.1",ready["port"],"get_status",{})
        if not state.get("sequence_complete") or state["revision"]!=5:raise RuntimeError(f"sequence did not complete at revision 5: {state}")
        write(arm/"oracle-observations.json",{"sequence_id":contract["sequence_id"],"independent_reference":"cycle35_preflight.oracle",
            "inputs":contract["steps"][-1]["validation"]["inputs"],"revisions":observations})
        summary={"sequence_id":contract["sequence_id"],"inference_performed":False,"final_revision":state["revision"],
            "function_count":len(state["function_handles"]),"steps":steps,"completed":state["sequence_complete"],
            "premature_progression_rejected":premature["code"],
            "active_tool_schemas":schemas,"production_bridge":"cycle20b_dispatch_probe.ts -> actual extension.ts tool handlers -> JSONL -> Cycle19Gateway",
            "trusted_progression":"host-only JSONL method; not in Pi active tool inventory"}
        write(arm/"bridge-summary.json",summary)
        return summary
    finally:
        stop(gateway);error.close()
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument("--output",type=pathlib.Path,default=HERE/"results/cycle35-sequential-creation/production-bridge")
    args=ap.parse_args();out=args.output.resolve()
    if out.exists() and any(out.iterdir()):raise SystemExit(f"refusing to overwrite evidence: {out}")
    out.mkdir(parents=True,exist_ok=True)
    for binary in ("bun",):
        if not __import__("shutil").which(binary):raise SystemExit(f"{binary} is required")
    results={label:run_mission(label,HERE/"results/cycle35-sequential-creation"/filename,out)
        for label,filename in (("mission-a","MISSION-A.json"),("mission-b","MISSION-B.json"))}
    write(out/"bridge-validation.json",{"schema":"basic-workspace.cycle35-production-bridge","version":1,
        "inference_performed":False,"missions":results,"passed":all(row["completed"] for row in results.values())})
    print(json.dumps({k:{"final_revision":v["final_revision"],"steps":len(v["steps"]),"completed":v["completed"]} for k,v in results.items()},indent=2))
if __name__=="__main__":main()
