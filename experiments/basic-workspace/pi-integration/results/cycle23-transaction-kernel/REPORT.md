# Cycle 23 — Shared Semantic Transaction Kernel

## Result

No-inference architectural consolidation completed. Numeric function creation (Cycle 19) and numeric literal maintenance (Cycles 20/21) now share the same revision-checked preview and atomic commit implementation. Each family retains its own typed operation validation, mission authorization, semantic identity checks, independent oracle, replay, and event formatting.

The integration probe used the production Pi TypeScript extension registration/handler and Python JSONL bridge for function creation, then the existing Cycle 21 production dispatch harness for maintenance. It did not call model inference.

## Deterministic bridge evidence

`preflight/summary.json` records:

- Function constructor schema captured from the registered extension: 5,151 compact JSON bytes; inventory matches the preserved Pi capture.
- Initial Workspace revision 1 remained unchanged during accepted preview.
- Commit advanced to revision 2; MIR interpreter/JIT agreement and fresh replay passed.
- A valid-shape but unauthorized function name was rejected as `MISSION_SIGNATURE`; a stale base revision was rejected as `STALE_REVISION`; both left the empty authoritative document unchanged. Repeating the commit after success was rejected as `STALE_REVISION`.
- Maintenance production dispatch passed both existing mission contracts, including four historical accepted proposal fixtures, the disposable commit/MIR/replay path, and the rejection controls.
- The TypeScript handler attached a real-shaped Pi tool call ID as JSONL transport metadata; the semantic request remained metadata-free and the gateway correlation record was retained.

## Historical behavior and tests

Existing Cycle 19 and Cycle 20/21 tests continue to exercise accepted/rejected proposals, stale revisions, unchanged state after rejection, identity preservation, independent validation, and fresh replay. New kernel tests verify preview-only state, commit at one revision, duplicate commit rejection as stale, and candidate mismatch rejection without mutation. `cycle23_transaction_preflight.py` is also a reproducible no-inference end-to-end bridge check.

Exact final test results are recorded in the completion report and the repository test command is `python3 -m unittest discover -s experiments/basic-workspace/tests -v`.

## Complexity accounting

Measured on the four audited Python components (`gateway.py`, `cycle19_gateway.py`, `cycle20_gateway.py`, `draft_protocol.py`):

| Measure | Baseline | After Cycle 23 |
|---|---:|---:|
| Production lines in audited files | 2,716 | 2,844 |
| Cycle 19 + Cycle 20 gateway lines | 1,683 | 1,690 |
| Shared lifecycle module | 0 | 121 |
| Independent preview/commit lifecycle implementations | 2 | 1 shared kernel + 2 adapters |
| Mission operation families using shared lifecycle | 0 | 2 |
| New production modules/classes | 0 | 1 module, 1 kernel class, 1 receipt dataclass |

The line count rises by 128 across this accounting boundary; this is not a LOC-reduction refactor. The value is that the correctness-sensitive ordering (revision check, preview record, commit revalidation, candidate/operation identity check, revision recheck, single atomic apply) now has one implementation and is verified against two operation families. Mission-specific output/reporting remains deliberately duplicated. Further unification is not justified by the current evidence: creation and maintenance candidates have different normalized identity rules and post-commit checks, and draft transactions have different semantics.

## Limits

- The kernel is process-local and has no durable recovery or idempotency key for repeated previews.
- Preview record count is not globally quota-bounded; existing single-session process lifetime remains the resource boundary.
- A failure in gateway post-commit integrity verification is reported after Workspace's atomic commit; rollback is not claimed.
- The shared layer does not own correlation metadata. The transport boundary remains responsible for it.
- No visual schema was changed; existing Cycle 22 evidence remains the presentation compatibility reference.
- No inference, model usability, or latency conclusion is part of this cycle.
