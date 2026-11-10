# Cycle 36 host-owned contracts

The complete contract JSON is preserved beside each accepted bridge run:

| Mission | Creation sequence contract | Cycle20 maintenance contract |
|---|---|---|
| A | [mission-a/creation-sequence.json](production-bridge-attempt-07/mission-a/creation-sequence.json) | [mission-a/maintenance-contract.json](production-bridge-attempt-07/mission-a/maintenance-contract.json) |
| B | [mission-b/creation-sequence.json](production-bridge-attempt-07/mission-b/creation-sequence.json) | [mission-b/maintenance-contract.json](production-bridge-attempt-07/mission-b/maintenance-contract.json) |

The sequence files are Cycle35 version-1 data contracts. Each step limits one
function name/signature, expected base revision, required previously created
callees, exact dependency edges, prior-function preservation, and
revision-specific independent expected results. Cycle35's strict contract
validator rejects unknown fields and unsupported operation families.

The maintenance files are Cycle34 version-2 `per_target` numeric literal
contracts. They explicitly list the three authorized typed targets, expected
original values, replacement values, allowed and unchanged function handles,
dependency edges, base revision, and built-in `clamp` / `threshold_call`
oracle data. Their exact file bytes are digest-bound to each handoff and its
separate host trust anchor.

No contract contains executable code, callbacks, source patches, or
agent-selected authorization policy.
