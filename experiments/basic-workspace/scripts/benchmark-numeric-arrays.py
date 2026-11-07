#!/usr/bin/env python3
"""Measure projection and fresh-worker costs for fixed numeric arrays."""
from __future__ import annotations

import json
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from basic_workspace.mir_execution import MirExecutionService, encode_projection
from basic_workspace.model import Workspace
from basic_workspace.projection import build_projection

OUT = ROOT / "results/numeric-arrays/benchmark.json"
REPETITIONS = 30
CAPACITIES = (0, 1, 4, 16, 64, 256)


def summary(values: list[float]) -> dict[str, float]:
    values = sorted(values)
    return {"mean": statistics.mean(values), "median": statistics.median(values),
            "p95": values[round((len(values) - 1) * .95)],
            "min": values[0], "max": values[-1]}


def create_case(capacity: int):
    ws = Workspace()
    did = ws.create_empty_document()["document_id"]
    arrays = [] if capacity == 0 else [{"name": "A", "upper_bound": capacity - 1}]
    expression = {"kind": "number", "value": 0}
    if capacity:
        expression = {"kind": "array_element",
                      "array_ref": {"kind": "local_ref", "name": "A"},
                      "index": {"kind": "local_ref", "name": "I"}}
    result = ws.create_numeric_function(did, f"READ_{capacity}", ["I"], 1,
                                        arrays=arrays, expression=expression)
    fn = next(row for row in result["created_entities"] if row["kind"] == "function")
    return ws, did, fn["symbol_id"], result["revision"]


def main() -> None:
    service = MirExecutionService()
    report = {"repetitions_per_engine_and_capacity": REPETITIONS, "warmups": 1,
              "worker_model": "one fresh MIR worker process per invocation; no compilation cache",
              "measurement_note": "worker_compile_and_execute includes process startup; MIR phase timings exclude Python projection and transport",
              "capacities": {}}
    for capacity in CAPACITIES:
        ws, did, function_id, revision = create_case(capacity)
        projection = build_projection(ws, did, revision)
        encoded = encode_projection(projection, 0, [0.0], "interp")
        case = {"capacity": capacity, "upper_bound": capacity - 1 if capacity else None,
                "projection_functions": len(projection.functions), "bwm2_bytes": len(encoded),
                "engines": {}}
        for engine in ("interp", "jit"):
            service.execute_function(ws, did, revision, function_id, [0.0], engine)
            rows = [service.execute_function(ws, did, revision, function_id, [0.0], engine)
                    for _ in range(REPETITIONS)]
            fields = ("projection", "serialization", "worker_compile_and_execute",
                      "mir_build", "mir_link", "mir_jit_compile", "mir_invoke")
            case["engines"][engine] = {
                "result": rows[-1]["result"],
                "worker_maxrss_kib_max": max(int(row["worker_maxrss_kib"] or 0) for row in rows),
                "timings_ms": {field: summary([float(row["timings_ms"].get(field, 0.0))
                                               for row in rows]) for field in fields},
            }
        report["capacities"][str(capacity)] = case
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT}; {REPETITIONS} fresh-worker samples per engine/capacity")


if __name__ == "__main__":
    main()
