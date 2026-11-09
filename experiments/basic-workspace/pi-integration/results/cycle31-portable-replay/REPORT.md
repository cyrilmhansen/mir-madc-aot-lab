# Cycle 31 — Shared Portable Constructive Replay

## Outcome

The 13-operation authentic Cycle 30 stream replays from an empty revision-1
Workspace through revision 14. It reconstructs five functions, all 27 live
portable handles, and the two retired `SCORE_CLASS` statement handles. The
historical handle `clamp_score.function` resolves to the renamed source symbol
`NORMALIZE_SCORE`. No retired identity is reused.

Normalized structure was compared directly with preserved snapshots at
revisions 11, 12, and 14. The replay's complete twenty-input observation corpus
for all five functions matches Cycle 30's saved host validation exactly, and
MIR interpreter and JIT outputs agree. Revision 9 is supported by the saved
rename identity/behavior validation. Revision 13 is supported by the committed
replacement and retirement receipt plus host validation. Those two checkpoints
are not represented as full semantic-snapshot matches.

## Consolidation

The shared implementation is
[`basic_workspace/portable_replay.py`](/home/john/projects/sushiworks/aot/mir-madc-aot-lab/experiments/basic-workspace/basic_workspace/portable_replay.py).
It uses canonical Workspace operations and has one explicit dispatcher for the
six operation families. It does not execute source text, interpret arbitrary
Python, authorize missions, or expose mutable Workspace documents in its
result.

Five active replay consumers now use it: Cycle 19, Cycle 20, Cycle 25, Cycle
28, and Cycle 29. The Cycle 20 baseline loader still performs its campaign
specific snapshot, commit, behavior, and provenance attestation around each
shared replay step. Mission authorization and host oracles remain in their
existing gateways.

| Measure | Before | After |
|---|---:|---:|
| Lines across the five audited gateway files | 3,804 | 3,377 |
| Shared replay module | 0 | 439 |
| Combined production lines | 3,804 | 3,816 |
| Gateway line reduction | — | 427 |
| Net production line change including shared module | — | +12 |
| Independent operation dispatch paths in the audited consumers | 6 | 1 |
| Operation families in shared dispatch | — | 6 |
| New replay classes | — | 2 (`PortableReplay`, `ReplayResult`) |
| Workspace mutation primitives / transaction lifecycles added | 0 | 0 |

The code consolidation is measurable: six replay dispatch paths were replaced
by one shared implementation, with gateway code reduced by 427 lines and only
12 net production lines added after the shared module. The small net increase
is the typed resolver and explicit identity ledger needed to cover block
replacement and retirement safely.

## Validation

* Shared replay regression: **8 passed**.
* Production-handler / JSONL bridge and migrated gateway focused regressions
  passed as part of the full suite, including Cycle 23's deterministic
  creation/maintenance dispatch check.
* Complete Workspace suite: **249 passed, 80 subtests passed**.
* Fresh replay and host validation report: [`equivalence.json`](equivalence.json).
* Revision evidence levels: [`revision-checkpoints.json`](revision-checkpoints.json).
* Live/retired identity state: [`identity-state-ledger.json`](identity-state-ledger.json).
* Replay operation receipts: [`replay-evidence.json`](replay-evidence.json).
* Negative replay controls: [`negative-controls.json`](negative-controls.json).
* Tampered-operation attestation control: [`historical-tamper-control.json`](historical-tamper-control.json).

The tampered final literal operation is syntactically replayable to a different
candidate revision, as expected for an interpreter. The separate historical
evidence check rejects it because its normalized state no longer matches the
preserved revision-14 snapshot. This keeps replay and attestation as separate
responsibilities.

Replay steps commit sequentially into the caller's temporary Workspace. A
later invalid operation does not roll earlier replay steps back; no
whole-stream atomicity is claimed. Each individual Workspace operation remains
revision checked and atomic.

## Reproduction

See [`REPRODUCE.md`](REPRODUCE.md). The workflow is Python-only and does not
launch Pi/Sushi or modify historical campaign artifacts.
