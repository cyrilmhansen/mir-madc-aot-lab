# Cycle 36 audit

## Baseline

At audit time HEAD was `41f633ae5a17d2419b184b40f462396be1572581` on
`experiment/mir-aot-correctness-cycle3`. The working tree already contained
unrelated semantic-replay/control-flow artifacts, MPDecimal logs, and Cycle 35
preflight/agent evidence. Those paths are outside this cycle and must remain
untouched.

## Existing responsibilities

| Boundary | Existing implementation | Reused responsibility |
|---|---|---|
| Creation authorization/progression | `cycle19_gateway.py` creation-sequence mode | Ordered host contracts, typed constructor validation, host-only checkpoint/progression, per-step validation, operation recording |
| Atomic transaction | `transaction_kernel.py` | Candidate fingerprinting, preview, revision checks, commit revalidation |
| Portable history | `basic_workspace/portable_replay.py` | The six canonical operation families and portable identity remapping |
| Maintenance authorization | `cycle20_gateway.py` | v1/v2 numeric edit contract validation, per-target policy, expected values, unchanged-function and dependency checks |
| MIR validation | Cycle19/Cycle20 host validators | Interpreter/JIT observations against host-owned expected data |
| Transport | `extension.ts`, `cycle20b_dispatch_probe.ts`, JSONL gateway | Typed tool schemas and real TypeScript-to-Python request path |

Cycle20's legacy baseline loader intentionally requires a constructive stream,
commit history, and final validation record. It verifies the stream profile,
mission completion, replay result, revision, committed snapshot, portable
identity set, and behavior. Historical Cycle29/rename/extraction exceptions
are tied to their existing evidence and are not broadened by Cycle36.

Cycle35 already records the evidence needed for a stronger, new baseline:
the host-owned sequence contract, each committed constructor operation,
per-step host validation, a checkpoint after every step, the final semantic
fingerprint, signatures, dependency graph, and portable handles. The existing
Cycle20 replay consumes its `constructive-operations.json`, `history.jsonl`,
and final host validation directly, but there is no independent trust anchor
binding these separate files to a specific source sequence and destination
maintenance contract.

The Cycle20 v2 path already validates each edit's handle independently and
commits the complete batch through one `SemanticTransactionKernel` transaction.
The Cycle31 replay dispatcher also applies each edit's function handle
individually. No Workspace operation, transaction kernel, or replay family is
missing.

## Baseline size

Line counts were measured with `wc -l` on production Python files before any
Cycle36 production edits:

| File | Lines |
|---|---:|
| `cycle19_gateway.py` | 1,169 |
| `cycle20_gateway.py` | 1,204 |
| `transaction_kernel.py` | 121 |
| `basic_workspace/portable_replay.py` | 452 |

These gateway files contain substantial historical mission behavior. Cycle36
will not copy or replace them with another gateway. The experiment will add a
bounded handoff verifier and a small Cycle20 initialization adapter.

## Pre-registered design

Selected approach: **A, an explicitly versioned verified Cycle35 stream
adapter in the Cycle20 baseline path**, with a separate host-trusted digest
anchor supplied to the receiving process. The adapter authenticates evidence
references and sequence/checkpoint semantics, then delegates actual program
reconstruction to the existing Cycle20 baseline loader and shared portable
replay path. Cycle20 still independently checks its own contract and
observations before reporting readiness.

The handoff bundle is not self-authenticating. Its anchor is a distinct
host-controlled file/argument. The verifier will hash the bundle and every
referenced source artifact, reject paths escaping the evidence root, compare
the sequence ID, profile, revision, final fingerprint, handle set, signatures,
dependencies, maintenance contract ID/digest, and complete step receipts.
Only after these checks may the normal Cycle20 constructor run.

Approach B, transferring a mutable in-process Workspace, is rejected as the
primary path: it cannot demonstrate independent reconstruction across gateway
processes and makes the document itself a trust input. It remains unnecessary
as a control because the required evidence is independently replayable.

Expected changes: one small production handoff module, a bounded optional
Cycle20 CLI/constructor adapter, Cycle35 contract fixtures and evidence runner,
no TypeScript schema changes, no new classes for gateway/transaction/replay,
and zero changes to canonical Workspace operations. Mission B should require
contract/oracle fixtures only.

Falsification: the hypothesis fails if Cycle35 evidence cannot meet the
existing Cycle20 baseline checks without weakening them, if Mission B needs a
mission-name branch or production-policy change, if bridge operation requires
a second transaction path, or if unauthorized/rejected maintenance mutates
the reconstructed authoritative baseline.
