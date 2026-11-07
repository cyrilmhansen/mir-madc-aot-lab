#!/usr/bin/env python3
"""Run the final rendered construction through historical BASIC interpreters."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
GENERATED = ROOT / "results/program-construction/constructed.bas"
OUT = ROOT / "results/program-construction/historical-oracle.json"
BASICC = Path(os.environ.get("BASICC", ROOT.parent / "basic-aot/results/aot/standalone/diagnostics/pristine-src/build/basic/basicc")).resolve()


def main():
    if not GENERATED.is_file():
        raise SystemExit(f"run program_construction_demo.py first; missing {GENERATED}")
    if not BASICC.is_file():
        raise SystemExit(f"historical basicc is missing: {BASICC}")
    source = GENERATED.read_text(encoding="utf-8")
    driver = source + "PRINT TRIPLE(9)\nPRINT CALCULATE(9)\nEND\n"
    rows = []
    with tempfile.TemporaryDirectory(prefix="atlas-basic-construction-", dir="/tmp") as directory:
        path = Path(directory) / "oracle.bas"
        path.write_text(driver, encoding="utf-8")
        for mode, flags in (("interpreter", []), ("jit", ["-j"])):
            result = subprocess.run([str(BASICC), *flags, str(path)], capture_output=True,
                                    text=True, timeout=10)
            row = {"mode": mode, "returncode": result.returncode,
                   "stdout": result.stdout, "stderr": result.stderr}
            rows.append(row)
            if result.returncode != 0 or result.stdout != "27\n30\n" or result.stderr:
                raise SystemExit(f"historical {mode} mismatch: {row}")
    report = {"basicc": str(BASICC), "generated_from_workspace_after_construction": str(GENERATED),
              "expected_stdout": "27\n30\n", "runs": rows,
              "temporary_source_cleaned": True,
              "note": "BASIC export is downstream oracle input only; construction and MIR execution do not read it."}
    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"historical interpreter and JIT match; wrote {OUT}")


if __name__ == "__main__":
    main()
