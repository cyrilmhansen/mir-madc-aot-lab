#!/usr/bin/env python3
"""Repeated deterministic latency measurements for Cycle34 v1 and v2 maintenance."""
from __future__ import annotations
import json, pathlib, statistics, sys, tempfile, time
HERE = pathlib.Path(__file__).resolve().parent
RESULTS = HERE / "results/cycle34-cross-function-authorization"
sys.path.insert(0, str(HERE.parent)); sys.path.insert(0, str(HERE))
from cycle20_gateway import Cycle20Gateway

def elapsed(fn):
    start = time.perf_counter_ns(); value = fn()
    return (time.perf_counter_ns() - start) / 1_000_000, value

def sample(version, contract):
    row = {}
    with tempfile.TemporaryDirectory(prefix=f"atlas-cycle34-perf-{version}-", dir="/var/tmp") as temp:
        ms, gateway = elapsed(lambda: Cycle20Gateway(pathlib.Path(temp) / "gateway", contract_path=contract))
        row["gateway_baseline_reconstruction_ms"] = ms
        ms, _ = elapsed(lambda: gateway.handle("discover_functions", {}, "discover"))
        row["target_discovery_ms"] = ms
        edits = [{"target": item["target"], "expected_value": item["expected_original_value"],
            "replacement_value": item["replacement_constraint"]["values"][0]} for item in gateway.contract["authorized_targets"]]
        if gateway.contract["version"] == 1:
            request = {"expected_revision": 3, "function_handle": "clamp_score.function", "edits": edits}
        else:
            request = {"expected_revision": 3, "scope_mode": "per_target", "edits": edits}
        ms, preview = elapsed(lambda: gateway.handle("preview_semantic_edit", request, "preview"))
        if not preview.get("ok"): raise RuntimeError(preview)
        row["authorization_and_preview_ms"] = ms
        ms, commit = elapsed(lambda: gateway.handle("commit_preview", {"transaction_id": preview["transaction_id"]}, "commit"))
        if not commit.get("committed"): raise RuntimeError(commit)
        row["commit_and_revalidation_ms"] = ms
        ms, validation = elapsed(lambda: gateway.validate_current(4))
        if not validation.get("mission_complete"): raise RuntimeError(validation)
        row["host_oracle_and_fresh_replay_ms"] = ms
    return row

def main():
    repeats = 5
    source = {"legacy_single_function_v1": HERE / "contracts/numeric-edit/cycle20-cap50.json",
        "cross_function_v2": RESULTS / "primary-contract.json"}
    measurements = {name: [sample(name, path) for _ in range(repeats)] for name, path in source.items()}
    summary = {}
    for name, samples in measurements.items():
        keys = samples[0]
        summary[name] = {key: {"median_ms": round(statistics.median(row[key] for row in samples), 3),
            "min_ms": round(min(row[key] for row in samples), 3), "max_ms": round(max(row[key] for row in samples), 3)}
            for key in keys}
    output = {"schema": "basic-workspace.cycle34-performance", "version": 1,
        "runs_per_mode": repeats, "environment": "same local Linux process/runtime; process launch excluded",
        "raw_samples": measurements, "summary": summary}
    (RESULTS / "performance.json").write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))

if __name__ == "__main__": main()
