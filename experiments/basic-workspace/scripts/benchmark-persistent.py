#!/usr/bin/env python3
"""Compare fresh one-shot workers with retained MIR modules."""
from __future__ import annotations

import json
from pathlib import Path
import statistics
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from basic_workspace.mir_execution import MirExecutionService, PersistentExecutionService
from basic_workspace.model import Workspace


def main() -> None:
    w = Workspace()
    doc = w.create_empty_document()["document_id"]
    created = w.create_numeric_function(doc, "DOUBLE", ["X"], 1,
        expression={"kind": "binary", "operator": "*",
                    "left": {"kind": "local_ref", "name": "X"},
                    "right": {"kind": "number", "value": 2}})
    revision = created["revision"]
    function_id = next(x["symbol_id"] for x in created["created_entities"]
                       if x["kind"] == "function")
    result = {"document_id": doc, "revision": revision, "function_id": function_id,
              "counts": [1, 10, 100, 1000], "engines": {}}
    for engine in ("interp", "jit"):
        row = {"one_shot": {}, "persistent": {}}
        for count in result["counts"]:
            times = []
            for n in range(count):
                started = time.perf_counter()
                value = MirExecutionService(timeout=5).execute_function(
                    w, doc, revision, function_id, [n], engine)["result"]
                times.append((time.perf_counter() - started) * 1000)
                assert value == 2.0 * n
            row["one_shot"][str(count)] = {
                "total_ms": round(sum(times), 3),
                "mean_ms": round(statistics.mean(times), 4),
                "median_ms": round(statistics.median(times), 4)}

        service = PersistentExecutionService(timeout=5)
        module = service.prepare_module(w, doc, revision, engine)
        started = time.perf_counter()
        instance = service.create_instance(module["module_id"])
        startup_ms = (time.perf_counter() - started) * 1000
        iid = instance["instance_id"]
        for count in result["counts"]:
            times = []
            for n in range(count):
                started = time.perf_counter()
                value = service.call_instance_function(iid, function_id, [n], revision)["result"]
                times.append((time.perf_counter() - started) * 1000)
                assert value == 2.0 * n
            row["persistent"][str(count)] = {
                "total_ms": round(sum(times), 3),
                "mean_ms": round(statistics.mean(times), 4),
                "median_ms": round(statistics.median(times), 4)}
        info = service.get_instance_info(iid)
        row["module_prepare_ms"] = module["projection_ms"]
        row["instance_startup_ms"] = startup_ms
        row["mir_build_link_ms"] = info["worker_timings_ms"]
        row["mir_build_count"] = info["mir_build_count"]
        row["mir_link_count"] = info["mir_link_count"]
        row["rss_kib"] = int(next(line.split()[1] for line in
            Path(f"/proc/{service.instances[iid].proc.pid}/status").read_text().splitlines()
            if line.startswith("VmRSS:")))
        destroy_started = time.perf_counter()
        service.destroy_instance(iid)
        row["instance_destroy_ms"] = round((time.perf_counter() - destroy_started) * 1000, 3)
        service.release_module(module["module_id"])
        result["engines"][engine] = row
        service.close()
    output = Path(__file__).resolve().parents[1] / "results" / "persistent-instances" / "benchmark.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + chr(10))
    print(output)


if __name__ == "__main__":
    main()
