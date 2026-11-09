# Cycle 27 — Post-rename semantic identity reuse

## Result

**Accepted.** One genuine Pi/Sushi session created `IS_AT_CAP(X)` from a reconstructed revision-9 Workspace. The new typed call used the historical handle `clamp_score.function`; the gateway resolved that handle to the existing `NORMALIZE_SCORE` symbol and emitted the current spelling in BASIC. The transaction committed revision 10. No replacement normalization function was created and no earlier portable identity changed.

## Baseline reconstruction

The host replayed exactly the eight authentic Cycle 26 committed operations from an empty Workspace. It reached revision 9, mapped all 18 established portable handles, compared normalized structure and bindings against Cycle 26 evidence, and verified interpreter/JIT behavior before inference. The current source name is `NORMALIZE_SCORE`; `IS_PASSING` and `SCORE_CLASS` remain bound to the function carrying `clamp_score.function`.

The final agent operation added one constructor, bringing the complete constructive stream to nine operations. It references the callee through `clamp_score.function`, not by source text or by an invented `normalize_score.function` handle.

## Deterministic production-path preflight

The preflight used the actual TypeScript tool handlers and JSONL gateway. The five active Pi tools were discovery, inspection, function preview, commit, and mission validation. Their captured Pi schema was 19,767 bytes. The configured Sushi/Qwen model was available in Pi's model inventory; this preflight did not make an inference request.

The preflight reconstructed revision 9, discovered `NORMALIZE_SCORE` under its old portable handle, accepted a non-mutating typed preview, committed a disposable candidate atomically, and validated MIR interpreter/JIT plus fresh replay. The emitted source used `NORMALIZE_SCORE`. Controls rejected invented/unknown or unauthorized handles, an attempt to use the old spelling as a local parameter, a stale revision, bad call arity, unknown semantic fields, and leaked transport metadata. Duplicate commit and changed-candidate commit were rejected without a second mutation.

The deterministic result is in `deterministic-preflight/summary.json`; it is not model activity.

## Genuine Pi/Sushi session

- Provider/model: Sushi / `Qwen3.8-Flash-Next-Sushi-STQ-2.75bpw`.
- Pi: 1.5.0.
- Turns: 5. Tool calls: 5 (one each for discovery, inspection, preview, commit, and validation).
- Preview: accepted at base revision 9; candidate was preview-only.
- Commit: one atomic commit, revision 9 → 10.
- Pi-reported usage: 25,402 input tokens, 1,788 output tokens, 40,106 cached prompt tokens, 0 cache-write tokens. These are the values Pi reported; cache-read is kept separate from input.
- Recorded session elapsed time: 76.917 seconds. Gateway tool-processing total: 473.633 ms.
- Pi lifecycle: `agent_end` and `agent_settled` observed; no pending tool calls; no timeout; process exited 0.

The exact Pi session is `real-agent-01/mission-3-pi-session.jsonl`; lifecycle observation is separately recorded in `mission-3-pi-lifecycle.jsonl` and `session-metrics.json`.

## Independent correctness and replay

The host-owned oracle ran all 16 requested inputs (`-100, -1, 0, 1, 19, 20, 39, 40, 44, 45, 49, 50, 51, 60, 100, 200`) on both MIR engines. `IS_AT_CAP(X)` returned 1 exactly when `NORMALIZE_SCORE(X) == 50`; all outputs matched, and interpreter/JIT agreed. The existing functions and their dependency edges were unchanged.

The complete nine-operation stream replayed from an empty Workspace. Structural, binding, behavioral, and engine equivalence all passed. The replay mapped 23 identities: all 18 baseline handles plus the new function, its parameter, and its statement handles. The `clamp_score.function` handle remained the call target while the source spelling remained `NORMALIZE_SCORE`.

See `real-agent-01/mission-3-validation-host.json`, `equivalence.json`, `constructive-operations.json`, and the top-level `identity-mapping.json`.

## Visualization

The generic offline replay is [visual-replay-generic.html](real-agent-01/visual-replay-generic.html). Its evidence-derived timeline shows revision 9, the discovered handles, a preview without changing committed code, revision-10 commit, MIR/JIT validation, and replay. The committed source first contains `IS_AT_CAP` at the commit frame. The commit frame shows the `NORMALIZE_SCORE(X)` call, while the identity inspector/report preserves `clamp_score.function` as its semantic identity. `visual-verification.json` checks these revision and preview/commit boundaries against the generated frames.

The live viewer URL was `http://127.0.0.1:...` during the run; its port was ephemeral and has since closed. The standalone HTML needs no server. No screenshot was captured for this cycle.

## Reporting correction

The inherited runner originally emitted `baseline_revision: 5` and the Cycle 24 mission label in derived summary metadata, even though `MISSION-3.json`, gateway readiness, and the actual reconstructed Workspace establish revision 9 and mission `cycle27.is-at-cap.v1`. The runner now derives both fields from the contract. The original generated summary is preserved verbatim as `summary.json`; `summary-corrected.json` records the corrected metadata and its evidence sources. The same correction is captured for the preflight summary as a separate derived file. No Pi transcript, tool call, gateway decision, or semantic operation was changed.

## Architecture accounting

- New mission contract: data only; no mission-specific transaction lifecycle.
- New production Python/TypeScript lines for replay, configured baseline execution, and runner metadata: approximately 188 additions across existing modules, with 43 removed/replaced lines. Most replay additions cover two historical operations (IF insertion and rename) that were already part of the supported constructive history.
- New deterministic preflight utility: 107 lines; new focused test module: 92 lines.
- New transaction lifecycle implementations: **0**. Both preview/commit paths continue through the shared Cycle 23 kernel and existing Workspace operations.
- Active Pi schema: 19,767 bytes across the five-tool inventory.

The compatibility cost was in reconstructing the exact renamed revision-9 seed, not in creating a new semantic authoring interface. A limitation remains: a historical commit without a semantic snapshot needs narrowly scoped identity/behavior attestations to prove the rename replay.

## Validation and artifacts

- Focused Cycle 27 tests: 6 passed.
- Existing older bridge tests initially exposed an over-strict comparison against historical oracle inputs. The replay check now compares overlapping recorded inputs and reports whether evidence coverage was complete; it still runs fresh interpreter/JIT checks on the configured mission inputs.
- Full Workspace regression suite: 230 tests passed in 29.595 seconds.

Artifacts are under this directory: contracts, deterministic TypeScript/JSONL preflight, provider preflight, genuine model transcript, event/history journals, nine-operation constructive stream, identity map, validation/equivalence, and offline HTML replay. Historical Cycle 11–26 evidence remains untouched.
