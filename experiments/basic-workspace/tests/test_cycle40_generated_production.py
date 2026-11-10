"""Deterministic generator checks for the Cycle40 cross-gateway campaign."""
from __future__ import annotations
import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "pi-integration" / "cycle40_generated_production.py"
SPEC = importlib.util.spec_from_file_location("cycle40_generated_production", SCRIPT)
cycle40 = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(cycle40)


def test_seeded_program_generation_is_reproducible_and_topologically_valid():
    for i in range(1, 17):
        a = cycle40.generated_case(i, 40000 + i)
        b = cycle40.generated_case(i, 40000 + i)
        assert a == b
        assert len(a["functions"]) == {"single_edge": 2, "shared_provider": 3,
            "chain": 3, "fanout_and_downstream": 4}[a["topology"]]
        handles = {f["portable_handle"] for f in a["functions"]}
        assert len(handles) == len(a["functions"])
        for edge in a["edges"]:
            assert edge["caller_handle"] in handles and edge["callee_handle"] in handles
        assert a["final_cap"] < a["initial_cap"]
        assert len(a["inputs"]) == len(set(a["inputs"]))


def test_independent_specification_exercises_edit_boundaries_and_transitive_callers():
    case = cycle40.generated_case(4, 40004)
    assert case["topology"] == "fanout_and_downstream"
    before = cycle40.math_values(case, case["initial_cap"] + 1)
    after = cycle40.math_values(case, case["initial_cap"] + 1, maintained=True)
    assert before[case["functions"][0]["portable_handle"]] == case["initial_cap"]
    assert after[case["functions"][0]["portable_handle"]] == case["final_cap"]
    assert before != after
    assert case["inputs"] == sorted(set(case["inputs"]))


def test_second_seed_configuration_changes_numeric_spec_without_changing_grammar():
    first = cycle40.generated_case(1, 40001)
    second = cycle40.generated_case(1, 140001)
    assert first["topology"] == second["topology"]
    assert first["seed"] != second["seed"]
    assert first["initial_cap"] != second["initial_cap"] or first["initial_thresholds"] != second["initial_thresholds"]
