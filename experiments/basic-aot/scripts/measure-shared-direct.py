#!/usr/bin/env python3
"""Thirty-run stage and runtime comparison for Cycle 6 direct MIR DSOs."""
from __future__ import annotations

import json
import pathlib
import platform
import statistics
import subprocess
import time
import os

HERE = pathlib.Path(__file__).resolve().parent.parent
LAB = HERE.parents[1]
OUT = HERE / "results" / "shared"
MEASURE = OUT / "cycle6-measure"
MEASURE.mkdir(parents=True, exist_ok=True)
N = 30
SOURCE = HERE / "tests/shared/libbasicdemo-direct.bas"
TIMED_PREFIX = OUT / "cycle6-timed"
MIR = pathlib.Path(str(TIMED_PREFIX) + ".mir")
OBJ = pathlib.Path(str(TIMED_PREFIX) + ".o")
BASE_OBJ = OUT / "libbasicdemo-direct.o"
WRAPPER = OUT / "basic-shared-api-madc.o"
RUNTIME = OUT / "libbasicrt.so"
DIRECT = OUT / "libbasicdemo-mir.so"
GCC_SO = OUT / "libbasicdemo-direct-gcc-reference.so"
COMPILER = LAB / "vendor/mir-upstream-54fa3e409224bbc6ffdbc421a80f02ff76f76ce6/build/basic/basicc"
ADAPTER = HERE / "build/mir-to-elf"
MERGER = HERE / "build/mir-objects-to-shared"
NUMERIC_CLIENT = MEASURE / "shared-client"
STRING_CLIENT = OUT / "bench-strings-client"


def timed(command: list[str]) -> float:
    start = time.perf_counter_ns()
    subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
    return (time.perf_counter_ns() - start) / 1e6


def summary(values: list[float], unit: str = "ms") -> dict[str, float | int | str]:
    return {"unit": unit, "n": len(values), "median": statistics.median(values),
            "min": min(values), "max": max(values)}


def timed_client(command: list[str], repetitions: int = N) -> list[dict[str, float]]:
    samples = []
    for _ in range(repetitions):
        proc = subprocess.run(command, text=True, capture_output=True, check=True)
        values = {}
        for line in proc.stdout.splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                try:
                    values[key] = float(value)
                except ValueError:
                    pass
            elif line.startswith("{"):
                values.update({key: float(value) for key, value in json.loads(line).items()
                               if isinstance(value, (int, float))})
        samples.append(values)
    return samples


def median_keys(samples: list[dict[str, float]]) -> dict[str, dict[str, float | int | str]]:
    keys = sorted(key for key in set.intersection(*(set(s) for s in samples))
                  if key not in {"iterations", "checksum"})
    return {key: summary([s[key] for s in samples], "ns") for key in keys}


def main() -> None:
    start = time.perf_counter_ns()
    subprocess.run(["bash", str(HERE / "scripts/build-runtime.sh")],
                   env={**os.environ, "FORCE_REBUILD": "1"},
                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
    runtime_archive_build_ms = (time.perf_counter_ns() - start) / 1e6
    start = time.perf_counter_ns()
    subprocess.run(["bash", str(HERE / "scripts/build-runtime-shared-dso.sh"),
                    str(HERE / "runtime/libbasicrt-shared.a"), str(BASE_OBJ), str(WRAPPER),
                    str(RUNTIME)], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
    runtime_dso_build_ms = (time.perf_counter_ns() - start) / 1e6

    names = ["SQUARE", "ADD", "STRLEN", "REPORT", "LITERAL$", "ECHO$", "LOCAL$",
             "CONCAT$", "UPPERTEST$", "EMPTY$", "FNBORROWED$"]
    direct_args = [str(MERGER), "--needed", "libbasicrt.so", "--needed", "libc.so.6",
                   "--needed", "libm.so.6", "--runpath", "$ORIGIN"]
    for name in ["CONCAT$", "ECHO$", "EMPTY$", "FNBORROWED$", "LITERAL$", "LOCAL$", "UPPERTEST$"]:
        direct_args += ["--hide", name]
    for name in ["basic_concat", "basic_data_fini", "basic_data_init", "basic_enable_line_tracking",
                 "basic_free", "basic_len", "basic_print", "basic_print_str", "basic_set_line",
                 "basic_strdup", "basic_upper", "free", "malloc", "memcpy", "strlen"]:
        direct_args += ["--require", name]
    direct_args += [str(DIRECT), str(BASE_OBJ), str(WRAPPER)]

    compiler_samples = [timed([str(COMPILER), "-S", "-o", str(TIMED_PREFIX), str(SOURCE)])
                        for _ in range(N)]
    object_args = [str(ADAPTER)]
    for name in names:
        object_args += ["--export", name]
    object_args += [str(MIR), str(OBJ)]
    object_samples = [timed(object_args) for _ in range(N)]
    direct_samples = [timed(direct_args) for _ in range(N)]

    gcc_command = ["cc", "-shared", "-Wl,--no-undefined", "-Wl,-z,defs", "-Wl,-z,text",
                   "-Wl,-z,relro", "-Wl,-z,now", "-Wl,--gc-sections", "-Wl,--exclude-libs,ALL",
                   "-Wl,--version-script=" + str(OUT / "basic-shared-api.map"), str(BASE_OBJ),
                   str(OUT / "basic-module-lifecycle.o"), str(OUT / "basic-shared-api.o"),
                   str(HERE / "runtime/libbasicrt-shared.a"), "-lm", "-o", str(GCC_SO)]
    gcc_samples = [timed(gcc_command) for _ in range(N)]

    subprocess.run(["cc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                    str(HERE / "tests/shared/shared-client.c"), "-ldl", "-lm", "-o",
                    str(NUMERIC_CLIENT)], check=True)
    numeric_direct = timed_client([str(NUMERIC_CLIENT), str(DIRECT), "1000000"])
    numeric_gcc = timed_client([str(NUMERIC_CLIENT), str(GCC_SO), "1000000"])
    string_direct = timed_client([str(STRING_CLIENT), str(DIRECT), "100000"])
    string_gcc = timed_client([str(STRING_CLIENT), str(OUT / "libbasicdemo-strings.so"), "100000"])

    data = {
        "host": subprocess.check_output(["uname", "-a"], text=True).strip(),
        "platform": platform.platform(), "repetitions": N,
        "notes": ["Each stage runs in 30 fresh processes after artifacts/runtime are built.",
                  "Runtime DSO build is a one-time build and excluded from warm measurements.",
                  "Numeric and string tests use 30 fresh client processes, 1,000,000 SQUARE calls and 100,000 BASIC_UPPER calls.",
                  "Direct and GCC deployment sizes are not packaging-equivalent; direct adds a shared runtime DSO."],
        "stage_ms": {"basic_to_mir": summary(compiler_samples),
                     "mir_to_et_rel": summary(object_samples),
                     "mir_object_capture_and_direct_et_dyn_emit": summary(direct_samples),
                     "gcc_final_link": summary(gcc_samples),
                     "one_time_gcc_runtime_archive_build": {
                         "unit": "ms", "n": 1, "elapsed": runtime_archive_build_ms},
                     "one_time_gcc_runtime_dso_build": {
                         "unit": "ms", "n": 1, "elapsed": runtime_dso_build_ms}},
        "runtime_ns_per_call": {"direct_mir": median_keys(numeric_direct),
                                "gcc_linked": median_keys(numeric_gcc),
                                "direct_string": median_keys(string_direct),
                                "gcc_string_reference": median_keys(string_gcc)},
        "raw_samples": {"basic_to_mir_ms": compiler_samples,
                        "mir_to_et_rel_ms": object_samples,
                        "direct_emit_ms": direct_samples,
                        "gcc_link_ms": gcc_samples,
                        "numeric_direct": numeric_direct,
                        "numeric_gcc": numeric_gcc,
                        "string_direct": string_direct,
                        "string_gcc": string_gcc},
        "artifacts_bytes": {"direct_basic_dso": DIRECT.stat().st_size,
                            "shared_runtime_dso": RUNTIME.stat().st_size,
                            "direct_deployment_total": DIRECT.stat().st_size + RUNTIME.stat().st_size,
                            "gcc_reference_dso": GCC_SO.stat().st_size,
                            "direct_et_rel": BASE_OBJ.stat().st_size},
        "direct_dependencies": subprocess.check_output(["readelf", "-d", str(DIRECT)], text=True).splitlines(),
    }
    path = MEASURE / "summary.json"
    path.write_text(json.dumps(data, indent=2) + "\n")
    print(path)
    print(json.dumps(data["stage_ms"], indent=2))
    print(json.dumps(data["runtime_ns_per_call"], indent=2))


if __name__ == "__main__":
    main()
