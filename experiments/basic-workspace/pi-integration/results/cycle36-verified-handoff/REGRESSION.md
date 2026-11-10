# Cycle 36 regression

Command:

```sh
python3 -m unittest discover -s experiments/basic-workspace/tests -v
```

Result: **274 tests passed** in 55.203 seconds. The Cycle35 recorded baseline
was 267 tests; Cycle36 adds seven test methods. No historical test was removed.

Focused handoff tests:

```sh
python3 -m unittest experiments.basic-workspace.tests.test_cycle36_verified_handoff -v
```

Result after final handoff schema and missing-anchor checks: **7 tests passed**.

Actual production bridge execution:

```sh
python3 experiments/basic-workspace/pi-integration/cycle36_preflight.py \
  --output experiments/basic-workspace/pi-integration/results/cycle36-verified-handoff/production-bridge-attempt-07
```

Both missions passed through the existing TypeScript extension handlers →
JSONL transport → Python gateways. No model inference occurred. The bridge
report is `bridge-validation.json`.

The negative campaign reported **45 checks passed**. It covers separate
anchor mismatch, altered and incomplete evidence, sequence order, revisions,
fingerprints, handle/dependency ledgers, validation receipts, destination
binding, malicious paths, mixed unauthorized edit batches, stale requests,
schema rejection, duplicate commit, and the Cycle34 historical bridge path.
Direct lifecycle tests also verify preview non-mutation, candidate
revalidation, restart behavior, and rejected edit snapshots.

The prior Cycle34 and Cycle35 evidence directories were read-only inputs and
remain unchanged.
