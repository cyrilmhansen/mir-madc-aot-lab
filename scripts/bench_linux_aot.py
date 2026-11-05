#!/usr/bin/env python3
"""Fresh-process Linux x86-64 MIR text/.bmir/.o/.so benchmark."""
import csv
import json
import math
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

root = Path(sys.argv[1]).resolve()
repeats = int(sys.argv[2])
art = root / "results/linux-x86_64/artifacts"
corpora = art / "corpora"
runner = art / "libmir-smoke"
aot = art / "aot-corpus"
dlopen = art / "elf-dlopen-corpus"
rows, emit_rows, size_rows = [], [], []

def invoke(command):
    started = time.perf_counter_ns()
    result = subprocess.run(command, check=True, text=True, capture_output=True)
    wall = time.perf_counter_ns() - started
    payload = json.loads(result.stdout.strip().splitlines()[-1]) if result.stdout.strip() else {}
    payload["wall_ns"] = wall
    return payload

def record(scenario, count, repetition, data):
    row = {"scenario": scenario, "functions": count, "repetition": repetition,
           "status": "PASS", **data}
    rows.append(row)

for count in (10, 100, 1000, 5000):
    text_path = corpora / f"corpus-{count}.mir"
    bmir_path = corpora / f"corpus-{count}.bmir"
    subprocess.run([sys.executable, str(root / "src/microbench/gen_corpus.py"),
                    str(count), str(text_path)], check=True)
    invoke([str(runner), "write-ir", str(text_path), str(count), str(bmir_path)])
    for label, mode, source in (("text_parse_then_eager_jit", "corpus-text", text_path),
                                ("bmir_decode_then_eager_jit", "corpus-bmir", bmir_path)):
        invoke([str(runner), mode, str(source), str(count)])
        for rep in range(1, repeats + 1):
            record(label, count, rep, invoke([str(runner), mode, str(source), str(count)]))

    object_path = art / f"corpus-{count}.o"
    shared_path = art / f"libcorpus-{count}.so"
    pie_path = art / f"corpus-{count}-pie"
    for kind, src, out in (("object", text_path, object_path),
                           ("shared", text_path, shared_path)):
        data = invoke([str(aot), "emit", kind, str(src), str(out), str(count)])
        emit_rows.append({"functions": count, "artifact": kind, **data})
    pie_text = corpora / f"corpus-{count}-pie.mir"
    subprocess.run([sys.executable, str(root / "src/microbench/gen_corpus.py"),
                    str(count), str(pie_text), "--pie-main"], check=True)
    data = invoke([str(aot), "emit", "pie", str(pie_text), str(pie_path), str(count)])
    emit_rows.append({"functions": count, "artifact": "pie", **data})

    for path, fmt, notes in ((text_path, "MIR text", "live arithmetic functions"),
                             (bmir_path, ".bmir", "MIR_write binary"),
                             (object_path, "ELF ET_REL", "MIR_gen_object_emit"),
                             (shared_path, "ELF ET_DYN .so", "MIR shared emitter"),
                             (pie_path, "ELF PIE", "MIR executable emitter")):
        size_rows.append({"artifact": path.name, "format": fmt, "bytes": path.stat().st_size,
                          "status": "MEASURED", "notes": notes})
    run = subprocess.run([str(pie_path)])
    if run.returncode != 0:
        raise SystemExit(f"PIE verification failed: {pie_path} returned {run.returncode}")

    for scenario, command in (("elf_object_MIR_object_load", [str(aot), "load", str(object_path), str(count)]),
                              ("elf_shared_dlopen", [str(dlopen), str(shared_path), str(count)])):
        invoke(command)  # one unmeasured warm-up in a new process
        for rep in range(1, repeats + 1):
            record(scenario, count, rep, invoke(command))

fields = sorted({key for row in rows for key in row})
out = root / "results/linux-x86_64"
with (out / "timings.csv").open("w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader(); writer.writerows(rows)
with (out / "emission.csv").open("w", newline="") as f:
    fields = sorted({key for row in emit_rows for key in row})
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader(); writer.writerows(emit_rows)
with (out / "sizes.csv").open("w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["artifact", "format", "bytes", "status", "notes"])
    writer.writeheader(); writer.writerows(size_rows)

def p95(values):
    return sorted(values)[max(0, math.ceil(.95 * len(values)) - 1)]

with (out / "summary.md").open("w") as f:
    f.write("# Linux x86-64 AOT fresh-process benchmark\n\n")
    f.write("Host CPU is QEMU TCG on an Apple M2 Ultra; results are emulated and not native x86-64 performance. "
            "One warm-up per scenario, then fresh process per measured row; page cache remains warm.\n\n")
    f.write("| Functions | Path | Median wall ms | p95 ms | Min ms | SD ms | Median setup/load ms | Median first call ms | Median RSS KiB |\n")
    f.write("|---:|---|---:|---:|---:|---:|---:|---:|---:|\n")
    for count in (10, 100, 1000, 5000):
        for scenario in ("text_parse_then_eager_jit", "bmir_decode_then_eager_jit",
                         "elf_object_MIR_object_load", "elf_shared_dlopen"):
            group = [r for r in rows if r["functions"] == count and r["scenario"] == scenario]
            walls = [r["wall_ns"] / 1e6 for r in group]
            if scenario.startswith("text") or scenario.startswith("bmir"):
                setup = [r.get("parse_ns", 0) + r.get("link_ns", 0) + r.get("jit_ns", 0) for r in group]
                first = [r.get("first_call_ns", 0) for r in group]
                rss = [r.get("maxrss_bytes", 0) / 1024 for r in group]
            elif scenario == "elf_object_MIR_object_load":
                setup = [r["load_relocate_ns"] for r in group]
                first = [r["first_call_ns"] for r in group]
                rss = [r.get("maxrss_kib", 0) for r in group]
            else:
                setup = [r["dlopen_ns"] for r in group]
                first = [r["first_call_ns"] for r in group]
                rss = [r.get("maxrss_kib", 0) for r in group]
            f.write(f"| {count} | {scenario} | {statistics.median(walls):.3f} | {p95(walls):.3f} | "
                    f"{min(walls):.3f} | {statistics.stdev(walls):.3f} | "
                    f"{statistics.median(setup)/1e6:.3f} | {statistics.median(first)/1e6:.6f} | "
                    f"{statistics.median(rss):.0f} |\n")
