# Cycle 36 architecture decision

## Selected boundary

Cycle36 uses a verified evidence handoff, not a shared mutable Workspace
object. The creation gateway and maintenance gateway remain independent
processes. The creation side writes canonical constructive operations and
host-owned checkpoint/validation evidence. A small receiver-side verifier
checks that evidence against a separately supplied trust anchor. It then
passes the authenticated stream/history/final host-validation paths to the
existing Cycle20 reconstruction path.

The receiver's state is reconstructed in a new empty Workspace using the
existing shared portable replay implementation. Cycle20 then runs its existing
baseline checks and its own mission contract validation. No maintenance tool
is activated before the constructor returns successfully.

## Why not transfer a Workspace directly

A direct transfer would prove only that two in-process objects can share
state. It would not prove that a receiving process can recover from portable
operations, and it would make an arbitrary mutable Workspace document part of
the trust boundary. It is therefore not the evidence path for this cycle.

## Handoff schema and trust

`basic-workspace.verified-creation-handoff`, version 1, contains a source
sequence identifier/profile, revision, operation count, exact relative
evidence references with SHA-256 values, final semantic fingerprint, live and
retired portable handle sets, signatures, dependencies, and the destination
maintenance contract identity/digest. References are constrained beneath the
declared source evidence root.

A separate host-owned anchor binds the exact serialized handoff bytes to the
expected source sequence, final fingerprint, revision, execution profile, and
destination contract digest. The bundle cannot grant itself authenticity by
editing an internal checksum. The receiving CLI accepts the bundle, anchor,
and source evidence root as host arguments; none are agent tools.

The verification stages are reported separately:

1. Schema and path validity.
2. Trusted bundle and artifact digest match.
3. Sequence ordering, revisions, and checkpoint consistency.
4. Shared portable replay and normalized semantic fingerprint match.
5. Portable identity, signature, and dependency equivalence.
6. Construction receipts and saved host observations match fresh MIR
   interpreter/JIT observations and the destination's independent oracle.
7. Cycle20's own mission authorization becomes available.

Authenticity does not imply semantic correctness; semantic correctness does
not imply maintenance authorization. The latter remains solely in the Cycle34
contract and existing Cycle20 authorization path.

## Transaction and history semantics

Each constructor remains its own revision-checked atomic commit. The three
numeric changes are one Cycle20 v2 `per_target` transaction with one preview
and one commit. The complete construction-to-maintenance workflow is not
atomic: committed creation prefixes remain committed if later handoff or
maintenance fails.

The final constructive stream uses four `create_numeric_function` operations
followed by one `edit_numeric_literals` operation for Mission A, and three
constructors followed by one edit operation for Mission B. The existing
Cycle31 dispatcher handles both streams.

## Components changed

The implemented production change is limited to the Cycle20 initialization
boundary and a verified-handoff helper. Cycle19 creation behavior and the
TypeScript schema remain unchanged. The bridge runner uses the existing
`cycle20b_dispatch_probe.ts` and the existing Cycle35 creation probe.

Mission B uses a distinct sequence configuration, maintenance contract and
oracle fixture. After Mission A is implemented, any production change needed
for Mission B will be separately recorded and will count against the
generalization hypothesis.

## Future rename assessment

The handoff authenticates the source program and portable identity ledger, so
the same boundary could in principle feed a separately authorized rename
gateway. That gateway would still need its own host-owned rename contract and
identity/source-name checks. Cycle36 does not implement or claim to validate
rename composition.
