# Cycle 15 visualization architecture audit

## Verified current state

- The authoritative program is still the Workspace token model. The compiler/viewer consumes display snapshots; it never reparses rendered BASIC.
- Workspace campaign histories contain mission-gateway lifecycle events. `transaction_committed` rows in the Cycle 13B/14B traces include committed `program_snapshot` strings and revision numbers.
- Genuine model tool calls and their arguments/results are retained separately in per-mission `agent-session.json` transcripts. Host validations and replay/equivalence records are in summaries and journals.
- Semantic symbols/statements have stable live-workspace IDs. Portable operation handles survive reconstruction; old journals do not consistently attach those handles to exact rendered token spans.
- The previous renderer already used verified function bounds and unique source diffs. Exact token-to-rendered spans are not generally recorded in the historical captures.
- Cycle 14B history includes post-hoc replay records. Presentation order therefore comes from the original mission transcripts, revision snapshots and explicit checkpoint boundary, not from sorting the aggregate journal alone.

## Minimal reusable pipeline

```text
Workspace / MissionGateway / host validation
        │ observed domain event + committed display snapshot when required
        ▼
Historical adapter (Cycle 11–14 only) or future producer (Python/Pi)
        │ versioned presentation-event JSONL
        ▼
VisualFrameCompiler (revision checks, deduplication, preview isolation, sticky observations)
        ├── visual-frames-generic.json → offline HTML
        └── progressive frames → loopback SSE → same HTML
```

The normalized event contract is `basic-workspace.presentation-event` version 1. It separates an event's source reference, provenance, revision, semantic focus, preview/outcome and observation from the generated `basic-workspace.visual-frames` version 2. A commit advances the displayed code only when the compiler has a matching revision snapshot. A producer may provide the Workspace-rendered commit snapshot in the event; the compiler checks it against any cached revision snapshot.

Historical adapters are allowed to understand old campaign formats. They do not rewrite old journals. The generic compiler and browser contain no Cycle 13/14 function names or storyboards. It consumes normalized events and per-frame dependency edges supplied by the adapter/program data.

## Source mapping

The normalized focus object carries opaque semantic handles, a mapping quality, and spans. Future producers can supply exact 1-based line / 0-based UTF-16-column ranges (end exclusive) for functions, parameters, declarations, statements, calls, assignment targets and expressions. The viewer renders these spans without using them for execution. Mapping labels are `exact_semantic_span`, `verified_unique_line_difference`, `verified_function_boundary` or `unknown`.

Cycle 13/14 captures use the last three methods: function identity is obtained from semantic/replay handles and validated operation evidence; the age assignment uses a unique line difference between authoritative revisions; no cursor positions or typing animation are inferred. Where no verifiable range exists, the adapter leaves the focus unknown or highlights the verified containing function.

## Runtime observations

The compiler keeps the latest actual observation with the revision it executed. A later commit makes it historical until a new validation arrives for the current revision. The UI says `Current revision`, `Historical result · revision rN`, or `Execution revision unknown`. Legacy captures did not retain per-call arguments uniformly; the adapter labels those as unrecorded and uses fixture IDs only when they are keys in the recorded engine results.

## Live event protocol and boundary

An observer appends one normalized presentation event per JSONL line to `visual-events.jsonl`. Commit events include a revision and, when the source bundle lacks it, the display snapshot captured from the authoritative Workspace. Observations include the executed revision, function, arguments and engine results when available. Preview, rejection, validation and context-reset events never change the compiler's committed source.

The viewer server binds only to `127.0.0.1`. It serves HTML, a health check and an SSE feed; only GET is implemented. It has no Workspace or mission mutation route. SSE uses monotonically increasing IDs, `Last-Event-ID` replay, duplicate-frame suppression and explicit gap/interruption events. If the bounded replay window is exceeded, it reports a gap and requires a fresh snapshot.

A future Pi extension should adapt its real tool events into this JSONL contract after receiving results from the Python MissionGateway. Pi remains a producer; it does not decide revisions or authorization. Model transport and viewer SSE remain independent. The loopback/file observer is an experiment boundary, not an OS security boundary.

## Historical ordering limits

Cycle 14B's successful resumed Mission 3 snapshot was produced by replaying the exact successful typed model operation into a fresh Workspace. It is identified as such in provenance. The first resumed attempt is a genuine rejected proposal and remains at revision 4. Some old journals lack comparable wall-clock timestamps across files; the adapter displays verified mission/checkpoint sequence and does not invent timing between those records.
