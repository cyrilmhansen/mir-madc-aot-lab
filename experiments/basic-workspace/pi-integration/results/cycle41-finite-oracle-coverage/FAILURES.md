# Failures and limitations

## Confirmed product findings

No genuine semantic or authorization defect was confirmed in Cycle41's generated production corpus. The deliberately incorrect, well-formed finite table is rejected at candidate preview as `MISSION_PREVIEW_ORACLE`, with revision and normalized state unchanged. An unknown finite-oracle portable handle is rejected as `MISSION_CONTRACT_HANDLE` before MIR execution. No expected value was changed to match observed engine output.

## Harness/measurement attempts retained

- The first confirmatory benchmark attempt used an input corpus that omitted historical baseline observations. Cycle20's legacy baseline adapter correctly requires its complete recorded validation input set; this made the v2 benchmark fixture invalid before candidate measurement. The attempt remains in `benchmark-confirmatory/`. The confirmatory benchmark was redesigned to start from the complete authenticated 16-input v2 corpus and extend to 32 and 64 inputs. No legacy acceptance rule was changed.
- An intermediate benchmark completed while a temporary overlap-only baseline comparison was being investigated. That production edit was reverted to preserve v1/v2 behavior, and those timing results are not used for Cycle41's confirmatory claims. `benchmark-confirmatory-final/` is the reported measurement, using the full historical corpus and the original strict baseline check.
- A replication started while the complete test suite was running and was interrupted to avoid reporting contended timings. The partial output is preserved in `benchmark-confirmatory-replication/`; an uncontented replication subsequently completed in `benchmark-confirmatory-replication-final/` and confirmed the relative table-parse increase.
- An initial test for destination-table modification expected the receiver to report `CONTINUATION_DESTINATION_MISMATCH`; verification actually fails earlier with `CONTINUATION_ARTIFACT_DIGEST` because the contract file inside the package is individually digest-bound. The test now checks both this artifact-integrity boundary and a separately supplied alternate-contract mismatch.
- One initial unknown-handle implementation surfaced a raw key lookup during MIR observation. V3 handle resolution now occurs immediately after authenticated aliases are available and rejects with `MISSION_CONTRACT_HANDLE` before observations. The regression test covers this case.
- The first priority-family production runs used two literal targets. Because three were feasible, they are preserved as exploratory/earlier confirmatory attempts, and a separate three-target amendment is running. The later runs are reported separately rather than overwriting the first corpus.

## Remaining supported-surface limits

Direct numeric editing still addresses numeric literal nodes, not negative numbers represented by unary-minus expressions. A finite table validates only its declared inputs, and a correct digest does not prove the independent mathematical specification. These are reported limits, not observed defects.
