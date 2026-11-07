#!/usr/bin/env python3
"""Measure projection and fresh-process MIR compile/link/invoke costs."""
from __future__ import annotations

import json
from pathlib import Path
import statistics
import time

from basic_workspace.mir_execution import MirExecutionService
from basic_workspace.model import Workspace


HERE = Path(__file__).resolve().parents[1]
OUT = HERE / "results/mir-execution/benchmark.json"
REPETITIONS = 30
SOURCE = "".join(
    f"FUNCTION STEP{i}(X)\nSTEP{i}=X*1.25+{i}\nEND FUNCTION\n"
    for i in range(1, 9)
) + "FUNCTION TARGET(X)\nTARGET=STEP8(STEP7(STEP6(STEP5(X))))/3\nEND FUNCTION\n"


def percentiles(values):
    ordered = sorted(values)
    def at(p):
        return ordered[min(len(ordered) - 1, round((len(ordered) - 1) * p))]
    return {"mean": statistics.mean(values), "median": statistics.median(values),
            "p95": at(.95), "min": min(values), "max": max(values)}


def main():
    ws = Workspace()
    t0 = time.perf_counter()
    opened = ws.open_document_from_string(SOURCE)
    open_index_ms = (time.perf_counter() - t0) * 1000
    did = opened["document_id"]
    fn = next(x for x in ws.get_document_structure(did)["functions"] if x["name"] == "TARGET")
    service = MirExecutionService()
    output = {"repetitions": REPETITIONS, "warmups": 1, "cache": "none; every call builds a fresh MIR context and worker process",
              "corpus": {"functions": 9, "source_characters": len(SOURCE)},
              "workspace_open_and_index_ms": open_index_ms, "engines": {}}
    for engine in ("interp", "jit"):
        service.execute_function(ws, did, 1, fn["symbol_id"], [2.5], engine)
        rows = []
        for _ in range(REPETITIONS):
            result = service.execute_function(ws, did, 1, fn["symbol_id"], [2.5], engine)
            rows.append(result)
        fields = ["projection", "serialization", "worker_compile_and_execute",
                  "mir_build", "mir_link", "mir_jit_compile", "mir_invoke"]
        output["engines"][engine] = {
            "result": rows[-1]["result"],
            "worker_maxrss_kib_max": max(int(x["worker_maxrss_kib"] or 0) for x in rows),
            "timings_ms": {field: percentiles([float(x["timings_ms"].get(field, 0.0)) for x in rows])
                           for field in fields},
        }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT}; {REPETITIONS} fresh-worker samples per engine")


if __name__ == "__main__":
    main()
