# Reproduce Cycle 36

All commands are model-free. Bun must be available for the real TypeScript
extension probe; the configured native MIR worker is used for interpreter/JIT
checks.

From the repository root:

```sh
python3 experiments/basic-workspace/pi-integration/cycle36_preflight.py \
  --output experiments/basic-workspace/pi-integration/results/cycle36-verified-handoff/<new-empty-output>
```

The runner refuses a nonempty output directory. It generates distinct
Mission A and Mission B sequence configurations, drives each constructor
through the real extension/JSONL path, validates and checkpoints each step,
then creates a handoff and separately stored host anchor. It starts a new
Cycle20 process for maintenance and again uses the TypeScript semantic-edit
tool handler. The operation stream contains only committed semantic
operations, not rendered BASIC source.

The accepted production-bridge campaign is preserved in
`production-bridge-attempt-07/`. Earlier attempts 1–6 remain as diagnostics;
they are not combined with the successful run.

Generate or verify the recorded negative campaign and lifecycle summary:

```sh
python3 experiments/basic-workspace/pi-integration/cycle36_security_evidence.py
```

Recompute deterministic timing summaries:

```sh
python3 experiments/basic-workspace/pi-integration/cycle36_metrics.py
```

Reassemble identity and replay indexes from the accepted bridge outputs:

```sh
python3 experiments/basic-workspace/pi-integration/cycle36_finalize_evidence.py
```

Run the focused or complete test suite:

```sh
python3 -m unittest experiments.basic-workspace.tests.test_cycle36_verified_handoff -v
python3 -m unittest discover -s experiments/basic-workspace/tests -v
```

The host trust anchor is a separate input. In a deployment it must be stored
and supplied by a trusted host process; putting the bundle and anchor in the
same untrusted writable location would defeat the authenticity guarantee.
