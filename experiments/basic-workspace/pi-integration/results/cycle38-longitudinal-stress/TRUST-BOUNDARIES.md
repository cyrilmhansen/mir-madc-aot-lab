# Trust boundaries

| Boundary | Input | Verification | Authority granted |
|---|---|---|---|
| Cycle19 construction | Typed constructor proposals | Host-owned creation-sequence contract; exact signature/dependency checks; preview/commit; independent oracle and checkpoint per revision | One configured creation step at a time |
| Cycle36 creation proof | Constructor stream and checkpoint artifacts | Creation-only schema, operation/revision checks, replay, fingerprints and host receipts under external anchor | Authenticated constructed baseline, no later edits |
| Cycle37 rename | Verified creation proof plus typed rename proposal | Host-owned rename v2 contract, stable portable target, canonical `rename_symbol`, preview/commit revalidation, identity/binding/behavior checks | One named rename |
| Cycle38 continuation | Creation proof + rename evidence + destination maintenance contract | Separate host builder/anchor and independent receiving verification; strict one-rename history shape; replay and MIR oracle | No mutation right; establishes only the verified baseline |
| Cycle20 maintenance | Reconstructed revision and v2 per-target contract | Exact target/value set, discovered identities, candidate comparison, unchanged functions/dependencies/tokens, kernel revalidation, independent oracle | One atomic three-literal batch |
| Cycle31 replay | Committed portable operations | Explicit bounded dispatcher through canonical Workspace operations | Reconstruction only; no mission authorization |
| TypeScript/JSONL | Tool args and correlation metadata | Existing schema and transport adapter; Python gateway remains authoritative | No independent authority; transport metadata is not semantic payload |

Schema validity, artifact integrity, provenance, semantic equivalence, functional correctness and authorization are separate checks. Continuation success is not maintenance authorization. Operation histories replay sequentially; a complete multi-stage workflow has no global rollback guarantee.
