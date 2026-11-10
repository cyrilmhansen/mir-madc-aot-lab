# Cycle 40 — Generated End-to-End Authorization Fuzzing

## Result

The complete production workflow passed for **24 confirmatory generated cases**: 16 frozen primary seeds plus 8 cases from a second seed offset. A separately labeled exploratory case also passed with a leaf-function rename, providing a second rename-target position and zero direct callers. Each workflow constructed 2–4 functions through Cycle19's real TypeScript/JSONL path, authenticated a construction handoff, renamed through Cycle37's real handler, authenticated the rename continuation, then previewed and committed three cross-function numeric edits through Cycle20's real handler. The maintenance batch changed the clamp comparison, clamp result, and a predicate threshold in one commit.

All 25 cases matched the independent arithmetic specification in the host validation, MIR interpreter, MIR JIT and fresh replay checks. The confirmatory corpus covered four graph shapes, each six times: a single edge, shared provider, chain, and fan-out with downstream caller. The campaign generated 584 rejected-request/provenance controls. The tampered creation handoffs and continuations were rejected against unchanged external anchors.

No production runtime changes were required. No unexpected authorization acceptance, oracle mismatch, interpreter/JIT divergence, replay mismatch, or provenance acceptance was observed.

## Interpretation

This is evidence that the existing production contracts compose across a varied but bounded subset of generated programs. It does not establish general support for the seven Cycle39 families: raw predicates, strict-less predicates, sequential overrides and two-callee sequential functions remain outside Cycle20's oracle vocabulary. See the compatibility matrix. The generated workflows were selected to fit existing `clamp` and `threshold_call` validation; unsupported cases were classified rather than passed off as end-to-end successes.

The successful cases are not exhaustive correctness proof. Numeric inputs are a finite boundary-oriented corpus. The counterexample reducer was not validated on a genuine production defect because no product discrepancy was found. Performance evidence is limited to per-tool timing traces and end-to-end attempt duration; isolated confirmatory scaling benchmarks remain future work.

## Acceptance levels

- Level 0: compatible subset identified; four Cycle39 shapes explicitly excluded.
- Level 1: passed; host-owned contracts generated for each case.
- Level 2: passed; 24 confirmatory complete actual TypeScript-to-JSONL workflows plus one exploratory case.
- Level 3: passed for accepted workflows; oracle, MIR and replay checks agree.
- Level 4: passed; authorization and provenance controls reject, without mutation.
- Level 5: passed for one injected stale-revision production-boundary failure; no genuine product failure was available to reduce.
- Level 6: partial; repeated end-to-end envelopes and tool timings retained, but no isolated confirmatory scaling study.
- Level 7: passed; second seed configuration ran eight full workflows.
- Level 8: no defect discovered.
- Level 9: partial; the generator runs a second configuration without production changes, within the same supported grammar.

Reproduction commands and preserved attempts are listed in `REPRODUCE.md`.
