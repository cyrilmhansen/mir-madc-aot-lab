#!/usr/bin/env python3
import csv
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

client, dylib, output, repeats = sys.argv[1:]
client, dylib, output = Path(client), Path(dylib), Path(output)
repeats = int(repeats)
env = os.environ.copy()
env["DYLD_LIBRARY_PATH"] = str(dylib.parent)

def run_one():
    start = time.perf_counter_ns()
    proc = subprocess.run([str(client), str(dylib)], env=env, check=True,
                          text=True, capture_output=True)
    wall = time.perf_counter_ns() - start
    rows = list(csv.DictReader(proc.stdout.splitlines()))
    if len(rows) != 1 or rows[0]["loaded_after_close"] != "0":
        raise RuntimeError("dylib was not fully unloaded or client output was malformed")
    row = rows[0]
    row.pop("cycle", None)
    row["process_wall_ns"] = wall
    return row

run_one()  # warm up executable and filesystem pages; do not call this cold disk.
rows = []
for repetition in range(1, repeats + 1):
    row = run_one()
    row["repetition"] = repetition
    rows.append(row)
fields = ["repetition", "compute_calls", "open_ns", "dlsym_ns", "first_call_ns", "compute_ns",
          "close_ns", "loaded_before", "loaded_after_close", "runtime_loaded_after_close", "user_cpu_us",
          "system_cpu_us", "minor_faults", "major_faults", "maxrss_native_units",
          "process_wall_ns"]
with output.open("w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
walls = [int(row["process_wall_ns"]) / 1e6 for row in rows]
opens = [int(row["open_ns"]) / 1e6 for row in rows]
rss_mib = [int(row["maxrss_native_units"]) / (1024 * 1024) for row in rows]
p_major = [int(row["major_faults"]) for row in rows]
compute_us = [int(row["compute_ns"]) / 1000 for row in rows]
runtime_retained = sum(int(row["runtime_loaded_after_close"]) for row in rows)
p95 = sorted(walls)[max(0, int(0.95 * len(walls) + .999) - 1)]
summary = output.with_name("macho-load-summary.md")
summary.write_text(
    "# Mach-O dylib load pilot\n\n"
    f"Fresh process per sample, one warm-up, {repeats} measured samples. "
    "macOS page cache was left warm. The loader confirms the test dylib is absent "
    f"after `dlclose`; libmadc runtime image retained after close in {runtime_retained}/{repeats} processes.\n\n"
    f"- Median direct `dlopen`: {statistics.median(opens):.3f} ms\n"
    f"- Median process wall time: {statistics.median(walls):.3f} ms\n"
    f"- p95 process wall time: {p95:.3f} ms\n"
    f"- Minimum process wall time: {min(walls):.3f} ms\n"
    f"- Sample standard deviation: {statistics.stdev(walls):.3f} ms\n"
    f"- Median process peak RSS: {statistics.median(rss_mib):.2f} MiB (Darwin `ru_maxrss`)\n"
    f"- Median major faults per process: {statistics.median(p_major):.0f}\n"
    f"- Median compute loop time (20,000 calls): {statistics.median(compute_us):.1f} µs\n",
    encoding="utf-8")
