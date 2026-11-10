#!/usr/bin/env python3
"""Collect repeated deterministic timings for the Cycle38 verified workflow."""
from __future__ import annotations

import json
import argparse
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(HERE))
from basic_workspace.model import Workspace
from basic_workspace.mir_execution import MirExecutionService
from basic_workspace.portable_replay import replay_constructive_stream
from verified_rename_continuation import verify_rename_continuation

ATTEMPT = HERE / "results/cycle38-longitudinal-stress/production-bridge-attempt-08"


def stats(values):
    return {"samples_ms": [round(x, 3) for x in values], "median_ms": round(statistics.median(values), 3),
        "min_ms": round(min(values), 3), "max_ms": round(max(values), 3)}


def main():
    global ATTEMPT
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt",type=Path,default=ATTEMPT)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args(); ATTEMPT=args.attempt.resolve()
    output = {"schema": "basic-workspace.cycle38-performance", "version": 1,
        "environment": {"python": sys.version.split()[0], "platform": sys.platform,
            "scope": "same local repository and runtime for both missions; deterministic, no inference"},
        "samples": {}}
    executor = MirExecutionService(timeout=20)
    for mission in ("mission-a", "mission-b"):
        src = ATTEMPT / mission
        package = src / "continuation-package"
        bundle, anchor, contract = (package / "continuation.json", src / "continuation-package-host-trust-anchor.json",
            package / "maintenance-contract.json")
        auth = []
        for _ in range(4):
            start = time.perf_counter()
            checked = verify_rename_continuation(bundle, anchor, package, contract)
            auth.append((time.perf_counter() - start) * 1000)
            if not checked["all_checks_passed"]: raise RuntimeError("continuation timing run failed verification")
        stream = json.loads((src / "maintenance/gateway-evidence/constructive-operations.json").read_text())
        replay_samples=[]; init_samples=[]; last=None
        for index in range(8):
            t0=time.perf_counter(); ws=Workspace(); doc=ws.create_empty_document(
                f"memory://cycle38/metrics/{mission}/{index}.bas")["document_id"]
            init_samples.append((time.perf_counter()-t0)*1000)
            t0=time.perf_counter(); last=replay_constructive_stream(ws,doc,stream["operations"],
                expected_final_handles=stream["portable_handles"],expected_retired_handles=[],expected_start_revision=1)
            replay_samples.append((time.perf_counter()-t0)*1000)
        inputs=json.loads((src / "independent-oracle-observations.json").read_text())["inputs"]
        handles=sorted(h for h in last.live_handles if h.endswith(".function"))
        oracle_samples={"interp":[],"jit":[]}
        for engine in oracle_samples:
            for _ in range(2):
                t0=time.perf_counter()
                for x in inputs:
                    for handle in handles:
                        executor.execute_function(ws,doc,last.revision,last.live_handles[handle],[x],engine)
                oracle_samples[engine].append((time.perf_counter()-t0)*1000)
        output["samples"][mission]={"continuation_authentication":stats(auth),
            "empty_workspace_initialization":stats(init_samples), "complete_fresh_replay":stats(replay_samples),
            "independent_mir_observation_corpus":{engine:stats(samples) for engine,samples in oracle_samples.items()},
            "observation_calls_per_sample":len(inputs)*len(handles), "replay_operations":len(stream["operations"])}
    # Preserve raw request latencies captured by the actual gateway processes.
    gateway = {}
    for mission in ("mission-a", "mission-b"):
        gateway[mission]={}
        for stage in ("creation", "rename", "maintenance"):
            path=ATTEMPT/mission/stage/"gateway-evidence/gateway-tool-timings.jsonl"
            rows=[json.loads(line) for line in path.read_text().splitlines() if line]
            gateway[mission][stage]={}
            for method in ("preview_create_function","create_checkpoint","host_advance_creation_sequence",
                "preview_rename","preview_semantic_edit","commit_preview","host_validate"):
                values=[row["elapsed_ms"] for row in rows if row["method"]==method]
                if values: gateway[mission][stage][method]=stats(values)
    output["gateway_recorded_latencies_ms"]=gateway
    path=args.output.resolve()
    if path.exists(): raise SystemExit(f"Refusing to overwrite performance evidence: {path}")
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(output,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({mission:{name:value["median_ms"] for name,value in row.items()
        if isinstance(value,dict) and "median_ms" in value} for mission,row in output["samples"].items()},indent=2))


if __name__ == "__main__": main()
