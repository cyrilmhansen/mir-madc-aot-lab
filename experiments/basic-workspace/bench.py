#!/usr/bin/env python3
"""Read representative historical inputs and time in-memory model operations."""
from __future__ import annotations

import pathlib
import statistics
import sys
import time
import tracemalloc

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from basic_workspace import Workspace

ROOT = pathlib.Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "basic-aot/upstream/basic/samples"
CASES = [
    ("tiny", SAMPLES / "fn.bas"),
    ("medium", SAMPLES / "bcg/mastermind.bas"),
    ("large", SAMPLES / "bcg/poker.bas"),
]


def measure(fn, count=25):
    values = []
    for _ in range(count):
        start = time.perf_counter_ns()
        fn()
        values.append((time.perf_counter_ns() - start) / 1e6)
    return statistics.median(values)


def run():
    rows = []
    for name, path in CASES:
        text = path.read_text(errors="replace")
        ws = Workspace()
        tracemalloc.start()
        opened = ws.open_document_from_string(text, f"memory://bench/{name}")
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        did = opened["document_id"]
        doc = ws._doc(did)
        symbols = ws.list_symbols(did)
        target = next((s for s in symbols if s["kind"] in ("parameter", "variable")), None)
        if not target:
            raise RuntimeError(f"No renameable symbol found in {path}")
        old_name = target["name"]
        suffix = old_name[-1] if old_name.endswith(("$", "%", "!", "#")) else ""
        temp_name = "AGENT_TMP" + suffix
        rev = ws.get_revision(did)
        rename_ms = measure(lambda: _toggle_rename(ws, did, target["symbol_id"], old_name, temp_name), 10) / 2
        lookup_us = measure(lambda: ws.find_definition(did, target["symbol_id"]), 2000) * 1000
        # Return to original spelling if a measured odd number of pairs changed it.
        if ws.find_definition(did, target["symbol_id"])["name"] != old_name:
            ws.rename_symbol(did, target["symbol_id"], old_name, ws.get_revision(did))
        renumber_ms = None
        if doc.labels:
            old_line = min(doc.labels)
            new_line = max(doc.labels) + 97
            renumber_ms = measure(lambda: _toggle_line(ws, did, old_line, new_line), 10) / 2
        render_ms = measure(lambda: ws.render_document(did), 100)
        rows.append({"case": name, "source_bytes": len(text.encode()), "physical_lines": len(doc.lines),
                     "tokens": len(doc.tokens), "symbols": len(doc.symbols),
                     "parse_and_index_ms": round(measure(lambda: Workspace().open_document_from_string(text), 9), 3),
                     "rename_transaction_ms": round(rename_ms, 4),
                     "symbol_lookup_us": round(lookup_us, 3),
                     "renumber_transaction_ms": round(renumber_ms, 4) if renumber_ms is not None else None,
                     "render_ms": round(render_ms, 4), "tracemalloc_peak_bytes": peak,
                     "diagnostics": len(doc.diagnostics)})
    out = pathlib.Path(__file__).resolve().parent / "results/benchmark.json"
    out.parent.mkdir(exist_ok=True)
    import json
    out.write_text(json.dumps({"python": sys.version.split()[0], "results": rows}, indent=2) + "\n")
    md = ["# BASIC Workspace microbenchmarks", "",
          "Read-only inputs are historical `basic-aot` samples. Parse timing includes tokenization and semantic index construction; edits include candidate snapshot, validation and index rebuild. `tracemalloc` peak covers initial open/index. 25-operation medians are used except parse (9) and lookup (2,000). No source files are written.", "",
          "| Case | Source B | Lines | Tokens | Symbols | Parse/index ms | Rename tx ms | Lookup µs | Renumber tx ms | Render ms | Peak bytes | Diagnostics |",
          "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for r in rows:
        md.append("| {case} | {source_bytes} | {physical_lines} | {tokens} | {symbols} | {parse_and_index_ms} | {rename_transaction_ms} | {symbol_lookup_us} | {renumber_transaction_ms} | {render_ms} | {tracemalloc_peak_bytes} | {diagnostics} |".format(**r))
    (out.parent / "benchmark.md").write_text("\n".join(md) + "\n")
    print(out.parent / "benchmark.md")


def _toggle_rename(ws, did, sid, old, new):
    ws.rename_symbol(did, sid, new, ws.get_revision(did))
    ws.rename_symbol(did, sid, old, ws.get_revision(did))


def _toggle_line(ws, did, old, new):
    ws.renumber_line(did, old, new, ws.get_revision(did))
    ws.renumber_line(did, new, old, ws.get_revision(did))


if __name__ == "__main__":
    run()
