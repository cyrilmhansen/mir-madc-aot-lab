# Cycle 18 architecture audit

## Verified starting point

- Repository HEAD at campaign start: `77321741548c07327ecce5fe2d723f6d96a0d0aa`; branch `experiment/mir-aot-correctness-cycle3`.
- The Cycle 17 operator summary said 153 tests while the committed Cycle 17 report said 152. Re-running `python3 -m unittest discover -s tests` before Cycle 18 tests were added reported 153; the Cycle 17 report is corrected to that observed count. The earlier one-test discrepancy's cause is not established. Cycle 18 adds six tests, for 159 total.
- The controlled Pi integration keeps the Python `Cycle16Gateway` and existing `SeniorMissionGateway` authoritative. Pi's TypeBox schema validates request shape; Python resolves handles, validates discovered signatures, applies mission policy, previews and atomically commits.
- Draft protocol state is temporary and revision-bound. Only `preview_function_draft` creates a gateway preview. Only `commit_preview` mutates the canonical Workspace. The incremental authoring history is separate from `constructive-operations.json`.
- The source display, live SSE viewer, semantic event journal and MIR validation already exist. Cycle 18 adapts the current mission name/allowed callee and draft batch size; it does not change the canonical token model or execution pipeline.

## Three comparison dimensions

| Dimension | Atomic arm | Incremental arm |
|---|---|---|
| Semantic representation | Nested typed expression and statement tree | Flat typed expression/statement graph with draft-local references |
| Model interaction granularity | Observed Pi tool calls; constructor proposal is one call | Observed Pi calls and operations per batch; one batch may contain many operations |
| Workspace commit granularity | One authorized atomic transaction | One authorized atomic transaction after the temporary draft is complete |

An operation batch is not an agent interaction. Draft revisions are internal accepted operation counts, not Workspace revisions. Both arms start from separate deterministic workspaces at revision 4.

## Schema audit and generality

The captured Pi 1.5.0 schema is generated at session start by the active extension and stored as `tool-schemas.json`. Atomic tool schemas total 19,792 bytes for five active tools; incremental schemas total 9,477 bytes for eight active tools. The whole-function constructor currently contains 10 `anyOf` nodes and 20 branch alternatives; the flat draft operation union has one `anyOf` node and seven branches. This is the measured current shape, not a claim about all future schema growth.

Function names, parameter names and function handles are syntactic strings, not schema enums. The same schema accepts a call referencing another portable handle. Python then requires that the handle resolve to a numeric function, be discovered, have compatible arity and be the single callee permitted by the current mission. Tests demonstrate acceptance of a generic handle by syntax, rejection by the AGE_CATEGORY mission when it points to IS_SENIOR, and acceptance by a separately configured narrow mission permitting IS_SENIOR. No TypeScript schema rewrite is needed to change the discovered call target.

The atomic nested grammar is deliberately bounded: current call arguments are atoms, conditions are one binary layer over call-or-atom values, and bodies support result assignments and IF blocks. Arbitrary recursive composition would require adding bounded schema branches or switching the atomic arm to referenced nodes. The incremental graph reuses existing handles and adds operation kinds as flat alternatives. Future growth in those alternatives is linear in operation kinds; this experiment does not extrapolate provider tokenization from JSON byte counts.

## Mission feasibility and controls

AGE_CATEGORY can be represented by existing syntax without adding language constructs: default result `-1`, then independent conditions for `AGE_BY_ID(ID) >= 0`, `>= 18`, and `>= 50`, assigning categories `0`, `1`, and `2`. The independent oracle covers unknown IDs and isolated ages 0, 17, 18, 49, 50, and 130 in both MIR engines. The category mission policy requires a semantic call to the discovered AGE_BY_ID handle and compares the complete candidate against the existing program baseline.

Before inference, deterministic tests checked both live captured schemas, generic handles, signature enforcement, atomicity, draft references, visualization, independent boundary execution and replay. The two final Pi RPC preflights confirmed the requested Sushi model is listed and exactly the intended five or eight tools are active. RPC preflight did not send an inference request.

## Limits

The local integration sees Pi JSON events, tool schema captures, provider usage metadata when Pi reports it, and Python gateway processing time. Pi does not expose complete serialized HTTP request bodies through this runner, so full request-context bytes will be reported as unavailable rather than inferred from event-stream bytes. One bounded A/B pair can show feasibility and interaction patterns, not statistical reliability or superiority.
