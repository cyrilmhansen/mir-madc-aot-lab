#!/usr/bin/env python3
"""Bounded fixed-seed semantic replay and MIR workload variants for Cycle38."""
from __future__ import annotations

import copy
import argparse
import json
import random
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
from basic_workspace.model import Workspace
from basic_workspace.mir_execution import MirExecutionService
from basic_workspace.portable_replay import replay_constructive_stream
from basic_workspace.projection import build_projection, projection_semantics
from cycle20_gateway import senior


ATTEMPT = HERE / "results/cycle38-longitudinal-stress/production-bridge-attempt-07"
EXECUTOR = MirExecutionService(timeout=20)


def load(mission):
    path = ATTEMPT / mission / "maintenance/gateway-evidence/constructive-operations.json"
    return json.loads(path.read_text(encoding="utf-8"))


def expected(mission, cap, threshold, x):
    normalized = min(cap, max(0, x))
    if mission == "mission-a":
        excellent = float(normalized >= 90)
        return {"bounded_score.function": float(normalized), "is_passing.function": float(normalized >= threshold),
            "is_excellent.function": excellent, "high_priority.function": excellent}
    senior = float(normalized >= threshold)
    return {"normalized_age.function": float(normalized), "is_senior.function": senior, "senior_flag.function": senior}


def main():
    global ATTEMPT
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt",type=Path,default=ATTEMPT)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args(); ATTEMPT=args.attempt.resolve()
    # An explicit seed and bounded ranges make these variations reproducible.
    rng = random.Random(38001)
    configs = []
    for mission in ("mission-a", "mission-b"):
        for index in range(6):
            if mission == "mission-a":
                cap = [74, 79, 82, 86, 92, 97][index]
                threshold = rng.randint(max(1, cap - 14), cap - 2)
                inputs = sorted(set([-20, -1, 0, 1, threshold - 1, threshold, cap - 1, cap, cap + 1, 89, 90, 99, 101, 150]))
            else:
                cap = [43, 51, 58, 63, 71, 88][index]
                threshold = rng.randint(max(1, cap - 10), cap - 1)
                inputs = sorted(set([-10, -1, 0, threshold - 1, threshold, cap - 1, cap, cap + 1, 64, 65, 80, 100, 150]))
            configs.append({"mission": mission, "variant": index + 1, "cap": cap, "threshold": threshold, "inputs": inputs})

    rows = []
    for config in configs:
        mission = config["mission"]
        stream = load(mission)
        operations = copy.deepcopy(stream["operations"])
        edit = operations[-1]
        if edit["operation"] != "edit_numeric_literals" or len(edit["edits"]) != 3:
            raise RuntimeError("Cycle38 workload history does not end in the expected three-target canonical edit")
        edit["edits"][0]["replacement_value"] = config["cap"]
        edit["edits"][1]["replacement_value"] = config["cap"]
        edit["edits"][2]["replacement_value"] = config["threshold"]
        started = time.perf_counter()
        ws = Workspace()
        doc = ws.create_empty_document(f"memory://cycle38/workload/{mission}/{config['variant']}.bas")["document_id"]
        replay = replay_constructive_stream(ws, doc, operations, expected_final_handles=stream["portable_handles"],
            expected_retired_handles=stream.get("retired_handles", []), expected_start_revision=1)
        replay_ms = (time.perf_counter() - started) * 1000
        expected_rows = {}; observed_rows = {}
        for x in config["inputs"]:
            expected_rows[str(x)] = expected(mission, config["cap"], config["threshold"], x)
            observed_rows[str(x)] = {}
            for engine in ("interp", "jit"):
                observed_rows[str(x)][engine] = {handle: EXECUTOR.execute_function(ws, doc, replay.revision,
                    replay.live_handles[handle], [x], engine)["result"] for handle in expected_rows[str(x)]}
            if observed_rows[str(x)]["interp"] != expected_rows[str(x)] or observed_rows[str(x)]["jit"] != expected_rows[str(x)]:
                raise RuntimeError(f"Independent oracle mismatch in {mission} variant {config['variant']} at {x}")
        normalized = senior.normalized_state(projection_semantics(build_projection(ws, doc, replay.revision)), replay.live_handles)
        rows.append({**config, "replay_revision": replay.revision, "portable_handles": sorted(replay.live_handles),
            "retired_handles": replay.retired_handles, "dependency_edges": senior.candidate_call_edges(normalized),
            "oracle": expected_rows, "interpreter_and_jit": observed_rows, "oracle_match": True,
            "replay_ms": replay_ms, "coverage": "canonical replay plus independent arithmetic oracle and both MIR engines; not a separate production authorization run"})
    output = {"schema": "basic-workspace.cycle38-generated-workloads", "version": 1,
        "seed": 38001, "variant_count": len(rows), "mission_specific_production_changes": 0,
        "generation_rule": "six explicit cap choices per mission; threshold chosen by seeded random.Random(38001) within documented bounded intervals; corpus includes adjacent threshold/cap values",
        "all_passed": all(row["oracle_match"] for row in rows), "workloads": rows}
    path = args.output.resolve()
    if path.exists(): raise SystemExit(f"Refusing to overwrite generated workload evidence: {path}")
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"variant_count": len(rows), "all_passed": output["all_passed"],
        "median_replay_ms": sorted(row["replay_ms"] for row in rows)[len(rows)//2]}, indent=2))


if __name__ == "__main__": main()
