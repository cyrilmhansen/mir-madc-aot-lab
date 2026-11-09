# Replay consumer migration

| Consumer | Shared replay use | Kept outside the interpreter |
|---|---|---|
| Cycle 19 `_replay` | Full committed constructive operation sequence | Mission result comparison, MIR observation and report formatting |
| Cycle 20 `_reconstruct_from_operation_stream` | Applies each ordered operation through `PortableReplay.apply_operation` | Stream provenance, revision snapshots, commit receipt, retirement ledger, and host behavior attestation |
| Cycle 20 `_run_full_replay` | Replays complete stream and compares final state | Cycle 20 normalization, observation corpus, and equivalence output |
| Cycle 25 `replay` | Replays constructors, literal edits and IF insertion | SCORE_CLASS oracle and identity equivalence |
| Cycle 28 `validate` | Replays its complete constructor/edit stream | Four-function oracle, allowed dependency edge and unchanged assignments |
| Cycle 29 `_replay_all` | Replays the current committed prefix or final stream | Extraction-specific function graph, identity migration report and behavioral checks |

The Cycle 20 evidence loader remains an adapter around the shared engine. Its
special checks are historical claims about Cycle 26–30 artifacts; moving them
into the operation interpreter would make otherwise portable replay depend on
campaign file layouts. The Cycle 29 verifier similarly compares its live
mission result after replay rather than adding extraction policy to the shared
dispatcher.

Cycle 20's obsolete typed-expression, typed-block, replacement, and numeric
target replay helpers were removed after their active callers migrated. Cycle
25's local IF resolver and Cycle 28's local replay dispatcher were removed.
Cycle 29's replay application loop was removed; its portable block projection
helper remains because the MissionGateway uses it to authorize and describe a
candidate block, not to replay a stream.
