# Mission A — Score evaluation

## Construction

The host-owned configuration is
[`creation-sequence.json`](production-bridge-attempt-07/mission-a/creation-sequence.json).
It creates `BOUNDED_SCORE`, `IS_PASSING`, `IS_EXCELLENT`, and `HIGH_PRIORITY`
in revisions 2–5, starting from the empty revision 1 Workspace.

The expected dependency edges are:

```text
BOUNDED_SCORE → (none)
IS_PASSING → BOUNDED_SCORE
IS_EXCELLENT → BOUNDED_SCORE
HIGH_PRIORITY → IS_EXCELLENT
```

Each committed prefix has an independent host oracle result for all functions
present at that revision and interpreter/JIT observations.

## Handoff and maintenance

The creation sequence is handed off at revision 5 using the bundle and
separate host anchor under
[`handoff/`](production-bridge-attempt-07/mission-a/handoff/). The receiving
gateway reconstructs all four functions from the four committed portable
constructors and verifies every checkpoint before maintenance.

The Cycle20 v2 contract is
[`maintenance-contract.json`](production-bridge-attempt-07/mission-a/maintenance-contract.json).
One authorized `per_target` transaction changes:

- BOUNDED_SCORE cap comparison: 100 → 80.
- BOUNDED_SCORE upper result: 100 → 80.
- IS_PASSING threshold: 60 → 70.

The three edits commit atomically at revision 6. `IS_EXCELLENT` and
`HIGH_PRIORITY` remain structurally unchanged; because the score cap is now 80,
both return 0 throughout the tested corpus.

The 17 required inputs and full per-revision observations are in
[`independent-oracle-observations.json`](production-bridge-attempt-07/mission-a/independent-oracle-observations.json).
All four functions agree with the separate host arithmetic oracle, MIR
interpreter, JIT, and fresh constructive replay.
