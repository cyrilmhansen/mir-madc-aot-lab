# Code-first semantic replay

## What changed

`visual-replay.html` is a standalone, offline code viewer driven by the new versioned `visual-frames.json`. The BASIC listing is the main viewport; line numbers, syntax color, revision badges and semantic highlights make each committed snapshot readable as an editor view. Playback offers play/pause, previous/next, a scrub bar, speed control and chapter selection. The JSON evidence inspector is collapsed by default.

Open `visual-replay.html` in a browser. The replay does not call the model, compile code, or use rendered BASIC as a replay input. Direct frame links are available with fragments such as `#p14-m2-preview` and `#p14-m3-check`.

## Cycle 14B presentation

The 18 frames show the initial `AGE_BY_ID`, real discovery and function-creation proposal/commit for `IS_SENIOR`, the age-205 discovery and preview, the revision-4 commit, validation, checkpoint and context reset, the first resumed-model rejection, deterministic reconstruction, and the successful resumed `IS_ADULT` proposal/commit/validation and final replay check.

Preview frames retain the last committed code and revision. A proposed function is shown in a separate preview block; the age edit is shown as an annotation beside the still-committed `42`. Only the later commit frame shows `55` in the program. The first rejected resumed proposal displays the unchanged revision-4 program. Reconstruction is explicitly labeled as deterministic host work, not model activity. Dependency edges are derived per visible committed source snapshot; proposed calls are labeled as previews and do not appear as committed edges.

## Cycle 13B presentation

The same viewer contains a separate chapter for the preserved real Cycle 13B `IS_SENIOR` composition run: original program, discovery, proposal, commit and MIR validation. The original model transcript and event journal were read but not modified.

## Evidence and highlight accuracy

The frame source is the committed canonical Workspace snapshots and actual saved model tool transcripts. Existing traces do not retain token-to-rendered-character spans for every historical discovery. Function highlights use the semantic function handle and the committed function block; the bound call is confirmed by the semantic operation evidence. The age cell highlight uses the portable `people.age.205` handle correlated with the unique changed line in the two canonical snapshots. That is an objective line-diff fallback, not a claim of stored token spans. No cursor position is inferred.

The longitudinal journal includes post-hoc replay records whose storage order is not the original model chronology. The presentation timeline therefore follows the preserved per-mission transcripts and canonical revision snapshots: seeded revision 2, Mission 1, Mission 2, the first failed Mission 3 session, deterministic reconstruction/checkpoint verification, and the successful fresh-context continuation. Model events, gateway decisions, host validation and reconstruction carry separate provenance labels. It does not animate imagined keystrokes. The successful Mission 3 committed snapshot was emitted by replaying the exact successful typed model operation into a fresh Workspace; its provenance says so. The historical mission transcript remains unchanged.

Some old journal rows do not encode precise wall-clock ordering across independent session files. The presentation communicates mission and checkpoint order, not fabricated millisecond timing. Recorded inference latency can be inspected in the collapsed diagnostics/evidence data.

## Browser captures

The PNGs below were captured from the actual local HTML using Firefox headless at 1600×1050. They are browser screenshots, not hand-drawn illustrations. Kitty was not used.

- `01-existing-program.png` — initial committed revision.
- `02-age-preview.png` — proposed age edit while `42` remains committed.
- `03-age-committed.png` — revision 4 with `55` committed.
- `04-adult-after-recovery.png` — committed `IS_ADULT` and host MIR validation after recovery.
- `../is-senior/real-model-02/cycle13-is-senior-committed.png` — Cycle 13B composition commit.

## Reproduction

From the repository root:

```sh
python3 experiments/basic-workspace/scripts/render-code-replay.py
python3 -m unittest experiments.basic-workspace.tests.test_code_replay -v
firefox --new-window file://$PWD/experiments/basic-workspace/results/semantic-replay/longitudinal-01/calibrated-resume-02/visual-replay.html
```

Use the timeline or the Previous/Next buttons to step through significant actions. The tested headless screenshot command used Firefox with a temporary isolated profile; no global browser or Kitty configuration was changed.

## Limits

This is a visual presentation derived from existing evidence, not a new event recorder. Historical token spans were not available, and the longitudinal evidence requires chronology reconciliation across mission transcripts and post-hoc replay records. Older frames therefore use semantic function identity and exact snapshot diffs where possible. The side panel is intentionally compact, but the code remains the dominant viewport. No new LLM call was made.
