#!/usr/bin/env python3
"""Capture pinned historical BASIC behavior and the in-memory MIR lookup run."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT.parents[1]
RESULTS = ROOT / "results/control-flow-lookup"
FIXTURES = RESULTS / "fixtures"
DEFAULT_COMPILER = LAB / "experiments/basic-aot/results/aot/standalone/diagnostics/pristine-src/build/basic/basicc"

HISTORICAL = {
    "comparison-values": 'EQ=1\nNE=0\nLT=1\nLE=1\nGT=1\nGE=1\nFALSE=0\n',
    "if-top-truth": "ZERO-FALSE\nNEGATIVE-TRUE\n",
    "for-positive": "6\n",
    "for-zero-iteration": "9\n",
    "for-negative": "3\n",
    "for-evaluation": "1\n",
    # Captures a pinned historical compiler discrepancy. In FUNCTION bodies
    # the IF condition is mishandled: this conditional returns 20 for both.
    "if-function-result": "ONE=20\nTWO=20\n",
}


def run(command: list[str]) -> dict:
    result = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
    return {"returncode": result.returncode, "stdout": result.stdout,
            "stderr": result.stderr}


def main() -> None:
    compiler = Path(os.environ.get("HISTORICAL_BASIC_C", DEFAULT_COMPILER)).resolve()
    if not compiler.is_file():
        raise SystemExit(f"historical compiler not found: {compiler}; set HISTORICAL_BASIC_C")
    records = []
    for stem, expected in HISTORICAL.items():
        fixture = FIXTURES / f"{stem}.bas"
        for engine, args in (("interp", []), ("jit", ["-j"])):
            observed = run([str(compiler), *args, str(fixture)])
            passed = (observed["returncode"] == 0 and observed["stdout"] == expected and
                      observed["stderr"] == "")
            records.append({"fixture": stem, "engine": engine, "expected_stdout": expected,
                            **observed, "matches_pinned_baseline": passed,
                            "classification": "known_function_if_mismatch" if stem == "if-function-result"
                            else "baseline_semantics"})
            if not passed:
                raise SystemExit(f"pinned historical output changed for {stem}/{engine}: {observed}")

    trace_path = RESULTS / "construction-trace.json"
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    expected_lookup = {101: 25, 205: 42, 900: 53, 999: -1, 2: -1}
    # Rendering is downstream oracle materialization only. The Workspace
    # compile/execute path itself remains token-model -> projection -> MIR.
    source = trace["rendered_diagnostic_only"] + "".join(
        f'PRINT "{ident}="; AGE_BY_ID({ident})\n' for ident in expected_lookup)
    with tempfile.TemporaryDirectory(prefix="atlas-control-flow-oracle-") as temp_dir:
        source_path = Path(temp_dir) / "age-by-id.bas"
        source_path.write_text(source, encoding="utf-8")
        for engine, args in (("interp", []), ("jit", ["-j"])):
            observed = run([str(compiler), *args, str(source_path)])
            records.append({"fixture": "rendered-age-by-id", "engine": engine,
                "expected_lookup": expected_lookup, **observed,
                "workspace_expected_stdout": "101=25\n205=42\n900=53\n999=-1\n2=-1\n",
                "matches_workspace_semantics": observed["stdout"] ==
                    "101=25\n205=42\n900=53\n999=-1\n2=-1\n",
                "classification": "known_function_if_mismatch"})

    report = {"historical_compiler": str(compiler), "command_template":
        "basicc [ -j ] fixture.bas", "records": records,
        "historical_fixture_checks_pass": all(r.get("matches_pinned_baseline", True) for r in records),
        "lookup_matches_historical": all(r.get("matches_workspace_semantics", True) for r in records
                                          if r["fixture"] == "rendered-age-by-id"),
        "note": "The pinned compiler gives the same broken function-IF results in interpreter and JIT; these are recorded as a compatibility discrepancy, not a Workspace pass."}
    (RESULTS / "historical-differential.json").write_text(json.dumps(report, indent=2) + "\n",
                                                            encoding="utf-8")
    print(json.dumps({"historical_fixture_checks_pass": report["historical_fixture_checks_pass"],
                      "lookup_matches_historical": report["lookup_matches_historical"],
                      "checks": len(records), "results": str(RESULTS / "historical-differential.json")},
                     indent=2))


if __name__ == "__main__":
    main()
