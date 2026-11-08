# Cycle 14B — Calibrated preflight and longitudinal continuation

## Outcome

The provider is **verified compatible** with the agent runner's actual request style. The real three-mission development sequence completed after correcting a stale Mission 3 policy baseline. The initial failed preflight, the first failed Mission 3 session, and all earlier Cycle 13 evidence remain preserved unchanged.

The existing `REPORT.md` is the original chronological report for the initial Cycle 14 stop. This file records the Cycle 14B continuation; it does not replace that evidence.

## Preflight

The requested Sushi endpoint advertised the configured Qwen model. A single compatibility probe using the runner's normal `tool_choice: auto` protocol returned the required `preflight_ok({"ok": true})` call.

- Classification: `verified_compatible`
- Model-list request: HTTP 200; requested model present
- Probe: 4.52 seconds, finish reason `tool_calls`
- Usage: 297 prompt, 67 completion, 37 reasoning tokens; cached-token count reported as 0
- Request/response: 552 / 919 bytes
- Configured request timeout: 60 seconds; bounded cold-server preflight override: 90 seconds

The previous failed probes used an imposed `required` choice, a 24-token budget, then a 128-token/45-second request. Those outcomes did not establish provider incompatibility. Sanitized evidence is in `calibrated-preflight-01/provider-preflight.json`; the earlier `provider-preflight.json` is unchanged.

## Longitudinal model sessions

Missions 1 and 2 were genuine model sessions in `calibrated-run-01`: the model created `IS_SENIOR(ID)` as a bound caller of `AGE_BY_ID`, then changed the age for logical entity 205 from 42 to 55. Both commits passed interpreter/JIT checks. Their actual transcripts are retained.

The first Mission 3 request was a genuine fresh-context attempt, but its valid initial preview was rejected as `MISSION_EXISTING_FUNCTION_CHANGED`. The campaign had captured the comparison baseline before Mission 2's edit. The subsequent exploratory calls exhausted the bounded tool-call budget without a commit. This failed transcript remains untouched in `calibrated-run-01/mission-3-is-adult/`.

For the corrected continuation, the committed Mission 1 and 2 operations were replayed into a new Workspace. The revision-4 semantic fingerprint matched the prior recovery checkpoint. The checkpoint contains 19 portable handles and is 4,282 bytes (roughly 773 tokens by the local byte/4 estimate); the old conversation was not included in the new model request. The Mission 3 gateway baseline was captured from the live revision-4 state after the age edit.

The resumed model discovered `AGE_BY_ID`, created `IS_ADULT(ID)` with a typed call bound to that function, previewed and committed revision 4 → 5, then validated. It used 5 turns and 5 dispatched tool calls. The preserved transcript reports 19,445 prompt tokens, 1,660 completion tokens, 17,631 cached prompt tokens, and 38.22 seconds of inference. These are provider-reported figures, not byte-derived estimates.

Across the successful path (the original Mission 1 and 2 sessions plus corrected Mission 3): 15 model turns, 16 tool calls, 47,091 prompt tokens, 3,797 completion tokens, 38,174 cached prompt tokens, and 94.32 seconds of inference. This is one longitudinal run, not a statistical comparison.

## Validation and replay

At revision 5, both MIR engines agreed:

| Logical ID | Age | IS_SENIOR | IS_ADULT |
|---:|---:|---:|---:|
| 101 | 25 | 0 | 1 |
| 205 | 55 | 1 | 1 |
| 900 | 53 | 1 | 1 |
| 999 | -1 | 0 | 0 |
| 2 | -1 | 0 | 0 |

Isolated boundary checks passed at ages 17 and 18. Unknown IDs remained false. The full committed constructive stream rebuilt the program in a fresh Workspace and passed structural, binding, behavioral and interpreter/JIT equivalence. All 24 portable semantic identities were remapped; the reconstructed call graph retains both composed functions' dependency on `AGE_BY_ID`.

The new HTML, SVG, event journal, recovery checkpoint, operation stream and equivalence record are under `calibrated-resume-02/`. The journal separates real model actions from deterministic replay and host validation. No Kitty graphical session or shader screenshot was tested.

## Commands

```sh
python3 experiments/basic-workspace/scripts/provider-preflight.py \
  --probe-timeout 90 \
  --output experiments/basic-workspace/results/semantic-replay/longitudinal-01/calibrated-preflight-01/provider-preflight.json

python3 experiments/basic-workspace/scripts/longitudinal-campaign.py \
  --output-dir experiments/basic-workspace/results/semantic-replay/longitudinal-01/<new-run>

python3 experiments/basic-workspace/scripts/resume-longitudinal-mission3.py \
  --source-run experiments/basic-workspace/results/semantic-replay/longitudinal-01/calibrated-run-01 \
  --output-dir experiments/basic-workspace/results/semantic-replay/longitudinal-01/<new-resume>

python3 experiments/basic-workspace/scripts/finalize-longitudinal-resume.py \
  --source-run experiments/basic-workspace/results/semantic-replay/longitudinal-01/calibrated-run-01 \
  --resume-run experiments/basic-workspace/results/semantic-replay/longitudinal-01/calibrated-resume-02

python3 -m unittest discover -s experiments/basic-workspace/tests -v
```

`resume-longitudinal-mission3.py` starts a fresh model conversation; the finalizer is deterministic and makes no provider request. For a new campaign, use a new empty output directory and the current local ignored provider configuration.

## Regression

The complete Workspace suite passed: **115 tests** (the 109-test baseline plus six provider/longitudinal checks). It covered mocked preflight success, truncation, timeout, malformed arguments, wrong tool, unavailable model, and optional required-choice diagnostics. Test-generated result changes were discarded by restoring the pre-test results snapshot; prior MPDecimal and experiment artifacts were retained.

## Remaining limits

- The initial failed Mission 3 transcript illustrates how repeated opaque policy errors can trigger costly model retries; the corrected run avoided that loop.
- The resume used the same model/provider in a fresh conversation, not a persistent model process.
- Checkpoint token count is an estimate; only per-request provider usage is authoritative.
- No text-editing comparison or statistical claim is made.
- The gateway constrains only calls routed through this experiment's exposed tools.
