# Cycle39 template compatibility with complete Cycle40 path

| Cycle39 family | Typed construction | Rename | Numeric target | Cycle20 oracle | Handoff | Complete production path | Reason |
|---|---|---|---|---|---|---|---|
| clamp | Supported | Supported | Supported when direct nonnegative cap literal | Supported (`clamp`) | Supported | Partial | No dependent threshold target to form required cross-function batch; not selected alone. |
| threshold_ge | Supported | Supported | Supported for direct nonnegative RHS | Unsupported as generated | Supported | Unsupported | Cycle20 has no raw-input threshold oracle. |
| threshold_lt | Supported | Supported | Supported for direct nonnegative RHS | Unsupported | Supported | Unsupported | No `<` raw-input oracle. |
| dependent_predicate | Supported | Supported | Supported for direct nonnegative RHS | Supported (`threshold_call`) | Supported | Supported shape | It has only one function target; Cycle40's principal generated batch also changes a clamp. |
| sequential_override | Supported | Supported | Limited; unary negative paths are not numeric targets | Unsupported | Supported | Unsupported | Cycle20 does not model ordered override semantics. |
| two_callees | Supported | Supported | Supported individually | Unsupported | Supported | Unsupported | Existing maintenance oracle supports one callee per threshold-call declaration, not two-callee sequential composition. |
| dependency_chain | Supported | Supported | Supported for direct nonnegative RHS | Supported recursively as threshold-call oracles | Supported | Supported shape | Can be composed with provider clamp and a three-target batch. |

The production campaign generates compatible clamp-plus-threshold graph variants. Four Cycle39 families (raw `threshold_ge`, raw `threshold_lt`, `sequential_override`, `two_callees`) are unsupported for complete Cycle20 production workflows; standalone `clamp` is only partially suitable. Those families remain outside the complete workflow denominator; they are not counted as passes or silently converted.
