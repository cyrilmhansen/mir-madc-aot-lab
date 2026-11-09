# Reproduce Cycle 31 portable replay

From the repository root:

```sh
python experiments/basic-workspace/scripts/cycle31-portable-replay.py
python -m pytest -q experiments/basic-workspace/tests/test_cycle31_portable_replay.py
```

The script reads the authentic Cycle 30 stream and its saved evidence without
rewriting it. It replays prefixes for the historical checkpoints, performs a
fresh full replay, runs the host validation input corpus through MIR interpreter
and JIT, compares the observations to Cycle 30's saved host validation, and
writes derived reports under:

`experiments/basic-workspace/pi-integration/results/cycle31-portable-replay/`

The regression test exercises the shared Python replay without Pi. The full
Workspace suite also includes the Cycle 20B and Cycle 23 production TypeScript
handler/JSONL dispatch preflight, and the Cycle 19/25/29 replay consumers.
No model provider is contacted by these commands.
