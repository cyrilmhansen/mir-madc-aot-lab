#!/usr/bin/env python3
"""Measure fresh-process execution of emitted PIE corpus artifacts."""
import csv
import math
import os
import statistics
import sys
import time
from pathlib import Path

root = Path(sys.argv[1]).resolve()
repeats = int(sys.argv[2]) if len(sys.argv) > 2 else 30
artifacts = root / "results/linux-x86_64/artifacts"
out = root / "results/linux-x86_64"
rows = []


def run(path):
    start = time.perf_counter_ns()
    pid = os.fork()
    if pid == 0:
        os.execv(str(path), [str(path)])
    waited, status, usage = os.wait4(pid, 0)
    wall_ns = time.perf_counter_ns() - start
    rc = os.waitstatus_to_exitcode(status)
    if rc != 0:
        raise RuntimeError(f"{path} returned {rc}")
    return {
        "wall_ns": wall_ns,
        "cpu_user_ns": int(usage.ru_utime * 1e9),
        "cpu_system_ns": int(usage.ru_stime * 1e9),
        "minor_faults": usage.ru_minflt,
        "major_faults": usage.ru_majflt,
        "maxrss_kib": usage.ru_maxrss,
        "exit_code": rc,
    }


for count in (10, 100, 1000, 5000):
    path = artifacts / f"corpus-{count}-pie"
    run(path)  # one unmeasured fresh-process warm-up
    for repetition in range(1, repeats + 1):
        rows.append({"functions": count, "repetition": repetition,
                     "scenario": "elf_pie_fresh_process", "status": "PASS",
                     "artifact_bytes": path.stat().st_size, **run(path)})

fields = list(rows[0])
with (out / "pie-execution.csv").open("w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)


def p95(vals):
    return sorted(vals)[max(0, math.ceil(0.95 * len(vals)) - 1)]


with (out / "pie-execution-summary.md").open("w") as f:
    f.write("# ELF PIE execution, fresh process\n\n")
    f.write("Each artifact is executed once as warm-up, then in 30 new processes. "
            "The workload verifies its expected result by returning zero. "
            "Linux runs in QEMU TCG on Apple M2 Ultra; page cache remains warm.\n\n")
    f.write("| Functions | Median wall ms | p95 ms | Min ms | SD ms | Median CPU ms | Median RSS KiB |\n")
    f.write("|---:|---:|---:|---:|---:|---:|---:|\n")
    for count in (10, 100, 1000, 5000):
        group = [r for r in rows if r["functions"] == count]
        wall = [r["wall_ns"] / 1e6 for r in group]
        cpu = [(r["cpu_user_ns"] + r["cpu_system_ns"]) / 1e6 for r in group]
        rss = [r["maxrss_kib"] for r in group]
        f.write(f"| {count} | {statistics.median(wall):.3f} | {p95(wall):.3f} | "
                f"{min(wall):.3f} | {statistics.stdev(wall):.3f} | "
                f"{statistics.median(cpu):.3f} | {statistics.median(rss):.0f} |\n")
