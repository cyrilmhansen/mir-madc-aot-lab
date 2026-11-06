#!/usr/bin/env python3
"""Thirty fresh-process measurements for the BASIC shared-library stages."""
from __future__ import annotations

import json
import os
import pathlib
import platform
import statistics
import subprocess
import time

HERE = pathlib.Path(__file__).resolve().parent.parent
LAB = HERE.parents[1]
REV = "54fa3e409224bbc6ffdbc421a80f02ff76f76ce6"
ROOT = LAB / "vendor" / f"mir-upstream-{REV}"
OUT = HERE / "results" / "shared" / "measure"
OUT.mkdir(parents=True, exist_ok=True)
SOURCE = HERE / "tests" / "shared" / "libbasicdemo.bas"
PREFIX = OUT / "libbasicdemo"
MIR = PREFIX.with_suffix(".mir")
OBJ = PREFIX.with_suffix(".o")
SO = OUT / "libbasicdemo.so"
DIRECT_SO = OUT / "libbasicdemo-direct.so"
RUNTIME = HERE / "runtime" / "libbasicrt-shared.a"
LIFECYCLE = HERE / "results" / "shared" / "basic-module-lifecycle.o"
TOOL = HERE / "build" / "mir-to-elf"
COMPILER = ROOT / "build" / "basic" / "basicc"
CLIENT = HERE / "results" / "shared" / "shared-client"
EXPORTS = ["SQUARE", "ADD", "STRLEN", "REPORT"]
N = 30
ITERATIONS = 1_000_000

def run(args: list[str]) -> tuple[int, str]:
    start = time.perf_counter_ns()
    proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True, check=True)
    return time.perf_counter_ns() - start, proc.stdout

def summary(samples: list[float], unit: str) -> dict[str, float | str]:
    return {"unit": unit, "n": len(samples), "median": statistics.median(samples),
            "min": min(samples), "max": max(samples)}

def time_stage(name: str, make_args) -> list[float]:
    values = []
    for _ in range(N):
        ns, _ = run(make_args())
        values.append(ns / 1e6)
    return values

def main() -> None:
    basic_mir = time_stage("basic_to_mir", lambda: [str(COMPILER), "-S", "-o", str(PREFIX), str(SOURCE)])
    mir_object = time_stage("mir_to_object", lambda: [str(TOOL),
        *sum((["--export", name] for name in EXPORTS), []), str(MIR), str(OBJ)])
    link = time_stage("gcc_shared_link", lambda: ["cc", "-shared", "-Wl,--no-undefined",
        "-Wl,-z,defs", "-Wl,-z,text", "-Wl,-z,relro", "-Wl,-z,now",
        "-Wl,--gc-sections", "-Wl,--exclude-libs,ALL", str(OBJ), str(LIFECYCLE),
        str(RUNTIME), "-lm", "-o", str(SO)])
    direct_emit = time_stage("mir_direct_shared_emit", lambda: [str(TOOL), "--export", "SQUARE",
        "--export", "ADD", "--direct-shared", str(MIR), str(DIRECT_SO)])

    runtime_samples: dict[str, list[float]] = {}
    for _ in range(N):
        _, stdout = run([str(CLIENT), str(SO), str(ITERATIONS)])
        for line in stdout.splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                runtime_samples.setdefault(key, []).append(float(value))

    data = {
        "host": platform.node(), "platform": platform.platform(),
        "compiler": subprocess.check_output(["cc", "--version"], text=True).splitlines()[0],
        "repetitions": N, "call_iterations_per_process": ITERATIONS,
        "shared_exports": {"SQUARE": "double(double)", "ADD": "double(double,double)",
                           "STRLEN": "double(const char *)", "REPORT": "void(double)"},
        "stages": {
            "basic_to_mir_ms": summary(basic_mir, "ms"),
            "mir_to_et_rel_object_ms": summary(mir_object, "ms"),
            "gcc_shared_link_ms": summary(link, "ms"),
            "mir_direct_shared_emit_ms": summary(direct_emit, "ms"),
            "runtime_each_fresh_process": {k: summary(v, "ns") for k, v in runtime_samples.items()},
        },
        "artifacts_bytes": {"et_rel_object": OBJ.stat().st_size, "gcc_shared": SO.stat().st_size,
                            "mir_direct_shared": DIRECT_SO.stat().st_size},
        "notes": ["30 separate compiler/linker/client processes; runtime archive is prebuilt and cached.",
                  "Client times SQUARE through a dlsym function pointer and an equivalent noinline C function.",
                  "MIR direct shared measurement is emitted separately and is not used for GCC .so timings."],
    }
    path = HERE / "results" / "shared" / "measurements.json"
    path.write_text(json.dumps(data, indent=2) + "\n")
    print(path)
    print(json.dumps(data["stages"], indent=2))

if __name__ == "__main__":
    main()
