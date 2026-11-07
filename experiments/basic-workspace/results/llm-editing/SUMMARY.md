# Real LLM BASIC editing comparison

## Run configuration

This is a genuine tool-calling run against the local OpenAI-compatible Ollama
endpoint, not the offline protocol fixture. Model requested: `gemma4:latest`
(Gemma 4, 8B, Q4_K_M; Ollama 0.20.0). Settings: temperature 0, seed 17,
thinking off, 1,024 output tokens per response, 8 iterations, 14 tool calls per
session, 120-second request timeout, and a 64,000-byte serialized-context cap.
No authentication was configured. Results keep only a loopback endpoint
classification, not a full endpoint URL. The run used the local CPU inference
worker on Skip; latency should not be generalized to hosted inference.

All 15 non-conflict tasks were run once per arm, for 30 independent sessions.
Each arm received the same task and model settings. The semantic arm used the
eight structured Workspace tools; the text arm used in-memory read, search,
exact-context patch, diff and subset-diagnostic tools. Neither arm received the
oracle or source in its initial prompt. No source file was edited. The provider
returned token accounting for every session.

## Outcomes and cost

| Arm | Correct | Safe refusals | Turns | Tool calls | Failed tool calls | Provider input tokens | Provider output tokens | Tool response bytes | Inference wait | Mean / median session |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Semantic Workspace | 15/15 (100%) | 3 | 58 | 43 | 5 | 124,466 | 15,705 | 38,798 | 20.17 min | 80.7 / 81.9 s |
| Text tools | 12/15 (80%) | 3 | 82 | 70 | 3 | 128,477 | 27,613 | 32,748 | 30.35 min | 121.4 / 103.9 s |

The paired outcomes were 12 ties and 3 semantic wins; there were no semantic
losses. This is a small, single-model, single-seed run, not a general accuracy
estimate. Semantic editing used 38.6% fewer tool calls and 10.2% fewer provider
tokens overall, with 33.5% less accumulated inference wait. Serialized model
requests totaled 598,093 bytes for semantic and 689,146 for text; raw model
response bodies totaled 81,207 and 124,741 bytes. Tool execution itself was
negligible in both arms. The full paired batch took 50.53 minutes wall time.

Summing source-bearing string fields actually returned by tools (read ranges,
search snippets, references, symbol names, preview diffs and explicit renders)
gives 1,267 bytes for semantic and 23,300 bytes for text. This is a source-text
payload measure, not total tool output: semantic metadata makes its complete
tool responses larger. The schema definitions were 62,415 semantic bytes and
28,005 text bytes in the per-session compact representation; repeated across
turns, the standalone encoded schema estimate is 241,338 and 153,094 bytes.
The provider's prompt-token totals include schema and conversation context and
are the authoritative token measure.

| Task | Semantic | Text |
|---|---|---|
| local rename with decoys | Pass | Pass |
| case-insensitive local reference | Pass | Pass |
| function rename | Pass | Fail: result assignment left unchanged |
| GOTO renumber | Pass | Pass |
| GOSUB renumber | Pass | Pass |
| ON GOTO renumber | Pass | Pass |
| atomic rename + renumber | Pass | Pass |
| name collision | Safe refusal | Safe refusal |
| move function | Pass | Pass |
| ambiguous array/function | Safe refusal | Safe refusal |
| incomplete function | Safe refusal | Safe refusal |
| colon-separated scope | Pass | Pass |
| historical `fn` | Pass | Fail: no edit/final answer |
| historical `mastermind` | Pass | Fail: ambiguous text patch hit 12 occurrences |
| historical `poker` | Pass | Pass |

The three text-arm failures were:

- `function_rename`: renamed the declaration and call but left the function
  result assignment using the old name; it reached the iteration limit.
- `historical_fn`: read the complete small source but stopped without an edit
  or final answer.
- `historical_mastermind`: exhausted the iteration limit after repeated
  ambiguous text patches; `10 REM` occurred 12 times, so the patch guard
  rejected the attempt.

All three required-refusal tasks were handled safely by both arms: a name
collision, an ambiguous array/function construct, and an incomplete function.
Semantic tool-call errors were recoverable and did not cause incorrect final
results. Text had two patch repair cycles in the `mastermind` trial.

The full per-turn traces, provider usage, exact tool schemas, task categories,
source sizes and tool byte counts are in `run.json`, `tool-definitions.json`
and `trials.csv`. `run.json` omits credentials and the complete endpoint URL.
The `pilot-*` JSON files are exploratory schema/output-limit checks and are not
included in the 15-task score. The initial schema pilot failed one semantic
rename; the compact one-task pilot passed both arms; the 512-token partial run
was stopped after truncation-related failures. The two identical saved copies
of that partial run were reduced to one artifact.

## Compact discovery mechanics

The separate deterministic query comparison measured the existing broad query
sequence against the compact exact/unique symbol lookup:

| Interface | Calls | Request bytes | Response bytes |
|---|---:|---:|---:|
| Broad discovery | 90 | 31,631 | 64,680 |
| Compact discovery | 59 | 26,336 | 19,279 |

Compact discovery reduced calls by 34.4% and response bytes by 70.2%. It
returns a unique symbol's scope, type, reference count, revision and diagnostic
summary together, while leaving full reference lists on demand. Ambiguous
matches are not selected automatically. These are scripted API mechanics, not
LLM trial measurements.

## Two-agent conflict

The accepted scheduled run is in `multi-agent.json`. Two genuine model sessions
used separate `AgentToolAdapter` views over one persistent Workspace server and
both discovered/previewed against revision 1. Agent A committed `X` → `POINTS`
at revision 2. Agent B's prepared revision-1 proposal then received the server's
`STALE_REVISION` rejection. B inspected the new revision, found that the old
symbol name was gone, and explicitly refused to rebase. The final document
remained at revision 2 with `POINTS`; the runner did not auto-retry B's edit.

The first scheduler pilot is preserved as `multi-agent-pilot-rebased.json` and
is not counted as a successful conflict demonstration: that pilot let B inspect
revision 2 and rebase to revision 3 without first receiving a stale rejection.
The scheduler was then tightened to require the prepared base-revision attempt.

## What this says about the interface

For scope-sensitive renames, case-insensitive references, function movement,
and line-label updates, the semantic tools gave the model a discoverable target
identity and a single atomic operation. Text tools remained effective for
simple, local changes and had lower response-byte volume. The observed failures
show the semantic interface's value on bound references and its cost in tool
schema/context; it is not uniformly cheaper. A compact unique-symbol query was
useful in scripted measurements, but the semantic run still had higher tool
response bytes than text.

The text arm uses the Workspace subset parser only for diagnostics. No compiler
or interpreter was run after each model edit. Thus the oracle checks final
source/refusal outcomes, not behavioral equivalence of arbitrary BASIC code.
The historical fixtures were read-only and invoked only through these editing
tools; interactive or destructive demos were not executed.

## Atlas boundary

The independent runner and reusable Workspace subprocess client were tested
with a real local model. Atlas Agent integration remains unverified: the
inspected Atlas Python executor has a sealed, fixed tool profile and no
supported structured Python callback seam. This experiment did not change or
bypass that contract. The adapter remains an independent integration reference,
not a claim of Atlas registration.

## Reproduction

See `REPRODUCE.md` for exact commands. Run the harness fixture for protocol
mechanics; it is not an LLM result. Re-running actual model trials requires a
configured endpoint and will consume inference time. The comparison is
single-run and temperature/seed settings do not guarantee deterministic
provider behavior.
