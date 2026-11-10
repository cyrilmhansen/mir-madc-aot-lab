# Generator

`cycle40_generated_production.py` generates from a separate arithmetic graph: one clamp with lower bound zero and an integer upper cap, followed by one to three `>=` predicates. Each predicate calls exactly one earlier function. The deterministic topology schedule is single edge, shared-provider fan-out, a three-node chain, then fan-out plus downstream caller. Names, portable stems, cap, thresholds, edit values and boundary corpus derive from each frozen seed.

The generator creates typed constructor JSON, but does not apply it to the authoritative production Workspace. Cycle19 receives each constructor through the active TypeScript handler and JSONL bridge. Contract data is created host-side from the mathematical graph. A provider rename and a three-target atomic numeric edit likewise use the existing Cycle37 and Cycle20 TypeScript probes.

The initial campaign is seeds 40001–40016. The second configuration uses seed offset 100000, producing seeds 140001–140008. Integer arithmetic is exact. Inputs include values adjacent to the initial and final cap and every relevant predicate threshold, plus fixed extrema and three seeded interior values.

Unsupported Cycle39 shapes are classified in `COMPATIBILITY-MATRIX.md`; this campaign does not silently convert them into the supported grammar.
