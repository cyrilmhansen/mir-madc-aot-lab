# Mission B — Three-level dependency chain

## Construction

The independent host-owned configuration is
[`creation-sequence.json`](production-bridge-attempt-07/mission-b/creation-sequence.json).
It creates `NORMALIZED_AGE`, `IS_SENIOR`, and `SENIOR_FLAG` at revisions 2–4.

```text
NORMALIZED_AGE → IS_SENIOR → SENIOR_FLAG
```

## Handoff and maintenance

The revision-4 handoff is independently anchored in
[`handoff/`](production-bridge-attempt-07/mission-b/handoff/). The same
receiver-side verifier, shared replay, Cycle20 contract implementation,
transaction kernel, TypeScript tool schema, and JSONL bridge are used as
Mission A.

The distinct Cycle20 v2 contract is
[`maintenance-contract.json`](production-bridge-attempt-07/mission-b/maintenance-contract.json).
Its one atomic edit batch changes NORMALIZED_AGE's cap comparison and result
100 → 60, and IS_SENIOR's threshold 65 → 55. It commits revision 4 → 5.

`SENIOR_FLAG` remains structurally unchanged and observes the new threshold
through its bound IS_SENIOR dependency. All functions match the independent
oracle, interpreter, JIT, and full replay for the 14-input corpus in
[`independent-oracle-observations.json`](production-bridge-attempt-07/mission-b/independent-oracle-observations.json).

Mission B required different contract/oracle data only; no production change
was made after Mission A to support it.
