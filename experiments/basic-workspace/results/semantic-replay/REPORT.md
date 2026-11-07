# Cycle 11 — Semantic replay and mission enforcement

## Outcome

This is a **scripted vertical experiment**, not a real LLM trace. It uses the
existing canonical Workspace and transaction APIs unchanged. Starting from an
empty virtual document, it constructs `DOUBLE(X)=X*2`, runs it through MIR,
previews and commits the permitted `X*3` edit, denies a function rename, then
reconstructs the revised program in a second empty Workspace from typed
operations with symbolic handles. The original workspace remains authoritative
throughout its campaign; rendered BASIC is used only for the human report.

The audit before implementation is in `AUDIT.md`. The baseline was commit
`0d3f89b12a2eac2f82752a7016de0dabfe92d183`; the original 85 tests passed
before changes. The final suite has **91 passing tests**.

## Three distinct records

1. **Semantic program state** remains the canonical lossless token model and
   its derived indexes. Transactions use the existing candidate-validation,
   revision-check and atomic publication path.
2. **Constructive metafile** (`constructive-operations.json`) contains two
   versioned typed operations and portable handles for the function,
   parameter and result statement. It contains no source text, MIR or original
   `sym_`/`stmt_` identifiers. On replay, creation results bind handles to the
   new Workspace's IDs; the expression reference is resolved through that
   mapping. Missing/unknown handles fail explicitly.
3. **Historical operation journal** (`history.jsonl`) records what this
   scripted harness actually proposed, previewed, committed, rejected,
   validated, executed and replayed. It keeps the forbidden rename and
   timings; that rejection is deliberately absent from the constructive
   stream. `rationale` values are harness-supplied claims, not verified
   reasoning. Sequence numbers and semantic payloads are deterministic in
   shape; timestamps, UUIDs and timings are naturally run-specific.

The operation envelope is versioned and carries mission/profile IDs,
transaction ID, base revision, preconditions, target handle, typed arguments,
rationale and outcome. Preview and commit outcomes are separate journal
events; committed envelopes include their resulting revision and alias
bindings. The BWM transport and MIR instruction stream are not agent-facing
metafiles.

## Execution and mission contracts

`execution-profile.json` names `basic-workspace.numeric-control.v1` and
classifies guarantees, implementation-dependent behavior, and unsupported
semantics. The campaign checks the profile reference and required interpreter
and JIT capabilities before replay. In this supported slice, `DOUBLE(9)` is
18 before the edit and 27 after it in both engines. The wider profile records
the existing double, truth/comparison, array, string, bounded-loop, function
call, error and persistent-instance limits; it does not claim full historical
BASIC compatibility.

`mission.json` is a versioned MissionContract. Its controlled gateway allows
only the exact initial construction and an edit to the `double.result` handle
whose expression is `X*3`. It checks the base revision, profile, operation,
target mapping and typed expression before preview and repeats authorization
immediately before the Workspace commit. The attempted `rename_symbol` is
rejected as `MISSION_OPERATION_FORBIDDEN` at revision 3; both revision and
rendered canonical state are unchanged. The test reaches the gateway, not the
private authorization helper.

The trust boundary is intentionally narrow: this policy applies only when all
campaign writes go through `MissionGateway`. A process with direct access to
`Workspace`, source files or arbitrary tools can bypass it. This is not a
general authorization system. Human approval hooks and agent-supplied
capability tokens are not implemented.

## Replay and equivalence

The campaign ran the following observable results:

| State | MIR interpreter | MIR JIT |
|---|---:|---:|
| Initial `DOUBLE(9)` | 18 | 18 |
| After permitted edit | 27 | 27 |
| Fresh-workspace replay | 27 | 27 |

Four equivalence results are reported independently in `equivalence.json`:

- **Structural:** same supported function, parameter, result assignment and
  normalized expression after replay — pass.
- **Binding:** references resolve to the corresponding logical handles — pass.
- **Behavioral:** expected outputs 18 and 27 reproduced — pass.
- **Engine agreement:** interpreter and JIT agree in original and replayed
  programs — pass.

The three semantic identities were all remapped to new UUIDs. IDs, token UUIDs,
MIR binaries and machine code need not match. No BASIC source was rendered,
reimported or reparsed during construction or replay. Diagnostic source
snapshots are taken from committed Workspace states after operations; preview
diffs are displayed separately and are never shown as the current program.

The journal has 29 events. It shows the exact sequence: empty checkpoint,
typed construction, initial execution, proposed edit, preview, commit, updated
execution, denied rename, fresh-workspace reconstruction, equivalence check.
Both preview/commit pairs and the rejection are linked by transaction IDs.

## Visualization and Kitty

`render-semantic-replay.py` reads `history.jsonl`, `execution-profile.json` and
`mission.json`; it does not call Workspace or re-run execution. It creates a
self-contained `replay.html` with previous/next controls, event timeline,
committed source, separate proposed diff, operation diagnostics and mission
results. `overview.svg` is a static trace-derived summary. Rendering the same
recorded event trace twice produces byte-identical HTML and SVG. The HTML
includes both diagnostic source and a normalized semantic-structure snapshot
for the last committed event at each timeline position.

Kitty **0.49.2** is installed. Kitty's custom shaders were introduced in
0.49.0, and its documented `shader_event` action can send `user:<name>` events
to event-driven shader pipelines. The optional `kitty-replay.py
--shader-events` emits semantic event names only when `KITTY_LISTEN_ON` is
provided. The operator's Kitty config has no active `listen_on` or remote
control setting; this harness has no controlling TTY. `kitty @ ls` failed with
`open /dev/tty: No such device or address`. Therefore remote shader activation
and a Kitty screenshot were **not tested**, and no screenshot is claimed.
ANSI automatic playback was exercised headlessly; step playback is available
with `--step`. No Kitty configuration was changed.

Kitty's shader layer remains optional visual emphasis over the semantic
renderer. It sees rendered frames and named events, not symbols, transaction
payloads or arbitrary semantic uniforms. See the [Kitty Custom Shaders
documentation](https://sw.kovidgoyal.net/kitty/custom-shaders/).

## Measurements

Recorded in `metrics.json` (one local campaign run):

- 2 constructive operations; 2 replay operations; 0 replay failures.
- 1 mission violation rejected; 0 unexpected model differences.
- 3 semantic handles rebound in the new workspace.
- Constructive stream: 2,133 bytes; historical journal: 31,153 bytes.
- Campaign: 11.5 ms; replay phase: 3.4 ms; rendering: 1.1 ms.
- Original validation/execute calls used both fresh-worker MIR engines. Their
  measured execution batches were approximately 2.7–3.0 ms each, inclusive of
  projection and native worker starts.

The stream is sufficient and portable, not compact compared with the tiny
rendered example. The larger journal preserves previews, rejected actions,
snapshots, timing and runtime observations. That is an expected difference in
purpose, not evidence for replacing the Workspace model.

## Kitty and HTML commands

From the repository root:

```sh
experiments/basic-workspace/scripts/reproduce-semantic-replay.sh
xdg-open experiments/basic-workspace/results/semantic-replay/replay.html
python3 experiments/basic-workspace/scripts/kitty-replay.py \
  experiments/basic-workspace/results/semantic-replay/history.jsonl --step
python3 experiments/basic-workspace/scripts/kitty-replay.py \
  experiments/basic-workspace/results/semantic-replay/history.jsonl --auto 0.8
```

`--shader-events` is optional and requires an already configured Kitty remote
control socket and a custom shader pipeline subscribed to events such as
`user:semantic-commit`. The experiment does not modify Kitty settings or
require shaders for comprehension.

## Falsification and limits

The tested falsification checks passed: the stream contains no original
opaque IDs; all three handles resolve in a fresh document; normalized
structure and binding match; denied rename leaves revision/render unchanged;
the interpreter and JIT reproduce expected values; the HTML renderer uses
only recorded snapshots and separates previews; and execution/replay do not
consume rendered BASIC. This is one deliberately small scripted example, not
general replay correctness. It does not yet replay the loop-and-array
`AGE_BY_ID` scenario, model arbitrary transaction dependencies, or validate
metafile portability across profile versions beyond exact profile-ID refusal.

## Reproduction and final repository state

```sh
experiments/basic-workspace/scripts/reproduce-semantic-replay.sh
```

The command builds the existing MIR worker, runs the complete Workspace
suite, executes the campaign, and renders HTML/SVG. The campaign labels itself
`scripted`; there was no LLM involved. No historical BASIC compiler, MIR,
MADC or AOT source was modified. Existing MPDecimal changes at the repository
root were preserved.

Recommendation: continue the algorithmic metafile as a small, versioned,
handle-based sequence of typed Workspace operations, with execution-profile
requirements and deterministic validation. Do not replace canonical tokens,
the semantic model, BWM or MIR with it. The next useful falsification is replay
of the already validated array/control-flow lookup, then a dependency-bearing
schema evolution. Track stream size and policy complexity; the current
minimality is promising, but no broad architectural generalization is yet
justified.
