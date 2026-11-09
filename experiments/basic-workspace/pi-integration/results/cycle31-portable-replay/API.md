# Portable replay API

Public entry point:

```python
replay = replay_constructive_stream(
    workspace, document_id, operations,
    expected_start_revision=1,
    expected_final_handles=stream["portable_handles"],
    expected_retired_handles=stream.get("retired_handles", []),
)
```

The caller owns the Workspace. The result does not expose the Workspace or its
mutable documents. It contains the final revision, portable-to-local identity
maps, retired handle metadata, identity lifecycle events, and per-operation
revision receipts. The caller may inspect its own Workspace or derive a
semantic projection after replay.

Supported operations are explicitly dispatched:

* `create_numeric_function`
* `edit_numeric_literals`
* `insert_typed_if_block`
* `rename_symbol`
* `edit_typed_if_condition`
* `replace_typed_if_block`

Typed calls resolve portable function handles against the current live map;
function signatures are checked before canonical construction. Local
references resolve against the target function's parameter IDs. Constructor
handles use the existing `.function`, `.parameter.id`, and
`.statement.<ordinal>` convention. Historical handle spelling is stable across
source rename; for example, `clamp_score.function` resolves to the source
function currently named `NORMALIZE_SCORE`.

Block replacement checks the portable expected block and fingerprint, resolves
the exact child statement IDs listed for retirement, applies Workspace's
`replace_typed_if_block`, removes those handles from live resolution, and adds
the distinct replacement handle. A previously seen handle cannot be reused.

The dispatcher contains no dynamic execution, source parsing, mission policy,
provider logic, or callbacks supplied by stream data. Unknown fields/shapes and
unknown operation kinds fail explicitly. Every mutation goes through
revision-checked Workspace APIs.
