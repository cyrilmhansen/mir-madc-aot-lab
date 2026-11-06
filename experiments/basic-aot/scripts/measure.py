#!/usr/bin/env python3
"""Fresh-process BASIC comparisons and separated cached-runtime AOT phases."""
import json
import os
import pathlib
import statistics
import subprocess
import time

here = pathlib.Path(__file__).resolve().parent.parent
lab = here.parents[1]
rev = "54fa3e409224bbc6ffdbc421a80f02ff76f76ce6"
mirroot = lab / f"vendor/mir-upstream-{rev}"
basicroot = here / "upstream/basic"
basicc = mirroot / "build/basic/basicc"
adapter = here / "build/mir-to-elf"
runtime = here / "runtime/libbasicrt.a"
results = here / "results/measurements-cycle2"
results.mkdir(parents=True, exist_ok=True)
runs = int(os.environ.get("RUNS", "30"))
compile_runs = int(os.environ.get("COMPILE_RUNS", "30"))
programs = {
    "hello": (basicroot / "tests/programs/hello.bas", basicroot / "tests/expected/hello.out"),
    "arith": (basicroot / "tests/programs/arith.bas", basicroot / "tests/expected/arith.out"),
    "loop": (basicroot / "tests/programs/loop.bas", basicroot / "tests/expected/loop.out"),
    "data-restore": (here / "tests/data-restore.bas", here / "tests/expected/data-restore.out"),
    "funcproc": (basicroot / "tests/programs/funcproc.bas", basicroot / "tests/expected/funcproc.out"),
    "array-2d": (here / "tests/features/array-2d.bas", here / "tests/expected/array-2d.out"),
}
report = {
    "host": subprocess.check_output(["uname", "-a"], text=True).strip(),
    "arch": subprocess.check_output(["uname", "-m"], text=True).strip(),
    "runs_per_mode": runs,
    "compile_runs_per_phase": compile_runs,
    "runtime_archive": str(runtime.relative_to(lab)),
    "runtime_archive_bytes": runtime.stat().st_size,
    "programs": {},
}


def timed(command, *, cwd=None, env=None):
    start = time.perf_counter_ns()
    proc = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          cwd=cwd, env=env, check=False)
    elapsed = (time.perf_counter_ns() - start) / 1e6
    if proc.returncode:
        raise RuntimeError(f"command failed ({proc.returncode}): {command}\n"
                           f"{proc.stderr.decode(errors='replace')}")
    return elapsed, proc.stdout, proc.stderr


def summarize(values):
    return {"median_ms": statistics.median(values),
            "p95_ms": sorted(values)[max(0, int(len(values) * .95) - 1)]}


runtime_start = time.perf_counter_ns()
subprocess.run([str(here / "scripts/build-runtime.sh")], check=True,
               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
report["runtime_cached_check_ms"] = (time.perf_counter_ns() - runtime_start) / 1e6
runtime_start = time.perf_counter_ns()
subprocess.run([str(here / "scripts/build-runtime.sh")], check=True,
               env={**os.environ, "FORCE_REBUILD": "1"},
               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
report["runtime_full_build_once_ms"] = (time.perf_counter_ns() - runtime_start) / 1e6

for name, (source, expected_path) in programs.items():
    expected = expected_path.read_bytes()
    base = results / name
    native = pathlib.Path(str(base) + "-native")
    compile_samples = {key: [] for key in ("frontend_mir", "mir_object", "native_link")}
    for index in range(compile_runs):
        mir = pathlib.Path(str(base) + ".mir")
        obj = pathlib.Path(str(base) + ".o")
        bmir = pathlib.Path(str(base) + ".bmir")
        start = time.perf_counter_ns()
        subprocess.run([str(basicc), "-S", "-o", str(base), str(source)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
        compile_samples["frontend_mir"].append((time.perf_counter_ns() - start) / 1e6)
        start = time.perf_counter_ns()
        subprocess.run([str(adapter), str(mir), str(obj)], stdout=subprocess.DEVNULL,
                       stderr=subprocess.PIPE, check=True)
        compile_samples["mir_object"].append((time.perf_counter_ns() - start) / 1e6)
        start = time.perf_counter_ns()
        subprocess.run(["cc", str(obj), "-Wl,--gc-sections", str(runtime), "-lm",
                        "-o", str(native)], stdout=subprocess.DEVNULL,
                       stderr=subprocess.PIPE, check=True)
        compile_samples["native_link"].append((time.perf_counter_ns() - start) / 1e6)
    compile_summary = {key: summarize(values) for key, values in compile_samples.items()}
    compile_summary["total_median_ms"] = sum(v["median_ms"] for v in compile_summary.values())
    compile_summary["mir_bytes"] = pathlib.Path(str(base) + ".mir").stat().st_size
    compile_summary["bmir_bytes"] = pathlib.Path(str(base) + ".bmir").stat().st_size
    compile_summary["object_bytes"] = pathlib.Path(str(base) + ".o").stat().st_size
    compile_summary["executable_bytes"] = native.stat().st_size

    modes = {
        "interpreter": [str(basicc), str(source)],
        "jit": [str(basicc), "-j", str(source)],
        "aot": [str(native)],
    }
    mode_summary = {}
    for mode, command in modes.items():
        times, rss, first_output = [], [], []
        for _ in range(runs):
            rss_file = results / "rss-current.txt"
            rss_file.unlink(missing_ok=True)
            elapsed, output, _ = timed(["/usr/bin/time", "-f", "%M", "-o", str(rss_file), *command])
            if output != expected:
                raise RuntimeError(f"output mismatch: {name} {mode}: {output!r} != {expected!r}")
            times.append(elapsed)
            rss.append(int(rss_file.read_text().strip()))
            rss_file.unlink(missing_ok=True)
            start = time.perf_counter_ns()
            proc = subprocess.Popen(["stdbuf", "-oL", *command], stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
            line = proc.stdout.readline()
            first_output.append((time.perf_counter_ns() - start) / 1e6)
            rest, stderr = proc.stdout.read(), proc.stderr.read()
            if proc.wait() or line + rest != expected:
                raise RuntimeError(f"first-output run failed: {name} {mode}: {stderr!r}")
        mode_summary[mode] = {
            **summarize(times),
            "median_time_to_first_output_ms": statistics.median(first_output),
            "median_max_rss_kib": statistics.median(rss),
            "executable_bytes": pathlib.Path(command[0]).stat().st_size,
        }
    ldd = subprocess.check_output(["ldd", str(native)], text=True)
    nm_undefined = subprocess.check_output(["nm", "-u", str(native)], text=True)
    report["programs"][name] = {
        "compile": compile_summary,
        "execution": mode_summary,
        "aot_ldd": ldd.splitlines(),
        "aot_has_mir_undefined_symbols": any("MIR_" in line for line in nm_undefined.splitlines()),
    }

out = results / "summary.json"
out.write_text(json.dumps(report, indent=2) + "\n")
print(out)
