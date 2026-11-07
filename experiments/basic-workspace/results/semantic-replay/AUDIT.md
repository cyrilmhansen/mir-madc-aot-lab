# Cycle 11 initial audit

Audit point: `0d3f89b12a2eac2f82752a7016de0dabfe92d183`, branch
`experiment/mir-aot-correctness-cycle3`. At audit time, the only pre-existing
working-tree changes are MPDecimal logs at the repository root. The Workspace
suite was rerun with `python3 -m unittest discover -s tests -p 'test_*.py'`:
**85 tests passed**. No source or persistent-worker implementation change is
needed for this experiment.

## Verified facts

- `Workspace` owns canonical token streams and derives symbol, statement,
  scope, and reference indexes. `create_empty_document` starts a revisioned
  document. Opaque IDs are UUID-derived and therefore are not portable across
  fresh workspaces.
- Existing structured operations include numeric/string function creation,
  shared numeric array declarations, expression/assignment edits, rename,
  line renumber, and function move. Typed expressions include numeric
  constants, references, arithmetic/comparison, calls, and indexed arrays.
- `preview_transaction` calls the same candidate-building validator as
  `apply_transaction`; commit rechecks the base revision and publishes only
  after validation. Failed transactions leave the authoritative document
  untouched. The API itself does not enforce a mission policy.
- Numeric projection is immutable and revision-bound. Fresh MIR execution
  supports interpreter and JIT. Persistent execution uses one worker per
  instance, module state local to that worker, numeric state only, one compile
  per worker, and no state migration. The worker lifecycle and BWM1–BWM5
  compatibility are already implemented.
- There is no existing general operation journal or visualization renderer.
  Existing demo scripts show direct structured calls, but are not replayable
  records and some retain ephemeral symbol IDs.
- Kitty 0.49.2 is installed on this host. Availability of a usable remote
  control socket, visible window, shader support, and screenshot capture is
  not established by the binary's presence alone.

## Assumptions and proposals, not baseline guarantees

- A portable constructive stream can be a small versioned list of existing
  typed operations with transaction-local aliases. During replay, creation
  results bind aliases to fresh Workspace identities; later references resolve
  through that map. The stream will be verified by reindexing and execution,
  not by reimporting rendered BASIC.
- A narrow controlled gateway can enforce one mission contract if all edits
  for that campaign pass through it. Direct access to `Workspace` or source
  editing bypasses the boundary; this is not a global authorization system.
- A JSONL event trace can be emitted by the harness around real API calls,
  recording scripted actions as scripted. An independent HTML/SVG renderer
  can derive all displayed state from event snapshots and results.

## Current gaps and minimum experiment

Missing pieces are a named machine-readable execution profile, a versioned
mission schema and allowlist, operation envelopes, portable identity aliases,
an observed event journal, deterministic replay, and a trace-driven human
viewer. The smallest test is a DOUBLE function: construct it from an empty
workspace, execute 9→18 in interpreter/JIT, preview and commit a permitted
result-expression change (multiplier 2→3), verify 9→27, reject a forbidden
rename before mutation, replay the portable stream into a fresh workspace,
and compare structure, binding aliases and behavior. If the existing model
cannot express this without changing its canonical token authority or
transaction boundary, stop rather than refactor it.

Falsification checks: replay must succeed with newly generated IDs; aliases
must resolve uniquely; forbidden edits must leave revision and rendering
unchanged; committed snapshots in the viewer must match observed revisions;
replayed interpreter/JIT outputs must agree; the compiler path must not render
or reparse source. Structural and behavioral equivalence are reported
separately.
