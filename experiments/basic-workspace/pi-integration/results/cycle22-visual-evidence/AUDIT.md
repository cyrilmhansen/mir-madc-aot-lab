# Cycle 22 evidence-to-view audit

## Inputs and trust boundaries

This replay is compiled from the preserved Cycle 20B and Cycle 21 `visual-events.jsonl`, each campaign's `visual-source.json` revision snapshots, and the corresponding host `validation.json`. The raw Pi sessions, gateway histories, validation records, and pre-existing HTML/frame artifacts are inputs only and were not rewritten. The HTML is a read-only display projection; BASIC source is never fed back to Workspace or MIR.

| Source evidence | Recorded content | Visible presentation |
|---|---|---|
| Pi discovery / selection events | Mission/tool references, selected portable handles, actor provenance | Action description, semantic handle chips, provenance |
| MissionGateway accepted preview | Base revision, authorization outcome, unified diff, typed target paths, edit count | Old/new diff dock; committed listing and revision remain at the base revision |
| Workspace commit event and revision snapshot | New revision, authoritative rendered snapshot, semantic paths, changed token IDs | Listing advances only on commit; changed source lines are highlighted |
| Per-engine validation events | Interpreter and JIT result maps, executed revision, Pi-tool or host provenance | Comparison table, selected inputs, and execution revision |
| Host `validation.json` | Independent expected results, expectation source, aggregate pass and engine agreement | Expected column and host-oracle status, joined only when execution revision matches |
| Constructive/replay records | Portable operations, remappings, structural/binding/behavioral equivalence | Replay evidence remains available in event details and source campaign artifacts |

## What the baseline viewer lost

The Cycle 20B/Cycle 21 gateway events recorded numeric proposals under `preview.diff` and actual runtime values under plural `observations`. The generic frame compiler copied the preview object but the HTML only rendered `append_lines`, which is used for function creation. It also consumed singular `observation`, so the MIR panel had no interpreter/JIT results. The existing host validation files contained expected values, but the frame compiler did not join them to the observations by executed revision.

The original visual events also used inherited session strings (`cycle20-real-agent-02` for the C20B campaign and `cycle20-real-agent-01` for C21). The campaign metadata and output directory identify the actual sessions. New normalized frames use `<campaign id>/<output directory>` for display identity; original event journals remain unchanged. The source campaign mission IDs and genuine event/tool references are preserved.

## Semantic-to-source accuracy

Neither campaign records character columns for numeric literal tokens. The commit events do retain the semantic function/control/expression paths and changed token IDs. The renderer therefore uses the authoritative before/after committed snapshots and a deterministic line diff, and marks it `verified_unique_line_difference` only when the number of changed new-source lines equals the transaction's recorded atomic edit count. C20B resolves to its two authorized changed lines; C21 resolves to the single comparison line. This is a line-level fallback, not an exact token-span claim. If the count does not agree, the renderer leaves the exact line unhighlighted instead of guessing. The frame also retains semantic handles and changed token IDs for audit.

## Preview and commit semantics

The preview panel renders only the unified diff supplied by the accepted MissionGateway preview. It is visually separate from the code listing. The compiler holds the committed revision and source unchanged until it receives a commit with an authoritative snapshot. Rejected proposals render in a denial panel and likewise cannot advance code. Cycle 21 stays at revision 4 in preview and advances to revision 5 at commit. Cycle 20B stays at revision 3 in preview and advances to revision 4 at commit.

## Runtime observation joins

The selected rows are a presentation convenience, not new execution. Cycle 21 displays inputs 39, 40, 50 and 60 for `is_passing`; Cycle 20B displays 49, 50, 51 and 60 for `clamp_score` and `is_passing`. Actual Interpreter/JIT results come from each event's recorded `observations`; expected values and the host-oracle verdict come from `validation.json`. A join is made only if the file's `executed_revision` equals the event's executed revision. Other results remain embedded in the frame data for diagnostics.
