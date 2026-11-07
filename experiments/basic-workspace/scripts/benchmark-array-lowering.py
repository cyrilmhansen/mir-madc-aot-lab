#!/usr/bin/env python3
"""Compare per-cell MIR dispatch with bounded stack-memory array lowering."""
from __future__ import annotations

import json
import os
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from basic_workspace.model import Workspace
from basic_workspace.mir_execution import MirExecutionService


def build(capacity):
    workspace = Workspace()
    document = workspace.create_empty_document()["document_id"]
    created = workspace.create_numeric_function(document, "VALUE_AT", ["I"], 1,
        arrays=[{"name": "VALUES", "upper_bound": capacity - 1}],
        expression={"kind": "array_element", "array_ref": {"kind": "local_ref", "name": "VALUES"},
                    "index": {"kind": "local_ref", "name": "I"}})
    function = next(row for row in created["created_entities"] if row["kind"] == "function")
    return workspace, document, function["symbol_id"], created["revision"]


def summarize(rows):
    phases = ("projection", "serialization", "worker_compile_and_execute",
              "mir_build", "mir_link", "mir_jit_compile", "mir_invoke")
    return {phase: round(statistics.median(row["timings_ms"][phase] for row in rows), 6)
            for phase in phases}


def main():
    executor = MirExecutionService()
    rows = []
    for capacity in (1, 4, 16, 64, 256):
        workspace, document, function, revision = build(capacity)
        for strategy, memory_value in (("register-dispatch", "0"), ("stack-memory", "1")):
            os.environ["BASIC_WORKSPACE_MEMORY_ARRAYS"] = memory_value
            for engine in ("interp", "jit"):
                warm = executor.execute_function(workspace, document, revision, function, [0], engine)
                if warm["result"] != 0:
                    raise SystemExit(f"incorrect capacity {capacity}, {strategy}, {engine}: {warm['result']}")
                samples = [executor.execute_function(workspace, document, revision,
                    function, [0], engine) for _ in range(30)]
                rows.append({"capacity": capacity, "strategy": strategy, "engine": engine,
                    "repetitions": 30, "result": warm["result"],
                    "median_ms": summarize(samples),
                    "maxrss_kib": max((sample["worker_maxrss_kib"] or 0) for sample in samples)})
            print(f"capacity {capacity} {strategy} done", flush=True)
    os.environ.pop("BASIC_WORKSPACE_MEMORY_ARRAYS", None)
    destination = ROOT / "results/control-flow-lookup/array-lowering-benchmark.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps({"method": "one warmup plus 30 fresh workers per cell",
        "sizes": rows}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(destination), "cells": len(rows)}, indent=2))


if __name__ == "__main__":
    main()
