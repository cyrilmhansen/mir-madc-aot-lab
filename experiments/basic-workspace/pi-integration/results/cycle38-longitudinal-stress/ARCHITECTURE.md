# Cycle 38 architecture

## Trust boundary

The workflow uses three independently scoped stages. Cycle19 commits constructors one by one. Cycle37 authenticates that creation history and commits one authorized rename. A trusted host then issues a Cycle38 continuation anchor only after verifying the complete rename stage. Cycle20 verifies that continuation against its own maintenance contract and reconstructs a new Workspace from the portable stream before exposing maintenance tools.

The creation-only Cycle36 `basic-workspace.verified-creation-handoff` remains unchanged. Cycle38 continuation is a different, explicit schema and accepts only a Cycle36 creation anchor plus exactly one Cycle37 rename operation. It does not act as a generic history format or mission graph.

## Chosen path

The host receipt packages evidence references and digests; it does not carry a Workspace object. Its trust anchor is stored outside the evidence package and binds the bundle digest, source creation trust root, rename contract identity/digest, final revision/fingerprint, portable ledgers, and destination maintenance contract identity/digest. The receiver verifies the receipt and artifact hashes, calls the original Cycle36 verifier on the nested creation proof, checks the exact rename suffix and Cycle37 host receipt, reconstructs with the shared portable replay code, runs MIR interpreter/JIT against the creation oracle, and compares structural and dependency state. It then derives Cycle20's baseline stream/history/validation adapter in its own output directory. Cycle20's pre-existing loader performs its own replay and contract scope checks.

## Why not extend the creation-handoff schema

The Cycle36 verifier intentionally equates constructor count, configured sequence length, operation count and final revision. Adding a rename exception there would couple the creation proof to a new operation family. A separate continuation record keeps the old schema strict while reusing its verifier for the exact creation prefix.

## Responsibilities kept separate

- Canonical Workspace: semantic state and `rename_symbol` / numeric-edit mutations.
- SemanticTransactionKernel: one preview/commit lifecycle per mutation.
- Cycle19: creation step authorization/progression.
- Cycle37: rename authorization through shared `rename_policy.py`.
- Cycle20: numeric edit authorization and independent maintenance oracle.
- Cycle31: the only portable history dispatcher.
- Cycle38 continuation verifier: attest the handoff between those existing processes; no mutation and no policy interpreter.
- TypeScript/JSONL bridge: unchanged; host orchestration supplies trusted files/arguments.

## Implemented result

Implementation adds `verified_rename_continuation.py` (one bounded evidence builder/verifier) and an opt-in Cycle20 initialization/CLI path. After verification, Cycle20 materializes a host-derived adapter containing the authenticated portable operation stream and the summary shape expected by its existing replay loader. The adapter is written under Cycle20's output directory and is never accepted as an agent-supplied baseline. Cycle20 then uses its existing stream reconstruction, contract checks, authorization, kernel preview/commit and independent validation.

Both missions used the same path. Mission B added no production code after Mission A. No gateway class, Workspace operation, transaction lifecycle, replay dispatcher or TypeScript tool was added. The continuation rejects histories with anything other than one rename suffix.

The initial four runner attempts remain as harness-failure evidence: missing directory creation before gateway launch, expecting a readiness `identity_count` Cycle20 does not publish, shallow schema-key collection, and missing creation of Mission B's rename directory. They all stopped before the relevant maintenance commit. Attempt 05 completed Mission A but stopped before Mission B's rename. Attempt 07 is the complete paired run.
