# Failure ledger

## Product findings

No confirmed Workspace, MIR interpreter, MIR JIT, portable identity, dependency binding, revision or replay defect was observed in the final 120-case campaign. No genuine product counterexample required minimization or promotion.

## Preserved harness calibration attempts

The `preflight-fast*` and `semantic-run-*` directories preserve early failures and corrected reruns:

1. `preflight-fast`: constructor operation body aliased a mutable generator body; the later mutation also changed the constructor payload. Fixed by deep-copying constructor arguments before mutation.
2. `preflight-fast-corrected`: expected identity ledger omitted Workspace's generated terminal result assignment. Fixed by accounting for the terminal assignment.
3. `preflight-fast-v3`: harness read a nonexistent `PortableReplay.revision` property. Fixed by reading authoritative Workspace revision.
4. `preflight-fast-v4`: the first independent clamp oracle conflated the edited comparison literal with the unchanged branch result. Projection inspection showed the canonical edit correctly changed only the comparison. Oracle now models both separately.
5. `preflight-fast-v5`: structure comparison initially included random Workspace-local UUIDs. It was changed to the established portable normalized semantic comparison; the following preflight passed.
6. `semantic-run-01`: negative RHS edit expected a signed literal, while the canonical path editor requires a direct numeric node. Generated edit thresholds were constrained to positive directly-addressable numeric nodes; negative inputs and lower bounds remain covered.
7. `semantic-run-02`: a generated lower comparison used a negative RHS, but the current semantic edit path accepts only a direct comparison RHS number and does not edit through unary-minus. The production/tool capability gap is recorded in `COVERAGE.md`.
8. `semantic-run-03`: a dependent clamp specification used shorthand key `upper` instead of the oracle's explicit `upper_condition` and `upper_result` fields. The rule was made consistent and the final corpus rerun.
9. `production-run-01`: Cycle19 requires the portable handle stem before `.function` to be one identifier; the first generator draft used additional dots. Generated stems were changed to underscores, matching the production contract.

These were generator, fixture, oracle and production-contract representability issues, not MIR defects. The final corpus reran after the relevant fixes. Their attempt outputs remain in place for audit.

## Reducer validation

`counterexamples/injected-reducer-check.json` contains a deliberately injected harness-only mismatch at input 8. The bounded reducer reduced seven inputs to `[8]` while preserving that injected predicate. It is explicitly excluded from product bug counts.
