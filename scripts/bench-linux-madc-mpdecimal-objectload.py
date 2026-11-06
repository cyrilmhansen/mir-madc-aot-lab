#!/usr/bin/env python3
import csv
import subprocess
import time
from pathlib import Path

root = Path(__file__).resolve().parent.parent
base = root / "results/linux-x86_64-native/libmpdec-cycle5"
obj = base / "madc-mir-object-corrected/libmpdec-main.o"
madc = root / "madc/bin/madc"
csv_path = base / "objectload-madc-uint128.csv"
log_path = base / "logs/objectload-madc-uint128-runs.txt"

command = [str(madc), "--no-config", str(obj)]
expected = "121932631112635269"

warmup = subprocess.run(command, text=True, capture_output=True, check=False)
if warmup.returncode != 0 or expected not in warmup.stdout:
    raise SystemExit(f"warm-up failed ({warmup.returncode}): {warmup.stderr}")

base.joinpath("logs").mkdir(parents=True, exist_ok=True)
rows = []
with log_path.open("w") as log:
    for rep in range(1, 31):
        start = time.perf_counter_ns()
        result = subprocess.run(command, text=True, capture_output=True, check=False)
        elapsed = time.perf_counter_ns() - start
        log.write(f"rep={rep} wall_ns={elapsed} status={result.returncode} stdout={result.stdout.strip()}\n")
        if result.returncode != 0 or expected not in result.stdout:
            raise SystemExit(f"run {rep} failed ({result.returncode}): {result.stderr}")
        rows.append((rep, elapsed, result.stdout.strip()))

with csv_path.open("w", newline="") as f:
    writer = csv.writer(f, lineterminator="\n")
    writer.writerow(("rep", "process_wall_ns", "result"))
    writer.writerows(rows)
