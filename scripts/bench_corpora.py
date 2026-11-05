#!/usr/bin/env python3
import csv
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

runner, artifacts, timing_csv, size_csv, repeats = sys.argv[1:]
artifacts = Path(artifacts)
repeats = int(repeats)
counts = (10, 100, 1000, 5000)
fields = ["scenario", "functions", "repetition", "wall_ns", "parse_ns", "link_ns",
          "jit_ns", "first_call_ns", "calls_ns", "user_cpu_us", "system_cpu_us",
          "minor_faults", "major_faults", "maxrss_native_units", "verified_calls",
          "result_checksum", "input_bytes", "status"]
sizes = []
rows = []

def invoke(args):
    started = time.perf_counter_ns()
    result = subprocess.run(args, check=True, text=True, capture_output=True)
    wall = time.perf_counter_ns() - started
    data = json.loads(result.stdout.strip().splitlines()[-1])
    data["wall_ns"] = wall
    data["maxrss_native_units"] = data.pop("maxrss_bytes")
    return data

for count in counts:
    text_path = artifacts / f"corpus-{count}.mir"
    bmir_path = artifacts / f"corpus-{count}.bmir"
    subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] /
                       "src/microbench/gen_corpus.py"), str(count), str(text_path)], check=True)
    invoke([runner, "write-ir", str(text_path), str(count), str(bmir_path)])
    sizes += [
        {"artifact": text_path.name, "format": "MIR text", "bytes": text_path.stat().st_size,
         "status": "MEASURED", "notes": "synthetic live-function corpus"},
        {"artifact": bmir_path.name, "format": ".bmir", "bytes": bmir_path.stat().st_size,
         "status": "MEASURED", "notes": "MIR binary written by MIR_write"},
    ]
    for scenario, source in (("text_parse_then_eager_jit", text_path),
                             ("bmir_decode_then_eager_jit", bmir_path)):
        mode = "corpus-text" if scenario.startswith("text") else "corpus-bmir"
        # One unrecorded process per corpus and path warms executable pages and
        # the filesystem cache. Timed repetitions still use fresh processes.
        invoke([runner, mode, str(source), str(count)])
        for repetition in range(1, repeats + 1):
            row = invoke([runner, mode, str(source), str(count)])
            row.update({"scenario": scenario, "functions": count,
                        "repetition": repetition, "status": "PASS"})
            rows.append(row)

with open(timing_csv, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
with open(size_csv, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["artifact", "format", "bytes", "status", "notes"])
    writer.writeheader()
    writer.writerows(sizes)

summary_path = Path(timing_csv).with_name("summary.md")
with summary_path.open("w") as f:
    f.write("# Synthetic benchmark summary\n\n")
    f.write("Host: macOS arm64. Every row is a new process; page cache may be warm. "
            "These are JIT and MIR-binary decode measurements, not ELF AOT measurements.\n\n")
    f.write("| Functions | Scenario | Median wall ms | p95 wall ms | Min ms | SD ms | "
            "Median parse ms | Median JIT ms | Median CPU ms |\n")
    f.write("|---:|---|---:|---:|---:|---:|---:|---:|---:|\n")
    for count in counts:
        for scenario in ("text_parse_then_eager_jit", "bmir_decode_then_eager_jit"):
            group = [r for r in rows if r["functions"] == count and r["scenario"] == scenario]
            walls = [r["wall_ns"] / 1e6 for r in group]
            parses = [r["parse_ns"] / 1e6 for r in group]
            jits = [r["jit_ns"] / 1e6 for r in group]
            cpus = [(r["user_cpu_us"] + r["system_cpu_us"]) / 1000 for r in group]
            p95 = sorted(walls)[max(0, int(0.95 * len(walls) + .999) - 1)]
            f.write(f"| {count} | {scenario} | {statistics.median(walls):.3f} | "
                    f"{p95:.3f} | {min(walls):.3f} | {statistics.stdev(walls):.3f} | "
                    f"{statistics.median(parses):.3f} | {statistics.median(jits):.3f} | "
                    f"{statistics.median(cpus):.3f} |\n")
