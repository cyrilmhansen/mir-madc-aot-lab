# Verified creation handoff contract

Schema: `basic-workspace.verified-creation-handoff`, version 1.

The bundle references (by relative path and SHA-256) the Cycle35 creation
sequence copy, constructive stream, host history, execution profile, every
revision checkpoint, and every per-step host validation receipt. It also
records source sequence ID, execution profile ID, final revision, operation
count, final semantic fingerprint, live and retired portable identities,
function signatures, dependency graph, and the destination Cycle20 contract
ID and byte digest.

The bundle is paired with a separately supplied
`basic-workspace.verified-creation-handoff-anchor`, version 1. The anchor binds
the exact handoff bytes plus source sequence, profile, final revision,
fingerprint, destination contract ID, and destination contract digest. The
agent cannot select or change either file. The receiving host must keep the
anchor in a host-controlled location or otherwise protect it independently;
the code cannot establish authenticity if an attacker can replace both the
bundle and the trusted anchor.

The receiver verifies strict schema and artifact paths, bundle digest, target
contract digest, source operation order and revision sequence, every checkpoint
fingerprint/signature/dependency/handle set, every commit snapshot, host
validation receipts, and finally replays the entire stream through the shared
portable replay implementation. Cycle20 then performs its existing full
baseline replay, behavior comparison, and maintenance contract checks before
the gateway can serve discover/inspect/edit tools.

The `execution_profile_id` in the creation contract and handoff is the
Cycle35 composition identifier `basic-workspace.numeric-composition.v1`.
Cycle35 also saves an execution-profile descriptor whose own `profile_id` is
`basic-workspace.numeric-control.v1`. The handoff binds and schema-checks that
descriptor; it does not conflate these two historical identifiers.

The handoff is not a Workspace transaction and does not grant maintenance
authority. The receiving Cycle20 v2 contract independently authorizes the
exact three target paths, original values, replacements, unchanged functions,
dependency edges, and oracle. The workflow is sequential: previously committed
construction remains if handoff or maintenance later fails.
