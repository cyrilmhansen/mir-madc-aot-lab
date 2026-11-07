#!/usr/bin/env python3
"""Compare structured MIR execution with the historical interpreter and JIT."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

from basic_workspace.mir_execution import MirExecutionService
from basic_workspace.model import Workspace


LAB = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parents[1]
BASICC = Path(os.environ.get(
    "BASICC", HERE / "../basic-aot/results/aot/standalone/diagnostics/pristine-src/build/basic/basicc"
)).resolve()
OUT = HERE / "results/mir-execution/differential.json"

CASES = [
    {
        "name": "precedence-parentheses-negative",
        "source": "FUNCTION CALC(X)\nCALC=-(X+2)*3+20/4\nEND FUNCTION\n",
        "function": "CALC", "arguments": [2], "expected": -7.0,
    },
    {
        "name": "locals-and-precedence",
        "source": "FUNCTION QUOTIENT(A,B)\nC=A+B*2\nQUOTIENT=(C-A)/B\nEND FUNCTION\n",
        "function": "QUOTIENT", "arguments": [5, 2], "expected": 2.0,
    },
    {
        "name": "multiple-functions-and-calls",
        "source": "FUNCTION DOUBLE(X)\nDOUBLE=X*2\nEND FUNCTION\n"
                  "FUNCTION SUM(A,B)\nSUM=DOUBLE(A)+B\nEND FUNCTION\n",
        "function": "SUM", "arguments": [9, 3], "expected": 21.0,
    },
    {
        "name": "case-insensitive-binding",
        "source": "FUNCTION MIXED(Value)\nMIXED=vAlUe*value+1\nEND FUNCTION\n",
        "function": "MIXED", "arguments": [-3], "expected": 10.0,
    },
]


def historical_run(source: str, function: str, args: list[float], jit: bool) -> dict:
    if not BASICC.is_file():
        raise SystemExit(f"historical basicc is missing: {BASICC}")
    call = f"{function}(" + ",".join(format(float(x), ".17g") for x in args) + ")"
    full_source = source + f"PRINT {call}\nEND\n"
    # This file is only an isolated reference input for the old compiler. The new
    # execution path below receives the canonical in-memory document directly.
    with tempfile.TemporaryDirectory(prefix="atlas-basic-mir-reference-", dir="/tmp") as temp:
        path = Path(temp) / "reference.bas"
        path.write_text(full_source, encoding="utf-8")
        command = [str(BASICC)] + (["-j"] if jit else []) + [str(path)]
        start = time.perf_counter()
        proc = subprocess.run(command, capture_output=True, text=True, timeout=10)
        elapsed_ms = (time.perf_counter() - start) * 1000
    if proc.returncode != 0:
        raise RuntimeError(f"{command!r} failed: {proc.stderr}")
    return {"stdout": proc.stdout, "stderr": proc.stderr, "returncode": proc.returncode,
            "wall_ms": round(elapsed_ms, 3)}


def main() -> None:
    worker = MirExecutionService()
    output = {"basicc": str(BASICC), "cases": []}
    for case in CASES:
        ws = Workspace()
        opened = ws.open_document_from_string(case["source"])
        did = opened["document_id"]
        functions = ws.get_document_structure(did)["functions"]
        row = next(f for f in functions if f["name"].casefold() == case["function"].casefold())
        runs = {}
        for engine in ("interp", "jit"):
            result = worker.execute_function(ws, did, 1, row["symbol_id"], case["arguments"], engine)
            reference = historical_run(case["source"], case["function"], case["arguments"], engine == "jit")
            expected = float(reference["stdout"].strip())
            if abs(result["result"] - expected) > 1e-12:
                raise AssertionError(f"{case['name']} {engine}: MIR {result['result']} != historical {expected}")
            if abs(result["result"] - case["expected"]) > 1e-12:
                raise AssertionError(f"{case['name']} {engine}: result differs from fixture oracle")
            runs[engine] = {"mir": result, "historical": reference, "match": True}
        output["cases"].append({"name": case["name"], "function": case["function"],
                                "arguments": case["arguments"], "expected": case["expected"],
                                "runs": runs})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(f"validated {len(output['cases'])} fixtures in interpreter and JIT; wrote {OUT}")


if __name__ == "__main__":
    main()
