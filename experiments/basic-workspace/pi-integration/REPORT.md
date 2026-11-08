# Cycle 16B report — Pi semantic tool grammar repair

## Outcome

The corrected Pi tool grammar supported one genuine bounded Sushi/Qwen mission. Pi discovered the revision-4 `AGE_BY_ID` function, proposed `IS_ADULT(ID)` as a typed function containing a semantic call to that function, received an accepted preview, committed revision 5, and invoked validation. The independent host oracle passed MIR interpreter/JIT checks, the age-17/18 boundary fixture, and a fresh-workspace semantic replay.

The original failed run remains preserved unchanged at [`results/real-pi-01/`](results/real-pi-01/). It is failure evidence, not part of the successful retry. The successful retry is [`results/real-pi-02/`](results/real-pi-02/).

## Corrected constructor grammar

The preview tool now exposes a mission-bounded TypeBox schema with discriminated `anyOf` branches. The captured schema is the exact JSON Schema returned by Pi 1.5.0 `ExtensionAPI.getAllTools()`, not a parallel handwritten copy. The complete five-tool schema is **20,343 bytes**; the constructor's `body.items` schema is **7,932 bytes**. It has typed array items, no empty `{}` item schemas, no `$ref` recursion, required properties, and `additionalProperties: false`.

Supported this mission:

- Numeric literal and local `ID` reference.
- A single numeric binary expression level with the supported comparison/arithmetic operator enum.
- A one-argument semantic call to the discovered portable handle `age_by_id.function`, usable as a binary operand.
- Result assignments with the explicit `{"kind":"result"}` target.
- A bounded `IF` condition with result-assignment `then` and optional `else` blocks; nested `IF` and deeper binary trees are intentionally outside this schema.
- The exact numeric function signature fields and one `ID` parameter.

The tool description includes one result-assignment example and one portable bound-call example. It does not provide the completed `IS_ADULT` body. Python gateway validation remains authoritative; malformed shapes receive machine-readable path diagnostics before preview, and mission-policy denials remain separate.

The eight exact rejected bodies from `real-pi-01` were checked against both the captured active Pi schema and the gateway: all eight are still rejected, at the appropriate boundary, with revision unchanged. A known-good typed IF/call request passes the exact active schema and gateway preview without mutating the seed.

## Genuine Pi run

Command:

```sh
python3 experiments/basic-workspace/pi-integration/run_cycle16.py \
  --output experiments/basic-workspace/pi-integration/results/real-pi-02 \
  --timeout 180 --open-browser
```

| Measure | Cycle 16B retry |
|---|---:|
| Pi / model | Pi 1.5.0 / Qwen3.8-Flash-Next-Sushi-STQ-2.75bpw |
| Model turns | 5 |
| Tool calls | 5: discover, inspect, preview, commit, validate |
| Malformed model proposals | 0 |
| Accepted previews / commits | 1 / 1 |
| First valid preview | Call 3 of 5 |
| Workspace revision | 4 → 5 |
| Provider input / output tokens | 9,142 / 3,388 |
| Provider cache-read tokens | 31,676 |
| Inference and process wall time | 86,543.59 ms |
| Full Pi event stream | 441,386 bytes (local raw session) |
| Sanitized observed session | 96,100 bytes |
| Active schema | 20,343 bytes |
| Loopback RPC benchmark | 74.0 ms startup; 0.082 ms median, 0.252 ms p95 (separate microbenchmark) |

The cache count is provider-reported and is not treated as free input. No text-editing baseline was run. The historical Cycle 14B Python Mission 3 reference completed in five turns and five calls with one commit, 19,445 input, 1,660 output, 17,631 cached input tokens and about 38.2 seconds. Prompts, schemas, and orchestration differ, so this is not a controlled comparison.

## Validation and replay

The host independently checked the actual committed revision 5. Both MIR engines agree and match the host oracle:

| ID | Age | IS_SENIOR | IS_ADULT |
|---:|---:|---:|---:|
| 101 | 25 | 0 | 1 |
| 205 | 55 | 1 | 1 |
| 900 | 53 | 1 | 1 |
| 999 | -1 | 0 | 0 |
| 2 | -1 | 0 | 0 |

Isolated threshold fixtures passed at age 17 (adult 0) and age 18 (adult 1), under interpreter and JIT. `AGE_BY_ID` and `IS_SENIOR` remained unchanged; the `IS_ADULT → AGE_BY_ID` call is semantically bound. The portable operation stream rebuilt the program in a fresh workspace: structural, behavioral, and interpreter/JIT equivalence all passed, with **24** semantic identity remappings.

## Event and visual evidence

The live browser started before inference. It received the committed seed, Pi discovery, a preview at revision 4, and only then the authoritative revision-5 commit snapshot. The viewer header distinguishes the committed seed from the agent mission result. The final artifacts are generated from normalized evidence:

- [`visual-replay-generic.html`](results/real-pi-02/visual-replay-generic.html) — offline code-first replay.
- [`visual-frames-generic.json`](results/real-pi-02/visual-frames-generic.json) — generic compiled frames.
- [`visual-events.jsonl`](results/real-pi-02/visual-events.jsonl) — presentation event stream.
- [`visual-replay-commit.png`](results/real-pi-02/visual-replay-commit.png) — real Firefox headless capture of the commit frame.
- [`visual-replay-validation.png`](results/real-pi-02/visual-replay-validation.png) — real Firefox headless capture of host validation and MIR observations.
- [`pi-session-observed.jsonl`](results/real-pi-02/pi-session-observed.jsonl) — sanitized observed Pi session, excluding thinking-channel updates and redacting the local checkout path.
- [`pi-tool-events-from-session.jsonl`](results/real-pi-02/pi-tool-events-from-session.jsonl) — start/end tool events adapted from Pi's actual JSON event stream.

The extension journal `pi-tool-lifecycle.jsonl` was preserved as recorded. It contains the five start events but no end events. The cause was in the gateway deduplication key: it used `toolCallId + empty phase`, so an end event for the same call was classified as a duplicate start. Pi 1.5.0's installed extension event bridge forwards `tool_execution_end`, and the raw Pi session contains five matching end records. The gateway now defaults the idempotency phase to event type; a regression test verifies distinct start/end persistence and duplicate deduplication. The adapted file is explicitly sourced from the genuine Pi stream, rather than retroactively pretending those events appeared in the extension journal.

Validation chronology is also explicit: the first revision-5 validation was requested by the Pi tool and executed by Python; the second was a separate host verification after the Pi call completed. Both traces refer to actual calls and results. No model actions were synthesized.

## Comparison with Cycle 16 failure

The preserved original session made five turns and ten tool calls: one discovery, one inspection, and eight invalid constructor proposals. It had four `MISSION_BODY` and four `MISSION_TARGET` rejections, no accepted previews, no commits, and timed out at 240 seconds with revision still 4. Its schema was only 1,527 bytes and exposed `body.items: {}`.

In the retry, schema size grew to 20,343 bytes, but the constructor body was concretely typed. The agent made one proposal, which previewed successfully, then committed and validated in five total calls within about 86.5 seconds. This single retry supports the diagnosis that schema ambiguity drove the prior failures; it is not statistical evidence of general model reliability.

## Deterministic tests and commands

Focused schema/gateway/viewer tests:

```sh
python3 -m unittest \
  experiments.basic-workspace.tests.test_pi_gateway \
  experiments.basic-workspace.tests.test_pi_schema \
  experiments.basic-workspace.tests.test_visualization -v
```

Full regression:

```sh
python3 -m unittest discover -s experiments/basic-workspace/tests -v
```

Preflight without inference:

```sh
python3 experiments/basic-workspace/pi-integration/run_cycle16.py \
  --preflight-only --output experiments/basic-workspace/pi-integration/results/preflight-08
```

Offline viewer:

```sh
python3 experiments/basic-workspace/scripts/basic-visual.py replay \
  experiments/basic-workspace/pi-integration/results/real-pi-02
```

The complete raw Pi session and isolated session directory remain local and ignored. The sanitized copy retains actual tool arguments/results and complete-message records while omitting transient reasoning updates. The tool restriction is an experiment-level model-visible allowlist, not an operating-system sandbox.

## Limitations

- The constructor grammar is deliberately mission-bounded, not a general recursive semantic authoring schema.
- The model mission is one successful run; no reliability or superiority claim follows.
- Cycle 16B's raw model endpoint and credentials remain only in local ignored configuration.
- This cycle used direct typed tools and a browser, not Pi's interactive full-screen TUI.
- The bridge fix affects future live lifecycle journals; the preserved prior journal is unchanged.
