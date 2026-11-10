# Maintenance contract v3

V3 retains the exact v2 top-level authorization shape plus `scope_mode: per_target`. It replaces the validation object with the bounded finite table:

```json
{"mode":"finite_expected_results","inputs":[-1,0,1],
 "functions":[{"function_handle":"provider.function","result_key":"provider"}],
 "expected_results":[{"provider":0},{"provider":1},{"provider":2}]}
```

Rows correspond positionally to inputs. Inputs and handles/result keys are unique. Each row must have exactly one finite numeric result for every declared result key. At most 64 inputs, 8 functions, and 512 cells are accepted. Boolean values, NaN, infinities, extra fields, omitted rows/columns, duplicates, and unknown handles fail closed. V1 and v2 contract shapes and their existing formula-oracle checks remain unchanged.

The table supplies validation expectations only; it grants no edit scope. Existing host-owned `authorized_targets`, exact old values, replacement sets, revision, candidate structure, identity and dependency invariants remain authoritative.
