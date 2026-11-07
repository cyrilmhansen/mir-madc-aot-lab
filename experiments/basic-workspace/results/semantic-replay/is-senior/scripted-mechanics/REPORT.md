# IS_SENIOR semantic composition campaign

Campaign kind: **scripted**. Final status: **passed**.

The semantic program is built from typed Workspace operations. `IS_SENIOR(ID)` must call the discovered `AGE_BY_ID` function; it is authorized only when the complete candidate projection preserves the original function and adds one supported numeric caller. Authorization is separate from the threshold/result oracle.

## Results

- Model status: `not_run` (real model disabled; scripted mechanics only); turns/tool calls: unknown/unknown.
- Workspace regression suite: 105 tests passed (`cd experiments/basic-workspace && python3 -m unittest discover -s tests -v`).
- Mission validation: True; interpreter/JIT agreement: True.
- Scripted negative controls: 11 attempted, passed=True (not model actions).
- Replay: True; portable identities remapped: 19.
- Boundary oracle at ages 49 and 50: True.
- Timings (ms): base construction 4.235, validation 62.653, replay/equivalence 59.425, scripted controls 32.232, visualization 2.645.
- Artifacts (bytes): constructive stream 6545, history 63304, HTML 79460, SVG 10332.
- Kitty: kitty 0.49.2 created by Kovid Goyal; remote control=False; no screenshot captured.

See `history.jsonl` for observed events, `agent-session.json` for the actual provider transcript when run, and `equivalence.json` for structural/binding/behavior checks. Rejected attempts remain in the journal; only committed typed operations appear in `constructive-operations.json`.



## Reproduction

```sh
python3 experiments/basic-workspace/scripts/is-senior-campaign.py --no-model --output-dir experiments/basic-workspace/results/semantic-replay/is-senior/scripted-mechanics
python3 experiments/basic-workspace/scripts/render-semantic-replay.py --trace experiments/basic-workspace/results/semantic-replay/is-senior/scripted-mechanics/history.jsonl --output-dir experiments/basic-workspace/results/semantic-replay/is-senior/scripted-mechanics
python3 experiments/basic-workspace/scripts/kitty-replay.py experiments/basic-workspace/results/semantic-replay/is-senior/scripted-mechanics/history.jsonl --auto 0.4
```

For one real bounded pilot, configure `BASIC_WS_CHAT_COMPLETIONS_URL` and `BASIC_WS_MODEL` in the environment, then run the campaign without `--no-model`. The report excludes endpoint URLs and credentials.
