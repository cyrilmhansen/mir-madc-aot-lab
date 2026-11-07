# Cycle 12 audit before implementation

## Verified baseline

- HEAD is `c22dba6f0c61f145109880be235121e324e95605` on
  `experiment/mir-aot-correctness-cycle3`. Before Cycle 12 edits, the working
  tree also had uncommitted Cycle 8/Cycle 11 result artifacts and MPDecimal
  logs/status. They were kept outside the Cycle 12 commit; MPDecimal files
  were not edited by this experiment.
- The full Workspace suite was rerun: **91 tests passed**. The existing
  `control_flow_lookup_demo.py` also ran successfully.
- `Workspace.create_numeric_function` already creates numeric arrays and
  nested typed `array_assign`, `for`, `if` and `assign` bodies in one atomic
  revision. No new BASIC construct or canonical representation is needed.
- Assignment statements have stable IDs and record target symbol, bound
  references, index token IDs and source line. `list_function_statements`
  discovers nested assignments. The compiler projection already preserves
  nested `ForLoop`/`IfBlock` order and typed expressions, but projected
  `Assignment` nodes currently do not retain their stable statement IDs.
- Preview and commit share `_prepare_transaction`; preview returns only a
  diff/summary today, not the candidate typed projection. Commit reruns full
  validation at the base revision. The Cycle 11 mission gateway is hard-coded
  to DOUBLE creation and an exact `X*3` expression and is not reusable for the
  lookup mission.
- `MirExecutionService` executes a committed revision through interpreter and
  JIT without rendering/reparsing. The Cycle 8 lookup fixture validates IDs
  101/205/900, missing IDs and the ID/index distinction; historical
  BASIC FUNCTION/IF output is known defective and will not be used as oracle.
- Cycle 11 rendering is self-contained and trace-driven, but normalized
  structure is DOUBLE-specific and its event schema contains no model turns.
- The existing OpenAI-compatible `ChatEndpoint` in `experiment/llm_runner.py`
  provides bounded requests, actual usage metadata and wire-byte timing. The
  local Ollama OpenAI endpoint responded to `/v1/models` and advertises
  `gemma4:latest`; no credential or endpoint URL is committed. The run will be
  bounded to one agent session.

## Reuse and campaign-specific gaps

Reuse: existing constructor, expression edit, symbol/statement discovery,
preview/commit, MIR execution, OpenAI-compatible client and HTML/SVG/Kitty
renderers. Cycle 11's event writer and metafile distinction are useful, but
its policy, IDs and normalizer cannot be generalized by changing only names.

Minimum changes: carry statement identity into projected assignment nodes; add
a read-only preview method returning a JSON-safe typed candidate projection;
normalize nested expressions/statements by declared handles; authorize only a
single assignment change after proving the PERSON_ID-to-slot map and exact
whole-projection delta; expose a small model tool gateway; and extend the
existing trace renderer to display nested structure and genuine tool events.
These are derived views and a campaign gateway, not a new editable model.

The policy is enforced only for calls routed through this gateway. It cannot
protect against direct Workspace, shell or filesystem access. The mission will
permit a finite age in a declared range (including 48), while the independent
task oracle requires 47. This separates authorization from mission success.

## Experiment and falsification

Construct AGE_BY_ID from typed operations, serialize the constructor and
portable handle declarations, then deserialize and replay them into an empty
Workspace. Bind all arrays/functions/parameters/statements from commit results.
The allowed slot must be derived by matching logical ID 205 in PERSON_ID, not
by treating 205 as an index. Preview a permitted alternative 48 without
committing it; let one real model session discover and update the age to 47.
Keep the model's chronological tool journal separate from the constructor
plus successful edit metafile. Run deterministic denied edits independently.

Falsifiers: replay references original IDs; nested binding differs; semantic
delta changes any node other than the age-205 literal; 48 fails authorization;
wrong entity, ID column or control-flow edits pass; stale revision commits;
rejections mutate state; 47 does not yield (25,47,53,-1,-1) in both MIR
engines; replay fails; or the viewer displays an uncommitted edit as current.

## Trust and assumptions

The agent tool process receives no raw Workspace or unrestricted tools. Host
code owns the Workspace, verifies mission invariants and independently runs
MIR after the model stops. The LLM sees its task and permitted tool schemas,
but no target statement UUID. Its rationale is recorded as a claim, never
interpreted as hidden reasoning. If the endpoint fails or times out, the trace
will record that exact outcome and no synthetic agent commit will be added.
