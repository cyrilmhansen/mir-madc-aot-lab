# Cycle 39 family compatibility

Classifications describe full production admission, not merely canonical replay. “Supported” requires a valid constructor, a Cycle37 rename, an exact Cycle20 edit target, finite-table host validation, authenticated handoffs and final shared replay. Unary-minus numeric nodes remain outside the direct literal editor.

| Family | Typed construction | Rename | Numeric target | Finite Cycle20 oracle | Verified handoff | Complete production workflow |
|---|---|---|---|---|---|---|
| Clamp | Supported | Supported | Supported for direct nonnegative cap/result literals | Supported | Supported | Supported |
| Threshold predicate `>=` | Supported | Supported | Supported for direct nonnegative RHS literal | Supported | Supported | Supported |
| Threshold predicate `<` | Supported | Supported | Supported for direct nonnegative RHS literal | Supported | Supported | Supported |
| Dependent predicate | Supported | Supported | Supported for direct nonnegative RHS literals | Supported | Supported | Supported |
| Sequential override | Supported | Supported | Supported for direct nonnegative IF RHS literals | Supported | Supported | Supported |
| Two callees | Supported | Supported | Supported for direct nonnegative IF RHS literals | Supported | Supported | Supported |
| Dependency chain | Supported | Supported | Supported for direct nonnegative IF RHS literals | Supported | Supported | Supported |

The two previously excluded oracle shapes (`<` predicates, sequential overrides, and two-callee semantics) are validated by host-generated finite expected tables. This changes only validation data, not Workspace grammar or mutation operations. Cycle41's production corpus includes primary/secondary runs for those families. The direct signed-literal representation limitation is not removed: editing a negative value represented as unary minus is unsupported even though negative inputs are valid and exercised.
