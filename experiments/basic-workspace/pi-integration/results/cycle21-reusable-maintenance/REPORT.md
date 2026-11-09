# Cycle 21 — reusable semantic maintenance

## Outcome

The same host-configured numeric-literal maintenance gateway handled both the historical two-location cap edit and the new one-location threshold edit. One genuine Pi 1.5.0 / Sushi Qwen session changed `IS_PASSING` from threshold 60 to 40, committed exactly one transaction (revision 4 → 5), requested MIR validation, and settled normally. No scripted edit substituted for the model's operation.

The code-first standalone replay is [real-agent-01/visual-replay-generic.html](real-agent-01/visual-replay-generic.html). The full model session and tool-call chronology are in `real-agent-01/pi-session.jsonl`, `pi-tool-lifecycle.jsonl`, and `pi-lifecycle.jsonl`.

## Mission and semantic result

Mission B changes one typed numeric literal, anchored to the discovered `is_passing.function` and the IF comparison's second operand. The contract requires old value 60 and replacement 40, keeps `clamp_score.function` unchanged, and requires the `IS_PASSING → CLAMP_SCORE` semantic edge to remain present.

The model's accepted preview showed only `60 → 40`; committed BASIC remained at revision 4 until the atomic commit. Revision 5 has the same clamp implementation and call binding. Eleven semantic handles were preserved in the live Workspace; the literal's token identity was preserved while its text changed. Fresh replay remapped all 11 identities.

For the requested corpus (`-100, -1, 0, 1, 39, 40, 41, 49, 50, 51, 59, 60, 80, 100, 200`), both MIR interpreter and JIT agree:

- `CLAMP_SCORE(X) = min(50, max(0, X))`.
- `IS_PASSING(X) = 0` below 40 and `1` at or above 40 after the call to `CLAMP_SCORE`.

The host-owned contract oracle, unchanged-function check, dependency check and replay all passed. Detailed values and per-engine observations are in [validation.json](real-agent-01/validation.json); replay equivalence is in [equivalence.json](real-agent-01/equivalence.json).

## Reusable contracts and production-interface preflight

Mission A is [cycle20-cap50.json](../../contracts/numeric-edit/cycle20-cap50.json); Mission B is [cycle21-is-passing-threshold40.json](../../contracts/numeric-edit/cycle21-is-passing-threshold40.json). Both use the same tool grammar and gateway authorization algorithm. The model-facing syntax contains no mission-specific values; the contract owns the authorized targets and replacements.

Before inference, `cycle21_preflight.py` exercised the actual TypeScript extension handler and JSONL gateway dispatch. It verified:

- The exact five active tools and their captured Pi 1.5 schemas (4,817 bytes).
- Four real Cycle 20 model proposals through the generalized schema and Mission A gateway; all four previews were accepted without changing the committed revision.
- Disposable preview, commit, MIR validation and fresh replay for Mission A (revision 3 → 4) and Mission B (revision 4 → 5).
- Rejection without mutation for incorrect count, undiscovered handle, wrong function, wrong old value, stale revision, ambiguous path, unauthorized dependent-function target, unknown semantic field and invalid partial batch.
- Missing `expression_path` and unknown edit properties fail the actual TypeBox schema. `expression_path: []` remains valid for assignment-root paths.
- Pi tool-call correlation crosses the TypeScript-to-Python boundary as transport metadata, remains available in timing records, and is not accepted as a semantic argument.

The machine-readable result is [dispatch-preflight-03/preflight-summary.json](dispatch-preflight-03/preflight-summary.json). Deterministic preflight is not model-success evidence.

## Genuine model measurements

| Measure | Result |
|---|---:|
| Model / Pi | Qwen3.8-Flash-Next-Sushi-STQ-2.75bpw / 1.5.0 |
| Model turns / tool calls | 5 / 5 |
| Discovery / inspect / preview / commit / validate | 1 each |
| Accepted previews / rejected model proposals / commits | 1 / 0 / 1 |
| Reported input / output / cache-read tokens | 8,608 / 960 / 16,863 |
| Pi-reported total tokens | 26,431 |
| Pi-observed elapsed time | 116,759.9 ms |
| Gateway processing (five semantic tools) | 292.555 ms |
| Active tool schema | 4,817 bytes |
| Constructive stream / event journal / session stream | 5,235 / 12,663 / 395,377 bytes |
| Visual frames / standalone HTML | 7 / 31,991 bytes |
| Commit revision | 4 → 5 |
| Fresh replay identity remappings | 11 / 11 |

The provider usage values are reported by Pi. Cache-read is reported separately; it is not interpreted as new uncached input. One session is feasibility evidence, not a performance comparison. Mission A and B contract files are 1,763 and 1,511 bytes respectively. The schema remained the same byte size as the previous Pi schema capture despite the edit-count bounds becoming 1..8.

## Reuse assessment and limitations

The reusable boundary is adequate for the two tested maintenance missions: edit target discovery, candidate comparison, count/scope/value checks, dependency preservation, preview, commit and validation are contract-driven. The supported host oracle language is intentionally limited to `clamp` and `threshold_call`; adding unrelated oracle semantics still requires reviewed host code. This is a small bounded contract interface, not a general policy engine.

The gateway implementation grew by 248 net lines from the Cycle 20 file because it now supports exact later-stream reconstruction and generic contract-driven validation. It avoids another mission-specific gateway and authorization copy, but total implementation LOC did not decrease. The only initial preflight problem was the corrected presentation mapping recorded under `schema-preflight/`; the successful capture is `schema-preflight-02/`. No prior Cycle 20 or Cycle 20B raw evidence was modified.

## Commands

From the repository root:

```sh
python3 experiments/basic-workspace/pi-integration/run_cycle20.py \
  --output experiments/basic-workspace/pi-integration/results/cycle21-reusable-maintenance/schema-preflight-02 \
  --contract experiments/basic-workspace/pi-integration/contracts/numeric-edit/cycle21-is-passing-threshold40.json \
  --baseline-stream experiments/basic-workspace/pi-integration/results/cycle20b-semantic-edit-recovery/real-agent-02/constructive-operations.json \
  --baseline-history experiments/basic-workspace/pi-integration/results/cycle20b-semantic-edit-recovery/real-agent-02/history.jsonl \
  --baseline-validation experiments/basic-workspace/pi-integration/results/cycle20b-semantic-edit-recovery/real-agent-02/validation.json \
  --preflight-only

python3 experiments/basic-workspace/pi-integration/cycle21_preflight.py \
  --output experiments/basic-workspace/pi-integration/results/cycle21-reusable-maintenance/dispatch-preflight-03 \
  --pi-schema-dir experiments/basic-workspace/pi-integration/results/cycle21-reusable-maintenance/schema-preflight-02

python3 -m unittest discover -s experiments/basic-workspace/tests -v
python3 experiments/basic-workspace/scripts/basic-visual.py replay \
  experiments/basic-workspace/pi-integration/results/cycle21-reusable-maintenance/real-agent-01
```

The one genuine model run used the same runner without `--preflight-only`, with `--output .../real-agent-01 --timeout 240`. To inspect the saved visual report, open `real-agent-01/visual-replay-generic.html` in a local browser.

## Validation summary

The complete Workspace suite passed **197 tests**. Deterministic contract/preflight tests passed, the genuine Mission B was authorized and committed, both MIR engines matched the independent oracle, and the complete constructor-plus-edit stream replayed with structural, binding and behavioral equivalence. The schema-preflight mapping issue was fixed before inference. There were no failed or rejected model proposals in the genuine session.
