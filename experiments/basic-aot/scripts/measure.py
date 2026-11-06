#!/usr/bin/env python3
"""Process timing/RSS comparison for validated double-mode sample programs."""
import json
import os
import pathlib
import statistics
import subprocess
import time

here = pathlib.Path(__file__).resolve().parent.parent
lab = here.parents[1]
root = here / "upstream/basic"
mirroot = lab / "vendor/mir-upstream-54fa3e409224bbc6ffdbc421a80f02ff76f76ce6"
basicc = mirroot / "build/basic/basicc"
adapter = here / "results/aot/mir-to-elf"
results = here / "results/measurements"
results.mkdir(parents=True, exist_ok=True)
runs = int(os.environ.get("RUNS", "30"))
compile_runs = int(os.environ.get("COMPILE_RUNS", "5"))
programs = ("hello", "arith", "loop")
report = {"runs": runs, "compile_runs": compile_runs, "programs": {}}


def execute(argv):
    rss_path = results / "rss-current.txt"
    start = time.perf_counter_ns()
    rss_path.unlink(missing_ok=True)
    proc = subprocess.run(
        ["/usr/bin/time", "-f", "%M", "-o", str(rss_path), *map(str, argv)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    elapsed = (time.perf_counter_ns() - start) / 1e6
    peak_kib = int(rss_path.read_text().strip())
    rss_path.unlink()
    if proc.returncode:
        raise RuntimeError(f"failed ({proc.returncode}): {argv}\n{proc.stderr.decode(errors='replace')}")
    return elapsed, peak_kib, proc.stdout


for name in programs:
    src = root / "tests/programs" / f"{name}.bas"
    expected = (root / "tests/expected" / f"{name}.out").read_bytes()
    native = here / "results/aot" / f"{name}-native"
    cases = {
        "interp": [str(basicc), str(src)],
        "jit": [str(basicc), "-j", str(src)],
        "aot": [str(native)],
    }
    result = {}
    for mode, argv in cases.items():
        times, first_output_times, rss_values = [], [], []
        for _ in range(runs):
            elapsed, peak, output = execute(argv)
            if output != expected:
                raise RuntimeError(f"output mismatch: {name} {mode}")
            times.append(elapsed)
            rss_values.append(peak)
            start = time.perf_counter_ns()
            proc = subprocess.Popen(
                ["stdbuf", "-oL", *argv], stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            first_line = proc.stdout.readline()
            first_output_times.append((time.perf_counter_ns() - start) / 1e6)
            rest = proc.stdout.read()
            stderr = proc.stderr.read()
            proc.wait()
            if proc.returncode or first_line + rest != expected:
                raise RuntimeError(f"first-output run failed: {name} {mode}: {stderr!r}")
        result[mode] = {
            "median_ms": statistics.median(times),
            "p95_ms": sorted(times)[max(0, int(len(times) * .95) - 1)],
            "median_first_output_ms_line_buffered": statistics.median(first_output_times),
            "median_peak_rss_kib": statistics.median(rss_values),
            "executable_bytes": pathlib.Path(argv[0]).stat().st_size,
        }

    base = results / name
    compile_parts = {
        "basicc_s_median_ms": [],
        "mir_to_object_median_ms": [],
        "gcc_link_median_ms": [],
    }
    compile_commands = (
        ("basicc_s_median_ms", [str(basicc), "-S", "-o", str(base), str(src)]),
        ("mir_to_object_median_ms", [str(adapter), str(base) + ".mir", str(base) + ".o"]),
        ("gcc_link_median_ms", [
            "cc", "-O2", "-ffunction-sections", "-fdata-sections",
            "-I", str(lab / "madc/third_party/mir"),
            "-I", str(root / "include"), "-I", str(root / "src"),
            "-I", str(root / "src/vendor"), "-I", str(root / "src/vendor/kitty"),
            "-I", str(root / "src/vendor/libdfp"), "-Wl,--gc-sections",
            str(base) + ".o", str(root / "src/basic_runtime.c"),
            str(root / "src/basic_pool.c"), str(root / "src/vendor/kitty/kitty.c"),
            str(root / "src/vendor/kitty/lodepng.c"), "-lm", "-o", str(base) + "-native",
        ]),
    )
    for _ in range(compile_runs):
        for key, command in compile_commands:
            start = time.perf_counter_ns()
            subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            compile_parts[key].append((time.perf_counter_ns() - start) / 1e6)
    result["aot_compile"] = {key: statistics.median(values) for key, values in compile_parts.items()}
    result["aot_compile"]["total_median_ms"] = sum(result["aot_compile"].values())
    result["aot_compile"]["mir_bytes"] = base.with_suffix(".mir").stat().st_size
    result["aot_compile"]["bmir_bytes"] = base.with_suffix(".bmir").stat().st_size
    result["aot_compile"]["object_bytes"] = base.with_suffix(".o").stat().st_size
    result["aot_compile"]["executable_bytes"] = pathlib.Path(str(base) + "-native").stat().st_size
    report["programs"][name] = result

out_path = results / "summary.json"
out_path.write_text(json.dumps(report, indent=2) + "\n")
print(out_path)
