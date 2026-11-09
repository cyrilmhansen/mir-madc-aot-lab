# Cycle 32 infrastructure audit

## Repository state and controls

At audit start, local `HEAD` was `979f982fcc9a1ccac84b7a268f4a2d2597e9180e` on `experiment/mir-aot-correctness-cycle3`, matching the expected Cycle 31 commit. The branch tracks `origin/experiment/mir-aot-correctness-cycle3`. The working tree already contained unrelated MPDecimal logs/disassembly and earlier BASIC result changes/untracked Cycle 13B, preflight-08, and real-pi-02 evidence. Those paths are preserved and excluded from Cycle 32 staging.

The frozen specification is in `MISSION.md`. No inference was performed.

## Responsibility map

| Layer | Existing implementation | Reusable capability | Mission-specific boundary |
|---|---|---|---|
| Canonical Workspace | `basic_workspace/model.py` | Typed `create_numeric_function`, `rename_symbol`, `edit_numeric_literal_at_path`; revision-checked preview/apply transactions | Each transaction operation is applied by Workspace, but Workspace does not own mission authorization |
| Projection / typed grammar | `basic_workspace/typed_expr.py`, `projection.py` | Numeric expressions, comparisons, result assignments, structured IF, calls and semantic projection | Does not define mission contracts or independent expected results |
| Atomic preview/commit | `pi-integration/transaction_kernel.py` | Preview snapshot/fingerprint, transaction id, base revision, commit revalidation and candidate fingerprint check | Caller supplies authorization/revalidation callback |
| Portable history | `basic_workspace/portable_replay.py` | One explicit dispatcher for six operations: create function, edit numeric literals, IF insertion, rename, IF-condition edit, typed-IF block replacement. It resolves portable handles and retirement over revision order | Replay applies recorded operations; it does not authorize a live agent proposal or attest campaign evidence |
| Function construction agent gateway | `cycle19_gateway.py` | Typed constructor checking, discovered dependency checks, transaction kernel and validation for its missions | Default is hard-coded to CLAMP_SCORE/IS_PASSING; the alternate creation contract admits one additional function on a verified Cycle 21 seed and has a one-commit mission lifecycle |
| Numeric maintenance gateway | `cycle20_gateway.py` | Contract-configured targets, expected-old-value checks, revision check, candidate projection comparison, token identity checks, atomic preview/commit, dependency invariants and MIR observation comparison | Baseline loader requires the Cycle 19B stream/evidence; current supported host oracle kinds are `clamp`, `threshold_call`, `score_class_call`; each request selects one function handle, and all edits are constrained to that function's authorized target set |
| Rename / extraction gateways | `cycle26_gateway.py`, `cycle29_gateway.py` | Existing rename and block-replacement examples and Cycle 31 portable replay | Their mission authorization and baseline assumptions are campaign-specific; they are not a general multi-operation mission sequence interface |
| TypeScript→JSONL bridge | `gateway.py`, Pi extension, Cycle 23 preflight | Real extension handler and JSONL request/response dispatch; creation and maintenance preflights exercise supported gateways | Bridge routes to a running selected gateway; it does not supply a configurable generic mission policy |
| Historical evidence verification | Cycle 31 reports/tests and campaign-specific reconstruction checks | Reusable portable replay result and deterministic normalized-state comparison patterns | Snapshot, provenance, and independent-oracle attestation remain campaign-owned |

## Representational finding

The requested program is expressible without new BASIC syntax or a new Workspace operation:

- Arithmetic uses numeric literals, local references, binary `+`, `-`, and `*`.
- Rebate and surcharge use result assignment plus a typed numeric comparison in structured IF.
- Aggregation uses three typed bound calls in a binary expression tree.
- Existing canonical operations cover function creation, symbol rename, and guarded literal edits.
- The Cycle 31 replay dispatcher already recognizes the relevant `create_numeric_function`, `rename_symbol`, and `edit_numeric_literals` operation families.

Portable handles can remain source-name-independent: `early_rebate.function` can continue to resolve after rename, and the final caller still binds to that Workspace symbol. A two-target `edit_numeric_literals` replay record can contain one target in each of two function handles; canonical replay resolves each target handle independently. (The live Cycle 20 gateway, in contrast, requires every requested edit to target the selected top-level `function_handle`.)

This establishes representational feasibility only. No new mission was applied to an authoritative Workspace in this audit.

## Production authorization/integration blocker

The exact production workflow required by `MISSION.md` cannot be configured through the existing live entry points:

1. `Cycle19Gateway`'s empty-document path installs two fixed mission specs (`CLAMP_SCORE`, then `IS_PASSING`) and a two-phase completion model. It does not accept four arbitrary constructor contracts or continue through four committed creation missions.
2. Its alternate data-driven creation-contract path requires a previously verified Cycle 21 stream as a seed and authorizes exactly one additional function. Its seeding path delegates to Cycle20's specific baseline reconstruction and is not an empty-document sequence loader.
3. `Cycle20Gateway` accepts a contract file, but initialization reconstructs and validates the Cycle 19B two-function history or its known stream format. Its contract validator rejects oracle kinds other than `clamp`, `threshold_call`, and `score_class_call`; those do not express the requested independent oracle for the four new functions and their affine/conditional aggregation.
4. The maintenance request selects one discovered `function_handle`; the authorization requires all edits in that request to target that function. The registered edit operation therefore cannot atomically authorize the BASE_CHARGE multiplier and RUSH_SURCHARGE threshold together. The two-location Cycle 20 mission examples refer to two target paths within one function, not two functions.
5. Rename support is demonstrated in the Cycle 26 specialized gateway, not configurable as one step in the Cycle 20 maintenance contract. The bridge does not combine a Cycle 19 constructor mission, a Cycle 26 rename mission, and a Cycle 20 cross-function maintenance transaction into one authorized history.

The gap is not a representation or replay limitation. It is an authorization/orchestration configuration limitation: there is no existing host-owned configuration that describes an ordered mission containing four one-at-a-time creations, one stable-identity rename, and a two-function atomic edit with an independent four-function oracle. Making this run through the production bridge would require a new mission dispatcher/adapter or extending existing gateway behavior. Both are explicitly prohibited by the pre-registered stop rule, so implementation and mission execution stop here.

## Baseline size rules and counts

Reproducible LOC means physical source lines (`wc -l`), comments and blank lines included, generated result files excluded:

- Canonical Workspace production: all top-level `basic_workspace/*.py` = **5,330 LOC**.
- Audited Pi integration core: `gateway.py`, `transaction_kernel.py`, `cycle19_gateway.py`, `cycle20_gateway.py`, `cycle25_gateway.py`, `cycle29_gateway.py` = **3,951 LOC** (sum of those tracked source files; preflight tooling excluded).
- Shared portable replay: `portable_replay.py` = **439 LOC**.
- Independent portable replay dispatch implementations after Cycle 31: **1** explicit dispatcher, **6** supported operation families.
- New mission-specific runtime classes or dispatchers added in Cycle 32: **0**.
- New Workspace operations, transaction lifecycles, replay families, dependencies, or model activity in Cycle 32: **0**.

Mission policy is not a single countable generic subsystem today: there are separate host-owned policy implementations for creation, numeric edit, rename, structural insertion/replacement and conditional edit. Cycle 20's contract configuration reduces literal-target policy duplication but does not make these lifecycle families composable into an arbitrary ordered campaign. Cycle 31 replay is a reusable interpreter for already-authorized history, not a policy engine.

The Cycle 31 recorded baseline is **249 tests and 80 subtests**; Cycle 32 will record the current rerun separately in `REGRESSION.md`.

## Conclusion

The Cycle 32 hypothesis is only partly supported. Existing typed Workspace operations and shared portable replay eliminate the need for new semantics and replay code, but existing production authorization cannot execute the complete novel mission without mission-specific runtime changes. This is a concrete generalization blocker, not a semantic correctness failure. The cycle stops before constructing a bespoke gateway or claiming production-path mission support.
