# Cycle 36 — Verified construction-to-maintenance handoff

## Result

The Cycle35 creation gateway's committed program can now be handed to a new
Cycle20 maintenance process through an independently verifiable evidence
bundle. The receiving process reconstructs an empty Workspace from portable
operations, checks the construction history and every revision checkpoint,
compares saved host interpreter/JIT receipts, runs its own baseline
observations, and only then enables its Cycle34 v2 maintenance contract.

Both model-free missions passed through the real TypeScript tool handlers and
JSONL bridge:

- **Mission A:** four functions committed at revisions 2–5; authenticated
  handoff at revision 5; one three-literal, two-function transaction committed
  revision 6.
- **Mission B:** three functions committed at revisions 2–4; authenticated
  handoff at revision 4; one three-literal, two-function transaction committed
  revision 5.

No Pi/Sushi inference was performed.

## What was verified

The trust anchor is a separate host-controlled file and binds the exact bundle
bytes, source sequence, execution profile, final semantic fingerprint and
destination contract digest. The bundle's internal artifact hashes are also
checked. The receiver rejects modified bundles, evidence, checkpoints,
contracts, dependency summaries and unsafe paths. A bundle plus a modified
internal checksum still fails against the unchanged external anchor.

Each construction prefix is replayed through the Cycle31 portable dispatcher
and checked against its checkpoint fingerprint, function signatures,
dependency graph, portable handles, commit snapshot and host validation
receipt. Cycle20 then performs its existing full reconstruction and baseline
oracle check. Maintenance authorization remains in the existing Cycle20 v2
contract path; the handoff does not carry or enlarge permissions.

Mission A matches its independent oracle, MIR interpreter, JIT and complete
five-operation replay for all 17 inputs. The cap becomes 80 and passing
threshold becomes 70. IS_EXCELLENT and HIGH_PRIORITY source structures remain
unchanged and both return 0 because of the cap.

Mission B matches its independent oracle, MIR interpreter, JIT and complete
four-operation replay for all 14 inputs. NORMALIZED_AGE caps at 60, IS_SENIOR
uses 55, and SENIOR_FLAG remains structurally unchanged while observing the
new result through its dependency.

Each complete stream includes the committed constructors and one
`edit_numeric_literals` batch. Every full-history prefix was reconstructed and
checked. There were no deleted or newly allocated identities during either
maintenance transaction; all live portable handles remained resolvable after
cross-process Workspace UUID remapping.

## Architecture outcome

The verified handoff is a bounded adapter to Cycle20's existing stream-based
baseline loader, not another gateway. Cycle19's sequence progression,
Cycle20's mission policy and transaction kernel, and Cycle31's replay
dispatcher remain authoritative. The TypeScript extension schemas did not
change. Mission B required no additional production code beyond the shared
implementation built for Mission A.

Production code grew by 340 net lines: 320 lines in a host-side handoff
verifier and 20 net lines in Cycle20's optional initialization/CLI adapter
(22 added, 2 removed). No legacy
loader was removed, so this result demonstrates integration and zero marginal
runtime cost for a second contract, but it does not claim that the historical
gateway code has been consolidated or deleted. The verifier repeats prefix
replay before Cycle20's own final stream replay; this deliberately costs
additional work to attest all construction checkpoints.

The separately stored anchor is a deployment assumption: the host must
protect it independently of the transferred bundle. Hashes prove integrity
only relative to that trusted anchor. The two finite input corpora are strong
boundary checks, not proofs for all numeric inputs.

## Acceptance levels

| Level | Result |
|---|---|
| 0 — Handoff blocker | Cleared |
| 1 — Verified handoff | Passed for both source programs |
| 2 — End-to-end Mission A | Passed, final revision 6 |
| 3 — Replay and security | Passed; 45 deterministic negative/security checks and 274 full-suite tests |
| 4 — Production integration | Passed through actual TypeScript → JSONL → Python path |
| 5 — Independent generalization | Passed; Mission B added zero production runtime code |
| 6 — Measured architectural benefit | Partially supported: no new transaction/replay/mutation engine and zero second-mission runtime cost; 340 net verifier/adapter LOC were added, and no legacy loader was removed |
| 7 — Rename future-readiness | Assessed only; a separately authorized rename policy could use the verified baseline, but was not implemented or tested |

Full details and reproducible evidence are linked from [AUDIT.md](AUDIT.md),
[ARCHITECTURE.md](ARCHITECTURE.md), [METRICS.md](METRICS.md),
[REGRESSION.md](REGRESSION.md), and [REPRODUCE.md](REPRODUCE.md).
