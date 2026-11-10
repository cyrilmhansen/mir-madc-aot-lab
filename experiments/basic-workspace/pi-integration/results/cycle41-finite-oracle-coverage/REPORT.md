# Cycle 41 — Host-owned finite oracle and semantic coverage expansion

## Result

Cycle20 now accepts a strict v3 `finite_expected_results` validation table while retaining its existing v1/v2 contracts and authorization flow. The table is host-owned expectation data; it does not describe or authorize mutations. The existing `SemanticTransactionKernel`, canonical numeric edit operation, candidate structural checks, MIR execution loop, portable replay and TypeScript tool schema are reused.

The primary confirmatory set contains 16 generated workflows and the independent second-seed set contains 8 more. Each of these 24 amended workflows has three literal edits authorized and committed atomically across the generated programs, and traverses the real Cycle19 creation, verified handoff, Cycle37 rename, verified continuation, and Cycle20 v3 maintenance handlers. Seven Cycle39 template families are represented across the confirmatory sets and retained controls. Every accepted revision matched the independently generated finite expectations in interpreter and JIT; final histories matched fresh portable replay. No Pi/Sushi inference was run.

The repository also preserves the first 24 priority workflows, which used two-target maintenance batches, plus two four-workflow smoke attempts and three template-control workflows. In total, 59 complete production workflows are indexed. The amended 24 three-target set is the principal acceptance result; earlier runs remain separately identified rather than overwritten. To avoid committing redundant lifecycle traces for every successful case, eight representative workflows retain complete raw bridge/handoff packages while compact records, complete constructive histories, snapshots, observations, contracts and trust receipts remain for all 59 (`evidence-compaction.json`).

## Verification and security

The v3 table is bounded to 64 inputs, 8 functions, and 512 cells, with exact object shapes, unique inputs/handles/result keys, positional complete rows and finite numeric values. Boolean and non-finite values are rejected. Unknown validation handles fail before MIR execution. A well-formed but incorrect boundary result is rejected during preview as an oracle mismatch without changing revision or normalized state. The external continuation binding rejects both a package table alteration and a substituted destination contract. Contract data is snapshotted in memory at gateway startup; rewriting its file later does not replace the active expectations.

v2 and v3 were run against the same authenticated Cycle34 baseline and the same three-target edit. They committed equivalent normalized state, portable history and observations. Existing v1/v2 paths remain in the full regression suite with their original oracle vocabulary and strict historical baseline attestation.

## Measurements

The finite-table path adds 64 net physical lines to Cycle20; all measured transaction, replay, handoff, continuation and TypeScript files are unchanged. No new gateway, operation, transaction mechanism, replay dispatcher, or agent-facing tool was added. Two uncontented v2/v3 runs used 16/32/64-value corpora and five fresh samples per mode/size. Schema/table parsing was 2.5–8.5x slower than parsing the smaller v2 formula declaration, but stayed below 0.08 ms per contract; preview, commit, MIR observation and full validation/replay stayed within 4%. The relative parse overhead repeated, but its absolute cost was not material to end-to-end validation. See `METRICS.md` and `PERFORMANCE.md`.

## Acceptance levels

- **Level 0 — blocker:** cleared for the seven tested numeric template families.
- **Level 1 — strict v3 contract:** passed.
- **Level 2 — v2/v3 equivalence:** passed.
- **Level 3 — expanded semantic coverage:** passed for raw `>=`, raw `<`, clamp, dependent predicate, sequential override, two-callee and dependency-chain templates.
- **Level 4 — complete production integration:** passed; 24 amended confirmatory workflows, plus retained earlier workflows and controls.
- **Level 5 — second seed configuration:** passed without mission-specific production changes.
- **Level 6 — security/provenance:** passed for tested malformed tables, wrong expectations, unknown handles, schema/tool requests and contract/anchor tampering.
- **Level 7 — differential correctness:** passed for all accepted finite corpora and replay prefixes.
- **Level 8 — performance:** completed; bounded to the reported shared two-function/three-target fixture.
- **Level 9 — genuine defect discovery:** no product defect found.
- **Level 10 — architectural reuse:** passed; all three gateway stages use existing runtime paths, with 64 net Cycle20 lines and zero new mutation/transaction/replay mechanisms.

## Limits

Finite inputs do not prove correctness for every numeric input, and contract integrity does not establish that a mathematical specification is true. Current generation exercised up to three functions; four-function cases were not emitted. Direct edits to unary-minus negative literal nodes remain unsupported. The benchmark isolates input-count scaling at fixed function/target count. Full Workspace regression and reproduction details are recorded in `REGRESSION.md` and `REPRODUCE.md`.
