# Coverage and limits

## Executed semantic corpus

`coverage-matrix.json` summarizes 120 distinct cases, round-robin across seven template families: clamp, `>=` predicate, `<` predicate, dependent predicate, sequential override, two callees, and a dependency chain. Each case contains one to three functions, a canonical constructor history, one portable-identity rename, and one bounded literal edit. The corpus covers five dependency shapes/depth strata, all function-count classes, threshold/cap neighbors, negative/zero/positive values, and deterministic interior points.

All 120 cases were checked on their committed stream and a fresh replay through the independent mathematical oracle, MIR interpreter and MIR JIT. The actual per-case input and output corpus is in `differential-results.jsonl`.

## Production tier

Sixteen preselected cases traversed TypeScript tool schema → JSONL → Cycle19 sequence gateway. They comprised 30 committed constructor steps across all seven families. The selected one-step/two-to-three-step constructor runs had separate host-owned sequence contracts, independent expected results and checkpoint progression.

The selected generated workflows exercised Cycle19 creation authorization. They did **not** pass the generated rename and literal-edit suffixes through Cycle37 and Cycle20 authorization. Those operations were checked through canonical replay and differential execution; existing historical tests still exercise the production rename and maintenance bridges on their registered contracts. Therefore this campaign does not establish 16 generated heterogeneous production workflows. That remains the largest untested composition gap.

## Negative and metamorphic coverage

The production bridge generated 100 rejected requests: 30 stale revisions, 30 unauthorized function names, 10 invented callees, and 30 unknown semantic fields rejected by TypeBox. All 70 Python gateway denials reported no mutation; TypeScript schema denials occurred before the accepted request at the same revision. Two focused unit controls cover unsupported replay operations and wrong expected literals. The aggregate is 102 controls; see `negative-controls.json`.

Twenty-eight generated cases checked rename invariance, literal edit inversion and independent replay determinism. A separate multi-function fixture changed a provider output at a boundary and observed the dependent caller change in both MIR engines while the caller's normalized structure remained unchanged.

## Explicitly unsupported or untested

- The production edit target interface accepts direct comparison numeric literals; it does not edit a negative literal through a unary-minus node. Generator edit targets therefore stay positive, even when other corpus thresholds are near zero.
- Generated cross-gateway rename→maintenance combinations were not run through all three gateways. This was kept separate from the 16 genuine Cycle19 bridge cases rather than represented as complete production workflows.
- No Pi/Sushi model inference was run.
- Bounded finite cases are not a proof over all integer or floating-point inputs.
- No floating-point, NaN or infinity workloads were admitted.
- Performance has no identical historical baseline for every substage.
