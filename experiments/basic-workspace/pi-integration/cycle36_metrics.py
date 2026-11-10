#!/usr/bin/env python3
"""Reproducible deterministic Cycle36 timing summary; no model/network calls."""
from __future__ import annotations
import json, pathlib, statistics, sys, tempfile, time
HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
RESULTS = HERE / "results/cycle36-verified-handoff"
RUN = RESULTS / "production-bridge-attempt-07"
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(HERE))
from basic_workspace.model import Workspace
from basic_workspace.portable_replay import replay_constructive_stream
from cycle20_gateway import Cycle20Gateway
from verified_handoff import build_handoff, verify_handoff

def read(path): return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
def stats(values): return {"samples": len(values), "median_ms": round(statistics.median(values), 3),
    "min_ms": round(min(values), 3), "max_ms": round(max(values), 3)}
def timed(fn, n=5):
    values=[]
    for _ in range(n):
        start=time.perf_counter(); fn(); values.append((time.perf_counter()-start)*1000)
    return stats(values)

def main():
    result={"schema":"basic-workspace.cycle36-deterministic-performance","version":1,
        "environment":"same local checkout, Python process, native MIR worker and Bun bridge; no inference or network calls",
        "missions":{}}
    for label in ("mission-a","mission-b"):
        root=RUN/label; evidence=root/"creation/gateway-evidence"; contract=root/"maintenance-contract.json"
        handoff=root/"handoff/handoff.json"; anchor=root/"handoff/host-trust-anchor.json"
        stream=read(root/"maintenance/gateway-evidence/constructive-operations.json")
        timings=[]
        for phase in ("creation","maintenance"):
            path=root/phase/"gateway-evidence/gateway-tool-timings.jsonl"
            timings.extend(json.loads(line) for line in path.read_text().splitlines() if line.strip())
        groups={}
        for row in timings: groups.setdefault(row["method"],[]).append(row["elapsed_ms"])
        gateway_stats={key:stats(vals) for key,vals in sorted(groups.items()) if key in {
            "preview_create_function","commit_preview","host_validate","create_checkpoint",
            "host_advance_creation_sequence","preview_semantic_edit","validate_mission"}}
        with tempfile.TemporaryDirectory(prefix="atlas-cycle36-metrics-",dir="/var/tmp") as temp:
            temp=pathlib.Path(temp)
            handoff_build=timed(lambda: build_handoff(evidence, root/"creation-sequence.json", contract,
                temp/"handoff.json",temp/"anchor.json"),5)
            handoff_verify=timed(lambda: verify_handoff(handoff,anchor,evidence,contract),5)
            baseline_init=timed(lambda: Cycle20Gateway(temp/f"init-{time.time_ns()}",contract_path=contract,
                verified_handoff_path=handoff,handoff_anchor_path=anchor,handoff_evidence_root=evidence),3)
        replay_times=[]
        for trial in range(5):
            ws=Workspace(); doc=ws.create_empty_document(f"memory://cycle36/metrics/{label}/{trial}.bas")["document_id"]
            start=time.perf_counter(); replay_constructive_stream(ws,doc,stream["operations"],
                expected_final_handles=stream["portable_handles"],expected_retired_handles=stream.get("retired_handles",[]),expected_start_revision=1)
            replay_times.append((time.perf_counter()-start)*1000)
        values=read(root/"independent-oracle-observations.json")["input_corpus"]
        oracle_times=[]
        for _ in range(5):
            start=time.perf_counter()
            for x in values:
                if label=="mission-a":
                    bounded=min(80,max(0,x)); _=(bounded,int(bounded>=70),int(bounded>=90),int(bounded>=90))
                else:
                    age=min(60,max(0,x)); senior=int(age>=55); _=(age,senior,senior)
            oracle_times.append((time.perf_counter()-start)*1000)
        result["missions"][label]={"creation_final_revision":len(read(root/"creation-sequence.json")["steps"])+1,
            "maintenance_final_revision":len(read(root/"creation-sequence.json")["steps"])+2,
            "gateway_tool_processing":gateway_stats,"handoff_serialization_and_hashing_5_runs":handoff_build,
            "handoff_verification_prefix_replay_5_runs":handoff_verify,
            "maintenance_gateway_startup_reconstruct_and_initial_mir_3_runs":baseline_init,
            "portable_full_stream_replay_5_runs":stats(replay_times),
            "independent_reference_arithmetic_5_runs":stats(oracle_times),
            "input_count":len(values),"stream_operations":len(stream["operations"])}
    (RESULTS/"performance.json").write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2))
if __name__=="__main__":main()
