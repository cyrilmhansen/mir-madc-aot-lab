# Cycle38 verified rename continuation, v1

## Purpose and accepted history

This host-only receipt authorizes no Workspace mutation. It authenticates exactly one supported history shape:

1. A Cycle36 verified creation-only handoff and its independent host anchor.
2. The same constructor prefix plus exactly one Cycle37 `rename_symbol` operation.
3. A successful accepted-preview/commit record and host validation at the next revision.
4. A separate host-owned Cycle20 v2 numeric maintenance contract.

The Cycle36 creation handoff remains creation-only. The continuation does not accept arbitrary mutation histories, additional rename operations, or a caller-provided mutable Workspace.

## Bundle and external anchor

The strict bundle records the creation sequence ID/revision, final revision and semantic fingerprint, exact rename and destination contract IDs/digests, live and retired portable handles, signatures, dependency edges, and digests/relative paths for the source handoff/anchor/evidence, rename contract/stream/history/validation/baseline, and destination contract.

A distinct host trust anchor is written outside the evidence package and binds the continuation bundle digest, source handoff and source anchor digests, rename contract, destination contract, final revision and fingerprint. The receiving host supplies that separately protected path; the mutable evidence package does not contain the anchor. Rehashing a modified bundle or changing its internal digests cannot replace the separately protected anchor.

## Receiver checks

The verifier checks strict fields/version/profile, safe package paths, every artifact digest, destination contract identity/digest, the original Cycle36 proof, exact operation-prefix equality and one authorized rename suffix, revision sequence, exact host commit/preview/validation evidence, portable handle continuity, unchanged dependencies/signatures, structural equivalence modulo target spelling, token identity continuity using a same-Workspace canonical rename check, and interpreter/JIT behavior against the authenticated construction oracle and rename receipt.

Only after those checks pass does Cycle20 derive its small in-process baseline adapter and activate its own independent maintenance authorization. The maintenance contract grants the edit rights; the continuation only establishes the state to which those rights apply.

## Limitations

The representation is intentionally one rename after one Cycle36 creation sequence. It is not a generic history envelope. Historical provenance depends on the receiving host selecting and protecting the source anchor and the new continuation anchor; self-consistent JSON alone is not a trust root. Finite execution corpora provide evidence, not proof for all numbers.
