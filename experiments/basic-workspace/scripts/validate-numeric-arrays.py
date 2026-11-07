#!/usr/bin/env python3
"""Run historical BASIC interpreter/JIT fixtures and the in-memory MIR array demo."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import sys

ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT.parents[1]
DEFAULT_BASIC = LAB / "experiments/basic-aot/results/aot/standalone/diagnostics/pristine-src/build/basic/basicc"
RESULTS = ROOT / "results/numeric-arrays"
FIXTURES = RESULTS / "fixtures"


def run(command: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(command, text=True, capture_output=True, timeout=10, **kwargs)


def main() -> None:
    sys.path.insert(0, str(ROOT))
    from basic_workspace.mir_execution import MirExecutionService
    from basic_workspace.model import Workspace

    basicc = Path(os.environ.get("HISTORICAL_BASIC_C", DEFAULT_BASIC)).resolve()
    if not basicc.is_file():
        raise SystemExit(f"historical basicc not found: {basicc}; set HISTORICAL_BASIC_C")
    expected = {
        "local-array": "11\n33\n44\n",
        "index-conversion": "22\n11\n",
        "repeated-call": "1\n1\n",
        "option-base-1": "11\n33\n",
        "duplicate-dim": "0\n",
        "array-call-name": "7\n101\n",
        "array-scalar-collision": "12\n",
        # The historical runtime stops on an invalid array index, so the
        # following PRINT is not reached; status is currently zero.
        "out-of-range": "",
    }
    rows = []
    with tempfile.TemporaryDirectory(prefix="atlas-basic-arrays-diff-") as temp:
        tempdir = Path(temp)
        for stem, output in expected.items():
            source = FIXTURES / f"{stem}.bas"
            for mode, args in (("interp", []), ("jit", ["-j"])):
                completed = run([str(basicc), *args, str(source)])
                ok = completed.returncode == 0 and completed.stdout == output and completed.stderr == ""
                rows.append({"fixture": stem, "mode": mode, "returncode": completed.returncode,
                             "stdout": completed.stdout, "stderr": completed.stderr, "pass": ok})
                if not ok:
                    raise SystemExit(f"historical {mode} mismatch for {stem}: {completed!r}")

        # Construct VALUE_AT from typed semantic calls; no BASIC source is opened.
        workspace = Workspace()
        did = workspace.create_empty_document()["document_id"]
        assignments = [{"array_ref": {"kind": "local_ref", "name": "VALUES"},
                        "index": {"kind": "number", "value": i},
                        "expression": {"kind": "number", "value": value}}
                       for i, value in enumerate((11, 22, 33, 44))]
        created = workspace.create_numeric_function(did, "VALUE_AT", ["I"], 1,
            arrays=[{"name": "VALUES", "upper_bound": 3}], array_assignments=assignments,
            expression={"kind": "array_element",
                        "array_ref": {"kind": "local_ref", "name": "VALUES"},
                        "index": {"kind": "local_ref", "name": "I"}})
        function_id = next(x["symbol_id"] for x in created["created_entities"] if x["kind"] == "function")
        executor = MirExecutionService()
        for engine in ("interp", "jit"):
            results = [executor.execute_function(workspace, did, 2, function_id, [i], engine)["result"]
                       for i in (0, 2, 3)]
            if results != [11.0, 33.0, 44.0]:
                raise SystemExit(f"workspace MIR {engine} mismatch: {results}")
            rows.append({"fixture": "typed-constructor", "mode": engine,
                         "results": results, "pass": True})

        # Source export is only used downstream as the historical compiler oracle.
        exported = workspace.render_document(did) + "PRINT VALUE_AT(0)\nPRINT VALUE_AT(2)\nPRINT VALUE_AT(3)\n"
        source = tempdir / "workspace-output.bas"
        source.write_text(exported, encoding="utf-8")
        for mode, args in (("interp", []), ("jit", ["-j"])):
            completed = run([str(basicc), *args, str(source)])
            ok = completed.returncode == 0 and completed.stdout == expected["local-array"] and completed.stderr == ""
            rows.append({"fixture": "rendered-downstream-oracle", "mode": mode,
                         "returncode": completed.returncode, "stdout": completed.stdout,
                         "stderr": completed.stderr, "pass": ok})
            if not ok:
                raise SystemExit(f"downstream historical {mode} mismatch: {completed!r}")

    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "historical-differential.json").write_text(
        json.dumps({"historical_basicc": "pristine historical BASIC compiler",
                    "rows": rows, "all_pass": all(row["pass"] for row in rows)}, indent=2) + "\n",
        encoding="utf-8")
    print(json.dumps({"all_pass": all(row["pass"] for row in rows), "cases": len(rows),
                      "results": str(RESULTS / "historical-differential.json")}, indent=2))


if __name__ == "__main__":
    main()
