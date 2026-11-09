# Cycle 27 architecture audit

## Verified baseline

- Repository baseline: `2d1734f9be6ad545a09fa36efe64b3ebb0f74ece` on `experiment/mir-aot-correctness-cycle3`.
- Cycle 26's authentic constructive stream has eight committed operations and reconstructs an empty Workspace to revision 9.
- The renamed function is currently spelled `NORMALIZE_SCORE`, while its established portable handle remains `clamp_score.function`. The saved `IS_PASSING` and `SCORE_CLASS` calls bind to that same semantic function.
- The Cycle 26 host evidence records behavior and identity preservation. Its final rename journal entry lacks a semantic snapshot, so reconstruction accepts that one historical shape only when the last operation and commit record agree and the saved host validation attests the preserved identities and bindings.
- Fresh reconstruction produced 18 mapped identities and interpreter/JIT agreement before model inference.

## Reused responsibilities

- `cycle19_gateway.py` already owns typed function construction, discovered portable function handles, the bounded creation contract, source projection, MIR execution, and the Cycle 23 `SemanticTransactionKernel` lifecycle.
- `cycle20_gateway.py` already owns portable stream reconstruction, numeric maintenance, host behavior checks, and the same shared transaction kernel. Its replay adapter now understands the already-recorded structural insertion and rename operations needed to rebuild Cycle 26. It invokes existing Workspace mutations; it adds no transaction lifecycle.
- `extension.ts`, `cycle20b_dispatch_probe.ts`, and the JSONL gateway remain the production Pi-to-Python path. Semantic authorization stays in Python. The deterministic Cycle 27 preflight invokes the production TypeScript handlers and JSONL dispatcher.
- `scripts/basic-visual.py` and the generic frame compiler consume the resulting event/snapshot evidence; the mission adds no campaign storyboard renderer.

## Minimal gaps and changes

The creation gateway could accept a configurable contract, but its baseline loader had been written against the Cycle 21 stream and Cycle 24 revision-5 oracle. Cycle 27 needed three narrow adaptations: replay the already-supported structural-insertion and rename operations when bootstrapping; execute/compare functions using their current names instead of a hard-coded `CLAMP_SCORE`; and take expected baseline behavior from the supplied host-owned contract. No BASIC or MIR capability was added.

The generic runner also hard-coded revision 5 and a Cycle 24 mission label in derived metadata. The runner now records the configured contract revision and mission ID. The genuine run's original output is retained as `real-agent-01/summary.json`; `summary-corrected.json` documents the metadata-only correction.

## Historical presentation caveat

Cycle 25's preserved display snapshots contain indentation drift from its original insertion helper. Those historical files were not edited. The Cycle 26 committed operation stream and semantic evidence were used for the revision-9 baseline; BASIC text is only a display projection and was not used to reconstruct the Workspace.
