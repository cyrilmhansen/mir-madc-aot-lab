# Regression results

Command:

```sh
python3 -m unittest discover -s experiments/basic-workspace/tests -v
```

Result: **256 tests passed in 45.074 seconds**. Full output is preserved in `regression.log`.

The run includes prior Cycle19 construction, Cycle20/21 numeric maintenance, Cycle23 transaction kernel, Cycle24 dependency creation, Cycle26 rename, Cycle29 extraction, Cycle30 identity lifecycle, Cycle31 portable replay, and deterministic TypeScript-to-JSONL bridge preflights. Existing V1 contracts and stream envelopes passed unchanged. Seven additional Cycle34 tests cover both contract modes, non-mutating denials, commit revalidation and rejection of a tampered legacy replay envelope.

The actual Cycle34 production bridge preflight is in `bridge-validation.json`; each of its two independently configured runs passed discovery, inspection, TypeBox validation, non-mutating preview, one revision-checked commit, host MIR/JIT validation, constructive replay and mixed-target rejection.
