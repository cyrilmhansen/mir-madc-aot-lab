#!/usr/bin/env python3
"""Repeated deterministic Cycle39 semantic and production-path timings."""
from __future__ import annotations
import argparse, copy, json, statistics, sys, time
from pathlib import Path
HERE=Path(__file__).resolve().parent; ROOT=HERE.parent
sys.path[:0]=[str(ROOT),str(HERE)]
from basic_workspace.model import Workspace
from basic_workspace.mir_execution import MirExecutionService
from basic_workspace.portable_replay import PortableReplay
from basic_workspace.projection import build_projection
from cycle39_differential_campaign import generate_cases

def stats(values):
    return {"samples_ms":[round(x,4) for x in values],"median_ms":round(statistics.median(values),4),
        "min_ms":round(min(values),4),"max_ms":round(max(values),4),"spread_ms":round(max(values)-min(values),4)}

def main():
    p=argparse.ArgumentParser();p.add_argument("--output",type=Path,required=True)
    p.add_argument("--production-summary",type=Path,required=True);p.add_argument("--repetitions",type=int,default=7)
    a=p.parse_args();case=generate_cases(4)[3]; ctor_count=len(case["functions"]);samples={k:[] for k in (
        "workspace_initialization","constructor_authoritative_apply","rename_and_literal_edit_apply",
        "projection_build","mir_interpreter_batch","mir_jit_batch","fresh_replay")}
    executor=MirExecutionService(timeout=2); inputs=[case["generation_parameters"]["threshold"]-1,
        case["generation_parameters"]["threshold"],case["generation_parameters"]["upper"]+1]
    operations=case["operations"]
    for repetition in range(a.repetitions):
        t=time.perf_counter();ws=Workspace();doc=ws.create_empty_document(f"memory://cycle39/perf/{repetition}")["document_id"]
        runner=PortableReplay(ws,doc);samples["workspace_initialization"].append((time.perf_counter()-t)*1000)
        t=time.perf_counter()
        for op in operations[:ctor_count]:runner.apply_operation(copy.deepcopy(op))
        samples["constructor_authoritative_apply"].append((time.perf_counter()-t)*1000)
        t=time.perf_counter()
        for op in operations[ctor_count:]:runner.apply_operation(copy.deepcopy(op))
        samples["rename_and_literal_edit_apply"].append((time.perf_counter()-t)*1000)
        t=time.perf_counter();projection=build_projection(ws,doc,ws.get_revision(doc));samples["projection_build"].append((time.perf_counter()-t)*1000)
        target=operations[0]["portable_handle"]
        for engine,key in (("interp","mir_interpreter_batch"),("jit","mir_jit_batch")):
            t=time.perf_counter()
            for x in inputs:executor.execute_function(ws,doc,ws.get_revision(doc),runner.aliases[target],[x],engine)
            samples[key].append((time.perf_counter()-t)*1000)
        t=time.perf_counter();rws=Workspace();rdoc=rws.create_empty_document(f"memory://cycle39/perf-replay/{repetition}")["document_id"]
        replay=PortableReplay(rws,rdoc)
        for op in operations:replay.apply_operation(copy.deepcopy(op))
        samples["fresh_replay"].append((time.perf_counter()-t)*1000)
    production=json.loads(a.production_summary.read_text(encoding="utf-8"))
    replay_per_operation=[value/len(operations) for value in samples["fresh_replay"]]
    dispatch=[step["bridge_dispatch_ms"] for row in production["workflows"] for step in row["steps"]]
    validation=[step["host_validation_ms"] for row in production["workflows"] for step in row["steps"]]
    checkpoint=[step["checkpoint_and_progression_ms"] for row in production["workflows"] for step in row["steps"]]
    result={"schema":"basic-workspace.cycle39-performance","version":1,"repetitions":a.repetitions,
        "representative_case":case["case_id"],"input_count_per_mir_batch":len(inputs),
        "semantic_timings":{k:stats(v) for k,v in samples.items()},
        "production_observed_timings":{
            "typescript_jsonl_tool_roundtrip_including_discover_inspect_negative_controls_preview_commit_validate":stats(dispatch),
            "independent_host_validation":stats(validation),"checkpoint_and_sequence_progression":stats(checkpoint)},
        "portable_replay_per_operation":stats(replay_per_operation),
        "registered_suspicious_replay_threshold_ms_per_operation":9.88,
        "suspicious_replay_regression":statistics.median(replay_per_operation)>9.88,
        "limits":"Per-tool preview and commit subcalls are not separately timed by the existing test probe; bridge dispatch is an end-to-end handler round trip. MIR rows include worker process startup/compile/invoke as reported by MirExecutionService. Replay comparison uses Cycle38's documented 24.7 ms median across five/six-operation histories, conservatively normalized by five operations; this is a coarse same-environment baseline rather than an identical semantic workload."}
    path=a.output.resolve();path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({"repetitions":a.repetitions,"semantic_medians_ms":{k:v["median_ms"] for k,v in result["semantic_timings"].items()},
        "production_dispatch_median_ms":result["production_observed_timings"]["typescript_jsonl_tool_roundtrip_including_discover_inspect_negative_controls_preview_commit_validate"]["median_ms"]},indent=2))
if __name__=="__main__":main()
