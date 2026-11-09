# Cycle 29 — Semantically Controlled Function Extraction

## Result

The two genuine Pi/Sushi sessions completed successfully. They used separate conversations and independently authorized transactions:

| Phase | Base → committed revision | Agent result | Host result |
|---|---:|---|---|
| Mission A: create `BASE_SCORE_CLASS(X)` | 11 → 12 | Accepted preview, one commit, normal Pi settlement | 16-input oracle, interpreter/JIT, preserved-program and replay checks passed |
| Mission B: replace the first `SCORE_CLASS` IF | 12 → 13 | One rejected proposal, one accepted preview, one commit, normal Pi settlement | Behavior, dependency graph, identity migration, interpreter/JIT and replay checks passed |

The final `SCORE_CLASS` calls `BASE_SCORE_CLASS(X)` for the first classification. The helper calls `NORMALIZE_SCORE(X)` through `clamp_score.function`. The subsequent `IS_PASSING` and `IS_AT_CAP` conditions remain unchanged. No BASIC source was imported or used as a mutation input.

## Verified baseline

The Cycle 28 ten-operation authentic constructive stream was replayed into a fresh Workspace. The reconstructed revision 11 matched the preserved semantic commit snapshot, saved execution profile, host observations and interpreter/JIT outputs. All 23 portable handles resolved to fresh Workspace identities. The historical Cycle 25 formatting differences remain documented with their original evidence.

Mission A adds five live portable handles (function, parameter and three constructor-created assignments). Mission B retires `score_class.statement.0` and `score_class.statement.1`, then allocates `score_class.statement.extracted-base-call`. Thus revision 12 has 28 live handles; revision 13 has 27. The migration is recorded in [`identity-migration.json`](real-agent-01/identity-migration.json). The deleted branch assignments are explicitly retired and are never reused.

The helper adds `BASE_SCORE_CLASS → NORMALIZE_SCORE`. Replacing the selected branch removes the former `SCORE_CLASS → NORMALIZE_SCORE` edge and adds `SCORE_CLASS → BASE_SCORE_CLASS`. The existing `SCORE_CLASS → IS_PASSING` and `SCORE_CLASS → IS_AT_CAP` edges remain. The complete final graph is in the host validation record.

## Production bridge preflight

The no-inference run invoked the real Pi TypeScript tool handlers and schemas, their production JSONL bridge, the Python gateway, and the same shared `SemanticTransactionKernel` used by the campaign. Both transaction families previewed without changing the Workspace, committed once, ran the host oracle and replayed from an empty Workspace. Duplicate commits, stale revisions, wrong target/fingerprint, undiscovered and incompatible calls, incorrect arity, unauthorized calls, incorrect retirement sets, and an unknown semantic field were rejected without mutation. Each arm exposed exactly five tools.

The first captured probe found that the block-replacement schema allowed only literals and parameter references as assignment values. After narrowing the change to the block-replacement tool schema, a second preflight passed. The final regression-compatible probe is [`production-bridge-03/summary.json`](deterministic-preflight/production-bridge-03/summary.json); the initial failed and intermediate schema captures are retained under `deterministic-preflight/` as diagnostic records. No scripted preflight operation is counted as model activity.

The final registered schemas measure 5,151 compact / 19,766 pretty bytes for creation and 2,704 compact / 7,218 pretty bytes for block replacement. During the genuine run, Mission A's captured schema was 29,010 pretty bytes because it was captured before the creation assignment schema was narrowed back to the preserved Cycle 23 grammar; the actual constructor payload used in the run was valid under both forms. Mission B's captured schema was 7,219 bytes. These are serialized schema sizes, not token estimates. The Pi provider-reported usage is reported separately below.

## Genuine agent activity

The actual recorded prompts, Pi JSON sessions, lifecycle observations, gateway events, tool schemas, and session summaries are preserved separately for both phases in `real-agent-01/mission-a/` and `real-agent-01/mission-b/`.

| Measure | Mission A | Mission B |
|---|---:|---:|
| Model turns | 5 | 6 |
| Tool calls | 5 | 6 |
| Preview attempts | 1 accepted | 2 (one denied, one accepted) |
| Commits | 1, revision 12 | 1, revision 13 |
| Provider input tokens | 34,556 | 36,190 |
| Provider output tokens | 1,990 | 5,318 |
| Reported cache-read tokens | 50,148 | 77,862 |
| Pi process elapsed | 106.642 s | 214.464 s |
| Gateway processing for agent tools | 1,165.102 ms | 2,376.350 ms |
| Settlement / process | `agent_settled`; exit 0 | `agent_settled`; exit 0 |

Mission B's first proposal used the semantic handle `score_class.parameter.id` as a local parameter spelling. The gateway returned `MISSION_REPLACEMENT_DENIED` without mutation. The model then used the inspected local parameter name `X`; the corrected preview passed. This rejection is genuine model activity and is retained in the transcript and journal.

Mission A's prompt named the portable `clamp_score.function` handle while asking the model to discover and inspect the functions. The transcript confirms the model performed discovery before construction, but the prompt did disclose the handle. Therefore this run demonstrates typed construction and a correctly bound historical identity, but it is not a clean test that the model independently inferred that particular handle from discovery alone. Mission B's helper identity was not supplied in its task prompt; the fresh session received the verified checkpoint and then called discovery and inspection.

The separate completion records report semantic correctness, authorization, commit, host validation, Pi settlement and launcher exit independently. Both missions passed all six dimensions. The visual-only settlement summaries were derived from the preserved lifecycle and process-exit records; raw Pi transcripts were not changed.

## Behavior, replay and identity

Both intermediate revision 12 and final revision 13 were validated over `-100, -1, 0, 1, 19, 20, 39, 40, 44, 45, 49, 50, 51, 60, 100, 200` for `NORMALIZE_SCORE`, `IS_PASSING`, `SCORE_CLASS`, `IS_AT_CAP`, and (after creation) `BASE_SCORE_CLASS`.

- All expected outputs matched on both MIR interpreter and JIT.
- The extracted helper implements the below-20 classification and retains the discovered bound call to `NORMALIZE_SCORE`.
- All four pre-existing function definitions remain unchanged by Mission A.
- Mission B preserves every later `SCORE_CLASS` statement and all other function definitions; the two replaced branch assignments are the only retired statements.
- Revision-12 replay remapped 28 live identities; revision-13 replay remapped 27 live identities. Structural, binding, behavioral and engine-agreement checks passed at both revisions.
- The complete 12-operation constructive stream consists of the authentic ten Cycle 28 operations followed by the two genuine commits. Retired handles are listed separately; neither retired handle is mapped to the replacement.

## Visualization

The generic offline replay is [`visual-replay-generic.html`](real-agent-01/visual-replay-generic.html), generated from the recorded semantic events and committed snapshots. It shows baseline revision 11, the helper preview/commit, the verified checkpoint and fresh-session boundary, the rejected and corrected block replacement, revision-13 commit, identity retirement, dependency graph and revision-bound host observations. The preview does not advance the committed listing. The status frames for settlement are host classifications derived from the actual Pi lifecycle streams.

Firefox headless captured actual browser screenshots at 1600×1250:

- [`baseline.png`](real-agent-01/screenshots/baseline.png)
- [`preview-large.png`](real-agent-01/screenshots/preview-large.png)
- [`commit.png`](real-agent-01/screenshots/commit.png)
- [`validation-large.png`](real-agent-01/screenshots/validation-large.png)
- [`mission-b-settled.png`](real-agent-01/screenshots/mission-b-settled.png)

The preview capture shows the old committed IF in the editor and the accepted replacement diff below it, labeled preview-only at revision 12. The commit capture shows the new call in `SCORE_CLASS`; the settled capture shows the dependency graph and revision-13 current execution observation.

## Architecture cost and limits

| Responsibility | Added/changed lines (approx.) |
|---|---:|
| Canonical typed block-splice implementation | 232 in `model.py` |
| Workspace client/server surface | 21 |
| TypeScript block-replacement schema and dispatch | 20 |
| Cycle 29 gateway, oracle, replay and contracts | 674 |
| Production TypeScript/JSONL deterministic preflight | 125 |
| Two-session Pi runner | 178 |
| Visual lifecycle finalizer | 68 |
| Cycle 29 tests | 124 |

The commit/preview lifecycle implementation count remains one: both mission families use `SemanticTransactionKernel`; the new operation does not implement a second transaction engine. However, the 674-line campaign gateway is substantial and remains mission-specific in its contracts, validation and replay composition. This is a real cost, not evidence that the architecture now supports arbitrary extraction without additional work. The Workspace operation itself is limited to replacing a verified IF with typed numeric result assignments; it rejects ambiguous physical spans such as comments or colon-separated statements. A more general reusable extraction facility would need a separately scoped design.

## Reproduction and validation

From the repository root:

```sh
python experiments/basic-workspace/pi-integration/cycle29_preflight.py \
  --output experiments/basic-workspace/pi-integration/results/cycle29-function-extraction/deterministic-preflight/production-bridge-NEW

python experiments/basic-workspace/pi-integration/run_cycle29.py \
  --timeout 240 \
  --output experiments/basic-workspace/pi-integration/results/cycle29-function-extraction/real-agent-NEW

python experiments/basic-workspace/scripts/basic-visual.py replay \
  experiments/basic-workspace/pi-integration/results/cycle29-function-extraction/real-agent-01

python -m pytest -q experiments/basic-workspace/tests
```

`NEW` must be a fresh output directory. The genuine run command starts one model session per mission and never retries. Provider settings are read from the operator's existing ignored Pi configuration; no endpoint or credential is stored here.

The full Workspace suite passed **238 tests and 80 subtests**. No inference was run during the deterministic preflight or finalization. This is one successful extraction trial and does not establish general reliability for arbitrary blocks or programs.
