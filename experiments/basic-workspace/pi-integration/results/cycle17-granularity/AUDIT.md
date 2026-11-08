# Cycle 17 architecture audit

## Verified starting point

- Repository started at `f240d9ae31682bf22a252ec7c26277081e872e02`, branch `experiment/mir-aot-correctness-cycle3`.
- Cycle 16B exposed five Pi tools. `workspace_preview_function` accepted a complete typed function request; MissionGateway previewed it as one candidate and the Workspace transaction committed it atomically.
- The atomic tool's active Pi 1.5.0 JSON Schema is captured in `preflight-atomic/tool-schemas.json` (20,343 bytes). Its mission-bounded body is a finite tree of `anyOf` branches; it is not a general recursive grammar.
- `Workspace.transaction()` and the existing MissionGateway already provide revision checks, validation, preview and atomic commit. Draft operations therefore need not edit canonical tokens or create a second compiler.
- The revision-4 seed is independently created for each arm: `AGE_BY_ID`, `IS_SENIOR`, numeric arrays and age 205 = 55. The model's first program mutation in either arm produces revision 5.

## Two authoring representations

**Atomic constructor.** One request carries the function signature and a nested typed expression/statement tree. It is straightforward to validate and commit once, but its JSON Schema repeats alternatives at each nested position. Cycle 16B deliberately bounded this to the supported mission. Extending it to deeper general expressions, nested IF and more statement kinds requires additional nested branch descriptions, and potentially multiplies schema size at each recursive level.

**Incremental draft.** `draft_protocol.py` keeps a mission-scoped graph of numeric expression nodes, statement nodes and blocks. Flat operation variants refer to short draft-local handles. Each ordered operation has an ID, advances a draft revision and is staged on a copy. A failed operation or batch publishes none of the partial changes. The complete draft lowers to the already-existing constructor request and passes the same MissionGateway preview, policy recheck and Workspace atomic commit. Workspace revision is checked separately from draft revision. A draft cannot commit against a changed Workspace base or mutate after commit.

The draft API is deliberately a temporary proposal builder, not a new authoritative model. Its operation history is kept in `draft-operation-history.json`; only the committed complete constructor transaction appears in the constructive stream. These histories answer different questions and are not interchangeable.

## Schema growth

The exact active Pi schemas, rather than hand-counted TypeBox definitions, were captured before either model session:

| Interface | Active Pi tools | Serialized schema bytes | Estimate at 4 bytes/token |
|---|---:|---:|---:|
| Atomic constructor | 5 | 20,343 | 5,086 |
| Incremental flat grammar before unary node | 8 | 8,709 | 2,177 |
| Incremental grammar with unary `+`/`-` node | 8 | 9,662 | 2,416 |

Adding the supported unary node expanded the incremental schema by 953 bytes (10.9%). The incremental schema used by arm B is 52.5% smaller than the active atomic schema. These are serialized-schema sizes and rough byte/4 estimates, not provider token measurements.

The flat operation union has seven expression/statement operation kinds in the measured arm-B schema. Its supported operation-kind branch count grows additively by one for each new flat operation variant; the fixed argument shapes also add bytes. By contrast, an illustrative fully expanded expression-tree schema with two atomic leaves, unary and function-call wrappers, and binary nodes has recurrence `N(d+1)=2+2N(d)+N(d)^2`: `N(0)=2`, `N(1)=10`, `N(2)=122`, `N(3)=15,262` alternative placements. This recurrence is a theoretical shape-count illustration, **not** a measured Pi schema byte count or a count of all possible operator-specific schemas. IF branch expansion adds another nesting dimension. The exact atomic growth for arbitrary recursion was not implemented or claimed.

## Limits and assurance boundary

The draft grammar is intentionally limited to finite numeric expressions and result-assignment/IF blocks needed by this task; it has a bounded batch of 16 operations and a 128-operation draft history. Handles are draft-local and never become Workspace identities. A draft operation can be independently identified and diagnosed, while the model may submit a bounded batch in one Pi tool call. The gateway owns mission authorization; flat schema acceptance is not authorization. Only the Python MissionGateway can preview or commit.

The incremental representation favors composition and intermediate inspection, while the atomic constructor remains the smaller number of semantic decisions for a simple function. Neither one-run A/B result establishes general reliability or model superiority.
