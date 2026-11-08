# Cycle 14B — Longitudinal agent session

Status: **mission_3_or_replay_failed**

- Model: `Qwen3.8-Flash-Next-Sushi-STQ-2.75bpw`.
- Missions committed: 2/3.
- Context reset: completed; fresh model conversation used checkpoint only.
- Checkpoint: verified before resume.
- Full replay: not completed.

See `summary.json`, `history.jsonl`, per-mission `agent-session.json`, `recovery-checkpoint.json`,
`constructive-operations.json`, `equivalence.json`, `replay.html`, and `overview.svg`.
Provider endpoint values and credentials are excluded. Each mission has a new model
conversation; Mission 3 receives only current tools, its objective, and the verified
checkpoint. Seed creation is harness activity, never model activity.

## Reproduction

```sh
python3 experiments/basic-workspace/scripts/provider-preflight.py --probe-timeout 90
python3 experiments/basic-workspace/scripts/longitudinal-campaign.py --output-dir experiments/basic-workspace/results/semantic-replay/longitudinal-01/another-run
```
