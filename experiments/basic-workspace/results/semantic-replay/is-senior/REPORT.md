# IS_SENIOR semantic composition campaign

Campaign kind: **real_llm_unrun**. Final status: **pending_model**.

The semantic program is built from typed Workspace operations. `IS_SENIOR(ID)` must call the discovered `AGE_BY_ID` function; it is authorized only when the complete candidate projection preserves the original function and adds one supported numeric caller. Authorization is separate from the threshold/result oracle.

## Results

- Model status: `not_run` (BASIC_WS_CHAT_COMPLETIONS_URL or BASIC_WS_MODEL is not configured); turns/tool calls: unknown/unknown.
- Workspace regression suite: 105 tests passed (`cd experiments/basic-workspace && python3 -m unittest discover -s tests -v`).
- Mission validation: False; interpreter/JIT agreement: not run.
- Scripted negative controls: 11 attempted, passed=True (not model actions).
- Replay: not run; portable identities remapped: not run.
- Boundary oracle at ages 49 and 50: not run.
- Timings (ms): base construction 4.274, validation None, replay/equivalence None, scripted controls 29.773, visualization 1.958.
- Artifacts (bytes): constructive stream 0, history 37465, HTML 53606, SVG 7180.
- Kitty: kitty 0.49.2 created by Kovid Goyal; remote control=False; no screenshot captured.

See `history.jsonl` for observed events, `agent-session.json` for the actual provider transcript when run, and `equivalence.json` for structural/binding/behavior checks. Rejected attempts remain in the journal; only committed typed operations appear in `constructive-operations.json`.

A completed scripted reference campaign is retained under `scripted-mechanics/`; it validates the gateway, MIR behavior and portable replay but is not model activity.

## Reproduction

```sh
python3 experiments/basic-workspace/scripts/is-senior-campaign.py --no-model --output-dir experiments/basic-workspace/results/semantic-replay/is-senior/scripted-mechanics
python3 experiments/basic-workspace/scripts/render-semantic-replay.py --trace experiments/basic-workspace/results/semantic-replay/is-senior/scripted-mechanics/history.jsonl --output-dir experiments/basic-workspace/results/semantic-replay/is-senior/scripted-mechanics
python3 experiments/basic-workspace/scripts/kitty-replay.py experiments/basic-workspace/results/semantic-replay/is-senior/scripted-mechanics/history.jsonl --auto 0.4
```

For one real bounded pilot, configure `BASIC_WS_CHAT_COMPLETIONS_URL` and `BASIC_WS_MODEL` in the environment, then run the campaign without `--no-model`. The report excludes endpoint URLs and credentials.
