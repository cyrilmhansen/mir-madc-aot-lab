# Cycle 21 architecture audit

## Existing boundaries

- **Pi transport:** `extension.ts` registers five typed tools, carries `toolCallId` only in `transport.tool_call_id`, and forwards requests through the newline JSON bridge.
- **Semantic operation:** `edit_numeric_literals` contains a revision, selected function handle and one or more `{target, expected_value, replacement_value}` edits. The function-anchored IF path and statement-handle assignment path both require an explicit `expression_path`; `[]` selects an assignment RHS root.
- **Identity/path resolution:** portable function and statement handles map to current Workspace IDs. IF expression locations are selected by typed control path, then checked against the expected numeric value and current revision. Literal tokens have stable token IDs, not separate semantic handles.
- **Authorization:** the host-owned JSON contract names allowed function handles, exact typed targets, old values, replacement constraints, edit-count bounds, unchanged functions, required dependency edges and an independent oracle. It contains no executable predicates.
- **Candidate/commit:** candidate construction and complete semantic diff validation happen before preview. Commit reruns authorization at the same expected revision and applies one Workspace transaction. The preview does not advance canonical tokens or revision.
- **Execution/replay:** the contract supplies a bounded numeric oracle; MIR interpreter and JIT execute the candidate. The constructive stream adds the committed portable edit after the original constructors and replays into an empty Workspace.
- **Presentation/provenance:** Workspace event snapshots feed the existing generic code-first frame compiler. Model discovery, gateway preview/commit, host validation and replay retain separate provenance.

## Cycle 20 specialization and Cycle 21 reuse

Cycle 20's edit schema was fixed to exactly two entries, and the mission validation named the clamp behavior. The shared handler now accepts a bounded 1–8 edit list; it does not branch on mission IDs. Authorization uses only the loaded contract and a small built-in oracle vocabulary (`clamp`, `threshold_call`). Mission A and Mission B are data-only contract instances. The production class remains a single gateway; no Mission B subclass or second authorization implementation was added.

The new Mission B contract is 1,511 bytes; the prior Mission A contract is 1,763 bytes. The active five-tool Pi schema is 4,817 bytes, the same serialized size as the previous schema capture: the `edits` bounds changed from 2..2 to 1..8 without changing the shape. The shared gateway grew from 785 to 1,033 lines (+248 net lines), mainly for stream-based revision-4 reconstruction, contract validation/oracle support, replay and reporting. The edit authorization/commit path itself is shared. This is reuse by configuration, not a claim that total code shrank.

## Trace and timing correction

Cycle 20B's raw timing journal contains five agent-tool calls totaling 276.538 ms. Its summaries displayed zero because aggregation depended on an `agent_tool` boolean absent in those older timing rows. The runner now also recognizes the five semantic gateway method names. A regression reads the preserved raw journal and expects 276.538 ms. The original raw journal and both historical summaries were left untouched; no corrected historical summary was substituted.

## Preflight observation

The first Pi schema-capture attempt reconstructed revision 4 but did not start the viewer: an initial visual event used an unsupported `portable_identity_replay` mapping. The gateway event now uses the viewer's existing verified function-boundary mapping. `schema-preflight-02` then captured the active Pi 1.5 schema and five-tool inventory. This was a harness metadata error, not a program or provider failure; no model inference occurred during that attempt.
