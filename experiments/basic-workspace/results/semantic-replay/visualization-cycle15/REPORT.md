# Cycle 15 — Generic code-first replay and live delivery

## Result

The existing code-first presentation has been separated into a reusable pipeline: recorded presentation events and committed display snapshots compile into versioned visual frames, which the same offline HTML renderer or a read-only loopback SSE viewer can consume. The generic compiler and viewer contain no Cycle 13/14 function names or campaign-specific storyboards. Historical format knowledge remains in the Cycle 13/14 adapter.

The Cycle 14B recording compiles to 18 significant frames. Offline and incremental compilation produce the same frames. A progressive delivery simulation reached the same revision-5 committed program in Firefox, with the same current-revision MIR observation. The demo replays recorded events; it is not another agent session.

## Architecture and evidence

See [ARCHITECTURE.md](ARCHITECTURE.md) for the audit, event contract, semantic-span accuracy, revision rules, provenance and live boundary. The machine-readable schemas and normalized bundles sit beside each campaign:

- [Cycle 14B normalized events](../longitudinal-01/calibrated-resume-02/visual-events.jsonl)
- [Cycle 14B display source and snapshots](../longitudinal-01/calibrated-resume-02/visual-source.json)
- [Cycle 14B generic frames](../longitudinal-01/calibrated-resume-02/visual-frames-generic.json)
- [Cycle 13B generic frames](../is-senior/real-model-02/visual-frames-generic.json)

The old Cycle 11–14 journals and `replay.html` artifacts were retained. The adapter reconstructs Cycle 14B's presentation sequence from the original mission transcripts, revision snapshots and checkpoint evidence; its deterministic fresh-workspace reconstruction is explicitly labeled separately from genuine model actions.

## Playback and browser validation

Open completed replay offline:

```sh
python3 experiments/basic-workspace/scripts/basic-visual.py replay \
  experiments/basic-workspace/results/semantic-replay/longitudinal-01/calibrated-resume-02
```

The command prints and updates `visual-replay-generic.html` in that campaign directory. To progressively deliver the preserved recording through the local viewer:

```sh
python3 experiments/basic-workspace/scripts/basic-visual.py demo \
  experiments/basic-workspace/results/semantic-replay/longitudinal-01/calibrated-resume-02 \
  --port 8765 --interval 0.65
```

Then open `http://127.0.0.1:8765/`. The viewer serves only GET endpoints, binds to loopback, and has no Workspace mutation route. For a future append-only producer, use `live` instead of `demo`; it begins following `visual-events.jsonl` after the loaded recording's current end.

Firefox 158.0.1 was driven headlessly against the actual generated HTML. Screenshots in this directory show the initial program, semantic selection, isolated preview, committed edit, checkpoint, resumed validation and final streamed state. The live screenshot shows action 18/18, revision 5, the committed `IS_ADULT` function and current-revision observations. Separately, `live` mode was exercised with a temporary campaign copy: an appended revision-5 observation arrived over SSE without changing the preserved campaign evidence.

The full suite passed **131 tests** in 2.988 seconds, including 10 new generic visualization tests. The generic replay CLI completed in 0.04 seconds on this run. The normalized Cycle 14B event file is 25,048 bytes, its 18-frame JSON is 91,388 bytes, and the standalone HTML is 69,047 bytes. The seven Firefox captures total 1,305,366 bytes. Timings are single local measurements, not a performance benchmark.

Validation commands:

```sh
python3 -m unittest discover -s experiments/basic-workspace/tests -v
python3 -m unittest experiments.basic-workspace.tests.test_visualization -v
python3 experiments/basic-workspace/scripts/basic-visual.py replay \
  experiments/basic-workspace/results/semantic-replay/longitudinal-01/calibrated-resume-02
```

The full suite was run while snapshotting and restoring `experiments/basic-workspace/results/`, because historical tests regenerate campaign outputs. No LLM request was made. Kitty, Pi integration, browser video and screenshot portability were not tested. No screenshot is fabricated: all seven PNGs came from Firefox rendering the actual HTML.

## Limitations

- Historical exact token spans are not present for every event. The adapter uses verified unique source-line changes or a verified function boundary and marks that mapping quality; it does not infer cursor positions.
- Some old tool results lack function arguments or cross-file wall-clock ordering. Missing metadata is shown as unavailable, and the Cycle 14B ordering follows verifiable transcript/revision evidence rather than invented timestamps.
- The live server is a local visualization prototype, not an authenticated remote service. The append-only file is the producer boundary; no Pi adapter is included.
- Live source changes require a commit event carrying a matching committed snapshot (or one available in the immutable snapshot map). Previews, denials and stale events cannot advance visible code.
- Browser capture exercised the recorded demo, while offline compilation and SSE equivalence are covered by deterministic tests and an appended-event smoke check. A separate interactive operator session was not run.
