# Cycle 34 metrics

## Production line counts

Count rule: physical source lines (`wc -l`), measured at baseline commit `d039476604e67e0003ac2ef9055c03c4530a1ede` and after implementation. Generated output, tests and the three Cycle34 evidence scripts are not production runtime.

| Production component | Before | After | Net |
|---|---:|---:|---:|
| Cycle20 gateway | 1,161 | 1,204 | +43 |
| Transaction kernel | 121 | 121 | 0 |
| Shared portable replay | 439 | 452 | +13 |
| TypeScript extension | 234 | 241 | +7 |
| **Production total** | **1,955** | **2,018** | **+63** |

The 103-line TypeScript dispatch probe is an existing deterministic test harness, not production runtime; it remains 103 lines (zero net change) and is excluded from the totals. Workspace core remains unchanged.

The gateway diff adds 65 and removes 22 lines. The former single-function authorization was moved into `_authorize_edit_batch`, used by both request versions; no second authorization pipeline exists. Portable replay adds a strict second envelope for the same edit operation and retains the old exact shape. It also verifies that a legacy envelope handle agrees with every legacy target. The transaction kernel and Workspace mutation layer are unchanged.

| Architecture count | Before | After |
|---|---:|---:|
| Independent edit authorization implementations for these modes | 1 (v1 only) | 1 shared batch implementation |
| Transaction kernels | 1 | 1 |
| Portable replay dispatchers | 1 | 1 |
| New Workspace mutation families | 0 | 0 |
| New transaction lifecycles | 0 | 0 |
| New replay families | 0 | 0 |
| New runtime gateway classes | 0 | 0 |
| New classes/abstractions | 0 classes; 1 extracted helper | 0 classes; 1 extracted helper |

## Mission and scaffolding cost

- Mission-specific runtime Python: **0 lines**. Both policies are host-owned JSON contract data.
- Two contract fixtures: 3 explicitly authorized target paths each; 2,074 bytes (primary) and 2,078 bytes (secondary).
- New regression test: 170 lines.
- Deterministic preflight, negative-control and timing tools: 333 lines total; these are evidence tooling, not runtime behavior.
- No changes to canonical Workspace operations or `SemanticTransactionKernel`.
- Both missions use one `edit_numeric_literals` constructive operation, each with three edits over two functions.

## Active TypeScript schema

The actual active Pi-extension registry capture contains exactly five tools. Compact UTF-8 JSON size of the complete serialized active tool schemas: **1,901 bytes**. The `workspace_preview_semantic_edit` v2 parameter schema alone is **1,311 bytes**. The schema requires `expected_revision`, literal `scope_mode: "per_target"`, and an edit array whose items have strict target/old/replacement shapes. It has no top-level function handle and rejects additional properties. Both primary and secondary captures are byte-equivalent in schema structure and size.

## Repeated timings

`performance.json` contains five local runs per mode and raw samples. Medians (min–max spread, ms):

| Phase | Legacy v1, 2 targets / 1 function | Cross-function v2, 3 targets / 2 functions |
|---|---:|---:|
| Baseline reconstruction/startup | 63.064 (60.471–68.869) | 71.065 (69.491–76.364) |
| Discovery | 0.066 (0.043–0.075) | 0.066 (0.044–0.090) |
| Authorization + preview | 64.568 (61.837–64.970) | 71.425 (70.772–72.105) |
| Commit + revalidation | 63.851 (62.290–67.479) | 71.380 (69.755–75.475) |
| Host oracle + full replay | 122.888 (118.827–127.227) | 135.033 (132.968–142.124) |

The v2 contract runs two additional corpus points and one extra edit, so these timings are not an isolated authorization-overhead comparison. Both modes complete the full deterministic lifecycle in well under a second on this local machine.

## Marginal cost

After Cycle34's shared boundary exists, Mission B required no production code: only its independent host contract and evidence fixture differ. Mission B has the same paths and invariants but different allowed replacement values and oracle outputs. This is the key reusable-authority result; it is not evidence of improved agent efficiency because no model was run.
