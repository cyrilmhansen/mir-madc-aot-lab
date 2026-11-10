# Cycle 35 audit and pre-implementation record

## Baseline and worktree

- HEAD: `bc333b204d8173a56430cc5edcf18d31ddb6e292`
- Branch: `experiment/mir-aot-correctness-cycle3`
- The worktree contains pre-existing MPDecimal logs/disassembly and BASIC evidence changes/untracked captures. They are out of scope and will not be staged.
- Cycle34's raw regression log reports 256 passing tests. Its `REPORT.md` summary said 254; that summary is corrected during Cycle35, while the raw log remains unchanged.

## Existing responsibilities

| Responsibility | Current implementation | Reusable for sequences? |
|---|---|---|
| Typed constructor syntax | `Cycle16Gateway.typed_shape_error` and the TypeScript constructor schema | Yes. Both mission programs fit the existing bounded one-parameter numeric grammar. |
| Per-function authorization | `Cycle19Gateway._candidate` against `current_contract` | Yes. It checks function name/signature, discovered callees, numeric call signatures, exact dependency handles, prior function invariants, and candidate bindings. |
| Atomic preview/commit | `SemanticTransactionKernel` called by `_preview` and `_commit` | Yes. Keep one function creation per transaction. |
| Identity assignment | `senior.aliases_for_new_function` after Workspace commit | Yes. Reuse after each committed step. |
| Independent validation | Cycle19 validation plus the verified-stream creation path's finite host oracle | Reuse the verified-stream path's expected-result data for every step, including all existing functions. |
| Constructive replay | Cycle31 shared `replay_constructive_stream` | Yes. No replay changes expected. |
| Progression/checkpoint | `create_checkpoint` and `advance_mission2` | The fingerprint and host-gated progression pattern is reusable, but its two missions and checkpoint fields are fixed to Cycle19. A small creation-only sequence cursor/checkpoint is missing. |
| Verified baseline reconstruction | `_init_from_verified_stream` | Useful evidence that creation can follow a prefix, but specialized to one step and older baseline inputs. Keep it intact. |

The current alternate `creation_contract_path` mode allows exactly one newly created function after a verified stream and supports multiple required callees. The default mode advances from hard-coded Mission 1 to Mission 2. The gap is the repeated host-controlled progression through creation-only steps.

## Baseline LOC

Physical source lines (`wc -l`):

| File | Before |
|---|---:|
| `cycle19_gateway.py` | 828 |
| `transaction_kernel.py` | 121 |
| `basic_workspace/portable_replay.py` | 452 |
| `extension.ts` | 241 |
| `cycle20b_dispatch_probe.ts` (test harness) | 103 |

## Pre-registered design

Extend `Cycle19Gateway` with an explicitly selected creation-sequence mode. Normalize the currently active sequence step into the existing `current_contract` fields and keep calling `_candidate`, `_preview`, `_commit`, `validate_current`, and the one transaction kernel. Add a small immutable sequence-contract validator, cursor advancement method reachable only through the trusted host API (not registered as a Pi tool), and sequence-bound checkpoint/recovery adapter. The same active step can resume from an authenticated prefix replayed by the existing Cycle31 dispatcher.

Do not create a second gateway class, schema compiler, transaction lifecycle, or replay implementation. The sequence contract is data-only and bounded to at most eight one-parameter numeric function creations. Both missions use independently supplied finite outputs for every function at every revision.

Expected production change: modify only `cycle19_gateway.py`; leave Workspace, transaction kernel, replay dispatcher, extension schema and JSONL transport unchanged. New tests, the deterministic bridge runner and two contract files are experimental/data artifacts, not production runtime.

The design is falsified if Mission B requires mission-name branches or separate authorization logic, if host progression is exposed in the agent tool inventory, or if reconstructing a validated prefix requires source-text reconstruction or direct Workspace mutations outside the existing replay engine.
