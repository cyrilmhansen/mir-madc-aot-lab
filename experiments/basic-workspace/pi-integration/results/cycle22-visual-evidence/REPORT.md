# Cycle 22 — Faithful visual evidence for semantic maintenance

## Result

The shared code-first viewer now renders semantic numeric-edit diffs, committed line changes, and revision-bound MIR observations for both historical edit shapes. No inference was run. The real Cycle 20B/Cycle 21 Pi transcripts and gateway journals were preserved.

Cycle 21 shows the proposed `IF (CLAMP_SCORE(X) >= 60)` → `IF (CLAMP_SCORE(X) >= 40)` replacement in a dedicated preview dock while the BASIC listing remains revision 4. On the commit frame the listing advances once to revision 5 and only the verified changed line is highlighted. Cycle 20B uses the same logic to show both original `100` literals replaced by `50`, with the preview still at revision 3 and the committed listing at revision 4.

Validation frames show actual interpreter and JIT values alongside the independent expected result. Cycle 21's selected rows are 39→0, 40→1, 50→1 and 60→1 for `IS_PASSING`; the panel labels execution revision 5, host-oracle provenance and interpreter/JIT agreement. The full input/output maps remain in the embedded frame evidence. The C20B table uses its two recorded validations and the selected cap boundary inputs.

## Provenance

Derived session identities are now formed from campaign metadata and output directory (`cycle21.is-passing-threshold40.v1/real-agent-01` and `cycle20b-real-agent-02/real-agent-02`). The inherited raw session strings are not copied into normalized frame identifiers. Raw source journals remain untouched. Mission IDs, event IDs, event provenance and host/Pi validation labels are retained.

No exact character spans are claimed because those were not recorded. Commit line highlights are marked as a verified line-diff fallback, gated by the transaction's atomic edit count and accompanied by semantic target handles and token IDs.

## Artifacts

- Cycle 21 HTML: [`cycle21/visual-replay-generic.html`](cycle21/visual-replay-generic.html)
- Cycle 21 frames: [`cycle21/visual-frames-generic.json`](cycle21/visual-frames-generic.json)
- Cycle 20B HTML: [`cycle20b/visual-replay-generic.html`](cycle20b/visual-replay-generic.html)
- Cycle 20B frames: [`cycle20b/visual-frames-generic.json`](cycle20b/visual-frames-generic.json)
- Evidence-to-view audit: [`AUDIT.md`](AUDIT.md)
- Frame and screenshot measurements: [`metrics.json`](metrics.json)
- Browser captures: [`screenshots/`](screenshots/)

Firefox 158.0.1 headless captured the actual HTML at 1440×1000 for baseline, accepted preview, commit and host validation, plus an 800×900 preview. The preview dock is visible at both widths; it remains separate from committed code. Screenshots are real browser captures, not mockups. Individual byte sizes and dimensions are recorded in [`metrics.json`](metrics.json).

## Reproduction

From the repository root:

```sh
python3 experiments/basic-workspace/scripts/basic-visual.py replay \
  experiments/basic-workspace/pi-integration/results/cycle20b-semantic-edit-recovery/real-agent-02 \
  --output-dir experiments/basic-workspace/pi-integration/results/cycle22-visual-evidence/cycle20b \
  --evidence-view experiments/basic-workspace/pi-integration/results/cycle22-visual-evidence/cycle20b-real-agent-02-evidence-view.json
python3 experiments/basic-workspace/scripts/basic-visual.py replay \
  experiments/basic-workspace/pi-integration/results/cycle21-reusable-maintenance/real-agent-01 \
  --output-dir experiments/basic-workspace/pi-integration/results/cycle22-visual-evidence/cycle21 \
  --evidence-view experiments/basic-workspace/pi-integration/results/cycle22-visual-evidence/cycle21-real-agent-01-evidence-view.json
python3 -m unittest experiments.basic-workspace.tests.test_cycle22_visual_evidence -v
python3 -m unittest discover -s experiments/basic-workspace/tests -v
```

The screenshot command used the installed browser against the standalone file, selecting a frame with its URL fragment:

```sh
firefox --headless --no-remote --profile <isolated-profile-dir> \\
  --window-size 1440,1000 --screenshot \\
  file:///absolute/path/to/visual-replay-generic.html#maintenance-4-a28b6087
```

Open either standalone HTML file locally. It has inline CSS/JavaScript and does not need the gateway, an HTTP server, external assets or network access. A validation view can be opened through its recorded frame URL fragment, e.g. `#maintenance-7-22aaedf3`.

## Validation and limits

The six new visual evidence tests cover both edit shapes, preview/source separation, single revision advance, exact expected number of highlighted lines, host/interpreter/JIT values bound to the executed revision, campaign session IDs, rejection behavior, and standalone offline output. The complete Workspace suite passed **203 tests**. The existing visualization regression suite also verifies saved historical frame equivalence, rejection behavior and read-only local viewing.

The display selector lists a small set of useful boundary inputs; it does not replace the complete oracle result files. Highlighting is line-accurate, not character-accurate. No raw evidence or Workspace mutation logic was changed. See `AUDIT.md` for data provenance and field mapping.
