# Cycle 12 — AGE_BY_ID semantic replay and model edit

## Outcome

**Passed the vertical experiment with one genuine local-model session.** The program was constructed from typed operations in an empty Workspace, edited through the controlled mission gateway, executed using MIR interpreter and JIT, and reconstructed in a fresh Workspace from a handle-based operation stream.

The validated result is:

| Logical ID | Before | After |
|---:|---:|---:|
| 101 | 25 | 25 |
| 205 | 42 | 47 |
| 900 | 53 | 53 |
| 999 | -1 | -1 |
| 2 | -1 | -1 |

The last case confirms that a logical ID is not an array index. Both engines returned these values before and after the edit, and both returned the same values in the reconstructed workspace. The historical BASIC FUNCTION/IF defect was not used as an oracle.

## Verified architecture and minimum changes

`AUDIT.md` records the starting audit. The live Workspace keeps canonical tokens as the editable state. The campaign constructs the existing nested numeric subset with `create_numeric_function`; the immutable compilation projection is then derived from that model. It is neither an editable AST nor a source-reparse path.

Two narrow additions support safe replay and policy checks:

1. Projected assignment nodes retain the stable statement identity already indexed by Workspace.
2. `preview_transaction_semantics` runs the existing transaction validator on a private candidate and returns a typed, read-only projection. The live document is not changed. Commit still calls `apply_transaction` at the expected revision after repeating the candidate check.

The projection serializer includes function signatures, scoped IDs, arrays and bounds, typed expressions, assignment targets, statement ordering, nested IF/FOR blocks and loop limits. The campaign maps these transient identities to declared handles. Structural comparison compares the full normalized typed tree. Binding comparison separately compares normalized reference edges. It does not use rendered BASIC as the replay input or as the equivalence check.

The only supported mission operation is replacing the numeric RHS of the statement whose verified target is the age cell for logical ID 205. The gateway first proves that `PERSON_ID` has one initializer for each ID and maps 205 to slot 1, then proves `PERSON_AGE[1]` is initialized to 42. It authorizes any finite value in `[0,130]`, not only 47. A separate host oracle enforces the requested task result 47. Preview authorization is not a reservation, and the gateway repeats revision, target and full typed-candidate checks at commit.

This is a single controlled API boundary. It does not constrain unrestricted Workspace access, shell, filesystem or process access outside the tools exposed to the model.

## Real model interaction

The run used the previously configured local Ollama-compatible endpoint and `gemma4:latest`; committed metadata stores only that the endpoint was loopback HTTP with a chat-completions API. No URL or credential is in these artifacts. Temperature was 0, seed 17, max output 800 tokens and per-request timeout 60 s.

The model was not given the target statement ID. Its actual sequence was:

1. `discover_symbols` — obtained the function, parameter, arrays and loop-variable IDs.
2. `inspect_statements` — inspected the typed assignments and found the age initializer at slot 1.
3. `preview_age_edit` — submitted the discovered statement ID and value 47; the gateway accepted the candidate at revision 2 → 3.
4. `commit_age_edit` — committed exactly that accepted transaction at revision 3.
5. `run_lookup_checks` — ran both engines.
6. Final answer — claimed the mission complete.

The 67-event journal contains 14 proposed operations, 6 accepted previews, 8 rejected operations and 3 commits after the initial seed: the model's age edit plus the fresh-workspace replay constructor/edit. The model itself made one commit.

The host independently ran all five expected cases in both engines and verified the fresh-workspace replay. The model used 6 request/response turns, 5 tool calls, 10,510 prompt tokens, 909 completion tokens and 0 provider-reported cached prompt tokens. Serialized requests totaled 46,910 bytes, responses 4,888 bytes and tool schemas 2,069 bytes. Total elapsed campaign time was about 69.36 s, of which reported model inference wait was 69.08 s.

One harness defect was visible in the genuine transcript: `run_lookup_checks` returned post-edit results but still labeled the pre-edit age-42 map as `expected`. The model explicitly noticed the inconsistency. The independent host oracle was correct and confirmed the update. The tool has since been corrected to report the mission expected values after commit and a `passed` flag. The recorded transcript is intentionally left unchanged; it remains evidence of the actual session and is not retroactively repaired.

No hidden model reasoning is recorded or claimed. The stored assistant content, tool selections/arguments, tool results, request messages, provider usage and timestamps are the actual protocol observations.

## Constructive metafile versus historical journal

The constructive stream contains the original typed function constructor and the one successful semantic edit addressed by `people.age.205`. It declares 14 portable handles: function, parameter, both arrays, loop variable and stable assignment handles. The fresh workspace generated different opaque `sym_` and `stmt_` values; references were resolved again through those handles. No original opaque ID is in the stream.

The stream intentionally excludes discoveries, previews, rejected attempts and the model's final statement. Those remain in `history.jsonl` and `agent-session.json`. This reduction is sufficient to rebuild the committed program, but it does not preserve why the model chose the target or the rejected-operation chronology; consult the historical journal for that evidence. Rejected attempts are never inserted into the constructive stream.

Equivalence levels are separate in `equivalence.json`:

- **Structural:** complete normalized typed projection equality, including nested control flow and statement ordering.
- **Binding:** equality of normalized edges for function, parameter, array, loop-variable, assignment-target and expression references.
- **Behavioral:** the fresh workspace returns the same results as the original committed workspace for the five-input corpus.
- **Engine agreement:** MIR interpreter and JIT results match the independent expected map.

The run reported all four as true. Transient IDs, token serialization and MIR output are not required to match byte-for-byte.

## Mission enforcement and negative controls

Eight scripted violations were rejected: function rename, entity-ID edit, unrelated age edit, loop-bound edit, IF-condition edit, stale revision, unknown statement ID and age 131. Every rejection had no revision increment, canonical-render change, binding/structure change or execution-result change. A preview changing the authorized cell to 48 was accepted by the policy range, then left uncommitted; this confirms authorization is not hard-coded to the functional goal. A unit test also races a valid preview with a competing workspace revision and verifies the stale commit is rejected without an additional mutation.

These are explicitly **scripted controls**, not model actions. The genuine model did not attempt policy violations.

## Measurements and artifacts

| Measure | Result |
|---|---:|
| Initial typed construction | 4.58 ms |
| Scripted negative-control suite | 168.79 ms |
| Fresh replay plus equivalence | 28.64 ms |
| Visual generation | 2.19 ms |
| Portable handles remapped | 14 |
| Constructive stream | 6,054 bytes |
| Historical journal | 138,919 bytes |
| HTML replay | 154,687 bytes |
| SVG overview | 10,634 bytes |

The HTML and SVG sizes include the genuine tool trace and typed snapshots. The journal is much larger than the constructive stream because it keeps actual request/response context, discoveries and eight scripted policy controls. No benchmark conclusion about semantic versus text editing is drawn from this one campaign.

Artifacts in this directory:

- `AUDIT.md` — verified starting architecture and scoped design.
- `execution-profile.json`, `mission.json` — machine-readable contracts.
- `constructive-operations.json` — portable replay input.
- `history.jsonl` — ordered observed event journal; scripted controls are labeled.
- `agent-session.json`, `agent-tool-schemas.json` — real request/tool transcript and exact exposed schemas.
- `equivalence.json`, `controls.json`, `summary.json`, `metrics.json` — machine-readable outcomes.
- `replay.html` — offline step-through viewer, showing committed state separately from candidate preview.
- `overview.svg` — static mission and event summary.
- `reproduce.sh` — tests plus deterministic fresh campaign in a separate output folder.

## Kitty

Kitty 0.49.2 is installed, and ANSI playback runs in a normal terminal. This execution environment had no active Kitty remote-control socket (`KITTY_LISTEN_ON` was unset) and no visible Kitty process. Shader activation and remote screenshots were therefore **not tested**; no screenshot is included. Kitty effects are optional and not required to understand the replay.

## Reproduction

From `experiments/basic-workspace/`:

```sh
python3 -m unittest discover -s tests -p 'test_*.py'
python3 scripts/age-by-id-campaign.py --deterministic-only --output-dir results/semantic-replay/age-by-id/reproduced-scripted
python3 scripts/render-semantic-replay.py --trace results/semantic-replay/age-by-id/history.jsonl --output-dir results/semantic-replay/age-by-id
python3 scripts/kitty-replay.py results/semantic-replay/age-by-id/history.jsonl --step
```

To conduct a new one-shot model run, set `BASIC_WORKSPACE_LLM_ENDPOINT`, `BASIC_WORKSPACE_LLM_MODEL` and optionally `BASIC_WORKSPACE_LLM_API_KEY` in the environment, then run `python3 scripts/age-by-id-campaign.py --output-dir <new-output-directory>`. Use a new output directory to preserve this recorded run. Do not reuse the old endpoint configuration blindly; the runner never records the full endpoint or key.

## Limitations and conclusion

The mechanism is validated for this nested numeric program and one mission-scoped assignment edit. The gateway is purpose-built, not a general policy engine; its verified ID-slot map is based on the constructed fixture. The current constructive API still represents names in transaction-local constructor references, while cross-operation references use portable handles. The historical journal is evidentiary, not a minimal replay file. The model run is one observation and not a statistical claim. Persistent runtime-state migration, other data types and broader mission policy remain out of scope.

The result supports a **small algorithmic metafile experiment**: typed constructor operations and portable semantic handles reconstruct a meaningful program without source reparsing. It does not justify replacing the canonical token model or adopting a generalized metafile architecture yet. The next falsification should use a different program shape and independently authored policy target, while fixing the discovered validation-tool expectation issue.
