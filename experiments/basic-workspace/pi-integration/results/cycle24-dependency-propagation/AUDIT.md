# Cycle 24 architecture audit

## Verified starting architecture

- The genuine Cycle 21 constructive stream contains two numeric function constructors and two typed numeric-literal edit operations. Cycle20Gateway replays those four operations into a new empty Workspace and verifies revision 5 against the recorded committed semantic snapshot and passing replay evidence.
- The fresh revision-5 Workspace contains `CLAMP_SCORE(X)` and `IS_PASSING(X)`, with the semantic edge `IS_PASSING → CLAMP_SCORE`. The replay maps 11 portable identities to new Workspace identities.
- Function creation is represented by the existing typed `create_numeric_function` operation. The Pi tool schema already supports numeric assignments, comparisons, IF statements and bound function-call expressions. No BASIC grammar or TypeScript schema extension was needed.
- Numeric-literal maintenance is already expressed by `edit_numeric_literals`; its MissionContract resolves function handles and verified expression paths, checks expected old values, computes candidate behavior and uses the same `SemanticTransactionKernel` preview/commit lifecycle.
- ProgramDefinition remains the canonical Workspace state. The MIR interpreter/JIT validate projections of that state; rendered BASIC is only a view.

## Cycle 24 extension

The Cycle 19 creation gateway previously represented the dependency as a single `callee` field. That assumption was the only creation-policy blocker. The creation contract now carries a finite `required_callees` list and explicit expected dependency edges. The gateway verifies each target was discovered, exists in the current Workspace, has a numeric return and compatible arity, and is the only set of callees used by the new function. It also compares the complete existing function structures against the captured baseline before preview and again through the kernel's commit revalidation.

Dependency edges are graph relations, not counts of source call sites. Repeated calls to the same permitted function therefore produce one dependency edge. A genuine first proposal called `CLAMP_SCORE` twice and was denied by the earlier occurrence-count comparison; the model corrected its proposal during the same session. The edge comparison was then corrected to set semantics and a deterministic regression now accepts repeated authorized call sites while still rejecting any extra or missing dependency.

Cycle20Gateway gained one bounded host-oracle kind, `score_class_call`, which composes already-supported clamp and threshold oracles. Mission policy remains configuration data; the oracle kind is an explicit finite validation operation, not an executable predicate or a general policy language.

## Transaction and trust boundaries

```text
Pi typed tools
  → existing TypeBox handlers
  → existing loopback JSONL bridge
  → Cycle 19 creation / Cycle 20 maintenance policy adapters
  → SemanticTransactionKernel.preview / commit
  → authoritative Workspace transaction
  → MIR interpreter and JIT host validation
```

There is no new transaction engine or lifecycle implementation. Creation and maintenance still have separate semantic authorization rules, but both preview candidates and commit through the same kernel. The deterministic preflight exercises the real TypeScript tool handlers and JSONL bridge for both operation families.

The gateway restricts only calls made through this controlled interface. It is not an operating-system sandbox.
