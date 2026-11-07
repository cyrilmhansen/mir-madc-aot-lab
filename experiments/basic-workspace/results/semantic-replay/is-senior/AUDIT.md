# Cycle 13 audit before implementation

## Verified starting state

- HEAD: `6d395515c3f771fcd03e14982be4e2cb41d2990f`; branch `experiment/mir-aot-correctness-cycle3`.
- The existing working tree has pre-existing uncommitted Cycle 8/Cycle 11 outputs and MPDecimal logs. They will remain outside this campaign commit.
- Cycle 12 records 98 passing tests and one real `AGE_BY_ID` edit. Its genuine request/tool transcript will not be changed.
- Workspace construction already accepts typed `call` expressions referring to a discovered numeric function ID, and projection validation verifies callee type, document, arity and the generated MIR call. A focused in-memory proof returned IS_SENIOR outputs `0,0,1,0,0` in both MIR interpreter and JIT without any Workspace or MIR changes.
- `preview_transaction_semantics` returns the typed candidate projection without installing it. `apply_transaction` repeats validation at the expected revision.
- The current Cycle 12 `run_lookup_checks` has a corrected expected-value branch, but its response omits the executed revision, phase, per-engine match state, engine agreement and a complete-mission flag. This makes stale/contradictory output hard to detect.
- Existing replay normalization already binds function calls through semantic IDs when aliases are supplied. The metafile must resolve its `age_by_id.function` handle separately in every Workspace.
- Existing HTML/SVG/Kitty renderers consume event traces. The HTML has a timeline but no first-screen campaign summary; the SVG has no derived function dependency graph.

## Minimum approach

Reuse the Cycle 12 `AGE_BY_ID` typed constructor and identity binder. Create `IS_SENIOR` as a second typed numeric function whose call request references a portable `age_by_id.function` handle; resolve that handle to the discovered live symbol ID immediately before preview/commit. Add a campaign-specific gateway that allows only one `create_numeric_function`, checks the complete candidate projection, verifies the old function is identical and verifies the new projection has a real bound call to AGE_BY_ID. Keep behavioral correctness as a separate host oracle, so a well-formed but wrong threshold can be authorized and still fail the mission.

Use a portable stream containing both constructors and the handle-based call. Replay into a new empty Workspace with fresh IDs, then compare normalized typed structure, binding edges and MIR behavior. Run threshold boundary edits only on an isolated fixture.

Add a revision-aware validation response and regression tests before starting the one bounded model call. Extend the existing trace renderer only to add summary and dependency information derived from the trace. No canonical model, BASIC grammar, MIR or BWM changes are planned.

## Trust and falsification

The mission policy only applies to the tools provided by this campaign gateway. It is not a security boundary against direct Workspace, shell or filesystem access. A replay that keeps the original function UUID, a missing/misbound call, a changed AGE_BY_ID projection, an unauthorized operation mutation, a stale validation response, or a host oracle mismatch falsifies the corresponding claim. Scripted controls and replay events will be labeled separately from genuine model tool calls.

## Post-implementation audit

- No changes were required in the canonical model, typed expression parser, MIR projection, BWM, or native worker. The existing constructor already creates a genuine cross-function `call` when given a discovered function symbol ID.
- The narrow addition is a campaign-local `SeniorMissionGateway`: portable `function_handle` resolution, a one-new-function mission check, a full normalized candidate comparison against the pre-existing function, a bound-call check, and authorization revalidation before the ordinary atomic Workspace commit.
- The functional oracle is intentionally separate. Tests show a threshold of 49 is structurally authorized but fails the independent 49/50 behavior check. The gateway does not encode the exact illustrative body.
- `replay_stream()` recreates the base program, rediscovers AGE_BY_ID by semantic function identity, resolves the portable handle in the fresh workspace, and compares normalized function/statement/expression structures. The replay stream contains portable aliases and typed arguments, not opaque symbol/statement IDs.
- The validation wrapper reports requested/workspace/executed revisions, phase, host-owned expectations, both engine observations, per-engine matches, agreement and mission-complete status. A stale request has no executed revision and cannot pass.
- Visual summaries choose the committed campaign workspace and exclude fixture setup commits from the scripted-control copy. The HTML/SVG and Kitty state view consume recorded events only.
- The real-model runner remains constrained to five campaign-specific tools; no shell, source replacement or unmediated Workspace mutation is exposed. The gateway trust boundary excludes any direct Workspace/shell access outside those tools.
- The configured model endpoint was not present in the process environment (`BASIC_WS_CHAT_COMPLETIONS_URL` and `BASIC_WS_MODEL` unset), so no real LLM request was made. The main campaign is marked `pending_model`; a separate `scripted-mechanics/` campaign validates the vertical mechanics without being counted as model activity.
- Kitty 0.49.2 is installed, but `KITTY_LISTEN_ON` is unset. ANSI playback ran; custom shader activation and a remote screenshot were unavailable and are not claimed.
- Final verification: all 105 Workspace tests passed with `cd experiments/basic-workspace && python3 -m unittest discover -s tests -v`. The campaign subset passed 14 focused semantic-replay tests. Scripted interpreter/JIT results, 49/50 boundary checks, 11 negative controls, fresh-workspace equivalence, SVG parsing and Kitty ANSI playback all passed.
