#!/usr/bin/env python3
"""Run shared string wrapper timings in fresh processes and retain raw samples."""
import json
import statistics
import subprocess
import sys
from pathlib import Path

here = Path(__file__).resolve().parent.parent
out = here / "results" / "shared"
client = out / "bench-strings-client"
library = out / "libbasicdemo-strings.so"
count = int(sys.argv[1]) if len(sys.argv) > 1 else 100_000
repetitions = 30
samples = []
for _ in range(repetitions):
    result = subprocess.run([str(client), str(library), str(count)], check=True,
                            text=True, capture_output=True)
    samples.append(json.loads(result.stdout))

keys = ("basic_upper_ns", "malloc_copy_free_ns", "c_upper_malloc_free_ns")
summary = {}
for key in keys:
    values = [sample[key] for sample in samples]
    summary[key] = {
        "median": statistics.median(values),
        "min": min(values),
        "max": max(values),
    }
data = {
    "host": "Skip Linux x86-64 native",
    "repetitions": repetitions,
    "iterations_per_process": count,
    "timings": summary,
    "samples": samples,
}
(out / "string-measurements.json").write_text(json.dumps(data, indent=2) + "\n")
print(json.dumps(summary, indent=2))
