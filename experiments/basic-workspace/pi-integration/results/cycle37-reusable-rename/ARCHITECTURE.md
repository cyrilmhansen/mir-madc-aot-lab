# Cycle 37 architecture decision

Cycle37 keeps Cycle26Gateway as the only rename gateway. Its legacy v1 startup continues to verify the authentic Cycle25 revision-8 evidence. A new explicit v2 startup mode accepts a host-selected Cycle36 bundle, separate host trust anchor, source evidence root, and a strict host-owned rename contract. It invokes `verified_handoff.verify_handoff` before reconstructing or enabling rename tools.

The old `_candidate` method's authorization responsibilities move to one reusable pure helper that receives the authenticated baseline, current Workspace, alias map, discovered set, request and contract. Both v1 and v2 call this same helper and the same `SemanticTransactionKernel` preview/commit methods. Mission-specific expected observations and presentation labels remain configuration-driven in v2; no mission-name dispatch is used.

The v2 host behavior baseline comes from the final Cycle35 host validation artifact referenced and digest-bound by the handoff. Cycle36 authenticates its per-step receipt against the creation contract and replays the program. Cycle37 compares fresh pre-rename and post-rename MIR interpreter/JIT observations using portable handles. The independent creation oracle therefore remains the source of expected behavior.

No change is planned to the handoff schema, portable replay vocabulary, Workspace mutation API, transaction kernel or Pi tool schema. Handoff authenticity is not rename authorization: the destination rename contract is separately host-owned and bound by the Cycle36 anchor.

## Strategy comparison and implementation

| Strategy | Result of review |
|---|---|
| A — Add verified-handoff initialization to Cycle26Gateway | Chosen. It retains the existing transaction and handler path and lets the host select v1 historical bootstrap or v2 authenticated construction. |
| B — Extract a separate shared rename adapter / transfer object | The candidate authorization itself was extracted as `rename_policy.py`, but a second gateway/adapter stack was rejected. A mutable in-process transfer would not demonstrate independently reproducible evidence across processes. |

The shared helper is called by the legacy v1 and new v2 modes. It owns strict request checks, stable identity resolution, canonical rename candidate construction, token/reference and dependency comparisons, and normalized candidate authorization. `Cycle26Gateway` remains responsible for its established preview/commit protocol, transaction revalidation, history and mission validation. The v2 initializer adds only the handoff-specific bootstrap and portable-handle keyed validation needed for an arbitrary compatible program.

Observed cost is 289 net production LOC: 123 lines in the shared policy and a net 166-line expansion of the existing gateway. This is not a near-zero adapter; its cost is the new authenticated bootstrap and generalized validation/reporting path. It did avoid a parallel gateway, handoff verifier, replay implementation, transaction mechanism, Workspace mutation, or TypeScript tool. Mission B needed contract/evidence data only. The design would be falsified by a future rename needing another authorization pipeline or a branch keyed to a specific mission name.
