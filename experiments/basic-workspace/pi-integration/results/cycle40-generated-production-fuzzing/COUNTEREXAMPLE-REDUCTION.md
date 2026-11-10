# Counterexample reduction status

No product discrepancy was discovered, so no genuine semantic or authorization counterexample was available to minimize. The two failed first attempts were harness call-shape errors before a full workflow and were corrected; they are preserved in attempts 01 and 02.

The reducer was validated against an injected stale-revision failure at the actual Cycle19 TypeScript-to-JSONL boundary. It reduced a generated clamp-constructor negative to a one-function, one-assignment host contract and one stale revision field, and retained the `STALE_REVISION` classification with unchanged state. The reduced run and receipt are in `reducer-attempt-01/`. This does not represent a discovered product defect or prove minimization for other failure classes.
