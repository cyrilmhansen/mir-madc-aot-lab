# Regression results

Focused Cycle37, Cycle26 legacy rename, and Cycle36 verified-handoff tests: **19 tests passed** in 16.362 seconds.

The original Cycle26 production TypeScript-to-JSONL preflight passed at `cycle26-legacy-preflight/summary.json`. It retained the revision-8 baseline, revision-9 commit, historical handle inventory, and its original CLAMP_SCORE → NORMALIZE_SCORE contract.

The Cycle37 production bridge completed both v2 missions through the actual TypeScript tool handler and JSONL Python dispatch path. Final attempt 5 used the fixed validation mapping and verified a non-mutating preview, revision 5 → 6 commit, host validation, fresh replay, unknown-field rejection, five authorization denials, and duplicate-commit rejection. No inference was performed.

Earlier Cycle37 bridge attempts are retained as diagnostic evidence. Attempt 2 had an evidence-path issue; attempt 4 exposed the validation identity-mapping bug and failed before reporting successful validation. Attempt 5 reran both full missions successfully after the correction.

Full Workspace regression command:

```bash
python3 -m unittest discover -s experiments/basic-workspace/tests -v
```

Result: **282 tests passed** in 117.756 seconds. The complete output is preserved in `full-workspace-tests.log`. The Cycle36 baseline was 274 tests; Cycle37 contributes eight focused test methods. No regressions were observed.
