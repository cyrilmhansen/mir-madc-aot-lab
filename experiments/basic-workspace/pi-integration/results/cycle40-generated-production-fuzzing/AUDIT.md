# Cycle 40 audit (pre-execution)

## Baseline

Local HEAD is `21f85d3a5e1e927a4e97b9ca71ac8f1af71f0214` on `experiment/mir-aot-correctness-cycle3`. Existing unrelated MPDecimal, semantic-replay, control-flow and Pi evidence changes are present and are being preserved.

## Interface audit

Cycle19's host-owned creation sequence supports ordered single-function commits, discovered typed calls, host validation and checkpoint progression. Cycle37 v2 rename contracts bind one portable target and validate identity/reference preservation. Cycle36's verified handoff authenticates a completed creation stream against a separately stored host anchor and destination contract. Cycle38's verified rename continuation binds the original creation proof, committed rename suffix, destination Cycle20 contract and a second host anchor. Cycle20 v2 authorizes an exact `per_target` batch and validates it through the existing transaction kernel.

Cycle20's independent oracle vocabulary is deliberately bounded to `clamp`, `threshold_call`, and `score_class_call`. Therefore this campaign admits only clamp providers and predicates whose result is a threshold comparison over one direct function call. Sequential overrides, raw-input predicates, strict-less-than predicates, and two-callee expression shapes are outside the production maintenance oracle even where Cycle19 and MIR can represent them. Negative numeric literals are excluded as direct edit targets because the numeric target resolver addresses literal nodes, not unary-minus syntax.

## Compatibility decision

The generated production subset uses 2–4 functions: one clamp provider and 1–3 `>=` threshold-call predicates in acyclic topological order. Graph variants include a single edge, shared provider fan-out, a chain, and fan-out with a downstream caller. Rename targets the provider. Maintenance atomically edits the provider's upper comparison and upper result literals plus one direct caller's threshold. All contract oracles are the existing clamp/threshold-call kinds. No production branch or schema extension is proposed.

## Reproducible counts

Baseline production runtime changes expected: zero. The 7 Cycle39 template families are each classified in `COMPATIBILITY-MATRIX.md`; Cycle40 generated production count and unsupported counts will be reported separately. Existing dispatch/replay/handoff tools are reused.
