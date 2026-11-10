# Cycle 41 audit and pre-registration

## Baseline

Verified HEAD: `6da6d2816afdd1069288265eb104f0f24e8ef377` on `experiment/mir-aot-correctness-cycle3`. Unrelated MPDecimal, replay, control-flow and Pi evidence changes remain untouched.

## Validation-path finding

Cycle20's strict contract validation admits only `clamp`, `threshold_call`, and `score_class_call` declarations for v1/v2. `_oracle_value` recursively evaluates those host declarations. `_expected_observations` feeds expected output maps to both preview candidate comparison and `validate_current`; `_run_observations` is the single shared MIR interpreter/JIT execution loop. Candidate authorization separately enforces exact targets, revisions, candidate structure, token identities, unchanged functions and dependency edges. The verified continuation binds the destination contract digest before baseline activation.

Cycle35 creation uses a finite input list with host-calculated expected result maps per revision. Cycle39 has an independent mathematical evaluator over seven fixed numeric template families. This makes a bounded table a data-format gap, not a Workspace semantic limitation.

## Frozen design

Add strict maintenance contract v3. Top-level fields match v2 and retain `scope_mode: per_target`. Validation fields are exactly `mode`, `inputs`, `functions`, `expected_results`; mode is `finite_expected_results`. Functions contain only unique `function_handle`/`result_key` pairs. Rows are positional and have exactly those result keys. Bounds: 1–64 unique finite numeric inputs, 1–8 unique functions, at most 512 result cells; Booleans and non-finite values reject. V1 and v2 validation paths are unchanged.

The gateway maps the host table into the existing expected-observation structure. It adds no expression evaluator, mutation, transaction, replay or model-facing tool. Authenticated handoff/continuation digest validation remains responsible for binding the destination contract. Handle resolution occurs after replay in the authenticated Workspace.

## Coverage plan frozen before generated runs

Target 16 confirmatory workflows balanced across Cycle39's raw `>=`, raw `<`, sequential-override and two-callee families; 8 second-seed workflows; existing Cycle39 compatible families retained as regression controls. Each selected workflow uses Cycle19 construction, Cycle37 rename, verified continuation, and Cycle20 v3 multi-target maintenance via the actual TypeScript/JSONL handlers. Seeds, selection and bounds are in `campaign-config.json`.
