# Cycle 38 — Longitudinal Semantic Workflow Stress Test

## Outcome

The primary hypothesis survived this bounded experiment: existing creation, rename, maintenance, transaction and replay paths composed across three gateway processes through a host-anchored continuation record. Both missions reached their specified final revisions and matched independent arithmetic expectations in fresh replay, MIR interpreter and MIR JIT.

The work did **not** produce a general workflow coordinator. It added one explicit continuation verifier for the narrow history shape `Cycle36 creation proof + one Cycle37 rename + Cycle20 maintenance contract`. Existing Cycle36, Cycle37 and Cycle20 authorization stayed in their own gateways. Mission B used identical production code; no mission-specific runtime branch was added.

No Pi/Sushi inference was run. All primary mission evidence is deterministic production-handler execution through TypeScript → JSONL → Python. The complete regression suite passed 287 tests.

## Mission results

Mission A created four functions at revisions 2–5, renamed the shared provider at 5→6, then atomically changed three literals across two functions at 6→7. The portable function identity remained `bounded_score.function` after its source name changed to `NORMALIZED_SCORE`. `IS_EXCELLENT` and `HIGH_PRIORITY` stayed structurally unchanged and became zero because the cap fell below their effective threshold.

Mission B created the three-function dependency chain at revisions 2–4, renamed `NORMALIZED_AGE` to `CAPPED_AGE` at 4→5 while retaining `normalized_age.function`, then committed the cap and threshold edits together at 5→6. It added no production code.

Each stage used the real existing five-tool allowlist. Both maintenance previews left the revision unchanged; each subsequent commit advanced it once. Three edits were one `edit_numeric_literals` constructive operation. Both engines matched independent host oracles at every saved prefix and final state. Complete observations, signatures, dependencies, identity maps and replay results are in the JSON evidence files and raw attempt 08.

## Trust and security

The receiver does not accept a mutable Workspace from the previous process. It verifies the separate continuation anchor, exact Cycle36 creation proof, exact Cycle37 rename suffix and commit/host receipts, portable handle set, signatures, dependencies, current fingerprint, and independent MIR observations. It reconstructs from an empty Workspace before activating the separately host-owned Cycle20 contract.

The 69-case rejection matrix passed. It combines actual construction/rename/maintenance TypeScript bridge denials and schema rejections with 26 continuation bundle/artifact/anchor attacks, including changing the bundle and its internal digest while the separate host anchor remains unchanged. The tamper tests fail closed before a maintenance transaction can be authorized. Restart tests confirmed that an uncommitted preview is process-local: after stopping and restarting, the revision remained unchanged and a new preview had a different transaction ID.

## Longitudinal and bounded stress

The primary streams were replayed prefix-by-prefix. Metamorphic experiments restored rename A→B→A and literal V1→V2→V1 semantics while preserving portable identities; two fresh replays agreed modulo local UUIDs. Reordering rename and maintenance was semantically replayable, but is not authorized by the revision-bound mission contract.

Twelve bounded fixed-seed variants changed caps and thresholds and passed shared canonical replay plus independent host expectations and both MIR engines. These variants were replay/oracle stress, not additional production-authorization runs; only the two primary missions exercised the full TypeScript transaction path.

## Architectural cost and limits

The production delta is 406 physical lines: 354 in the new narrow continuation verifier and 52 in Cycle20's opt-in adapter/CLI boundary. Cycle19, Cycle26/37, Cycle36 handoff verification, the transaction kernel, Cycle31 replay and TypeScript bridge were unchanged. No new gateway class, transaction mechanism, mutation, tool schema or replay dispatcher was added.

The measurable cost is a second evidence/replay/oracle pass at the rename-to-maintenance boundary (median 0.78 s for Mission A and 0.54 s for B on this machine). The verifier duplicates no replay dispatcher, but it does independently assert continuation-specific identity, operation-order and rename invariants on top of the original gateway checks. That duplication is intentional defense at a process boundary and is bounded to one rename suffix.

Seven interruption points were covered for both missions. Two points were actively interrupted through production previews (rename and maintenance); committed-stage cut points were reconstructed from their authentic portable prefixes. This is not an all-or-nothing workflow: earlier successful commits remain committed if a later stage stops. Finite corpora and two programs do not prove correctness for arbitrary contracts or all numeric inputs.

## Acceptance levels

- **Level 1 — Authenticated continuation:** met.
- **Level 2 — Complete Mission A:** met.
- **Level 3 — Complete Mission B:** met.
- **Level 4 — Replay and identity integrity:** met for both recorded streams and prefixes.
- **Level 5 — Security and recovery:** 69 rejection cases passed; all seven declared cut points recorded, with preview interruptions actively exercised and committed cuts recovered by replay.
- **Level 6 — Production integration:** met for both full primary workflows through existing TypeScript→JSONL handlers; full historical suite green.
- **Level 7 — Bounded robustness:** partially met. Twelve deterministic replay/oracle variants and metamorphic controls passed, but the variants changed portable operation streams and were not each run through a separate host authorization contract. The two primary missions did traverse the full production authorization path.
- **Level 8 — Measured architectural reuse:** met narrowly: one host continuation adapter, zero Mission B production delta, no new mutation/transaction/replay mechanism. The added verifier cost and boundary replay overhead are material and documented.

The first complete attempt (07) revealed that its host anchor was colocated with the evidence bundle. That run is preserved as diagnostic evidence. Attempt 08 writes the host anchor outside the mutable evidence package and is the final accepted run. See `AUDIT.md`, `ARCHITECTURE.md`, `TRUST-BOUNDARIES.md`, `METRICS.md`, `REGRESSION.md`, and `REPRODUCE.md` for detail. No historical raw evidence was rewritten and no commit was pushed.
