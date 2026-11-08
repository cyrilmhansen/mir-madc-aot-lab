# Cycle 14B — Corrected longitudinal resume

Status: **passed**

The original calibrated run completed Mission 1 and Mission 2 with genuine model sessions, then its Mission 3 gateway rejected a valid proposal because its comparison snapshot was stale. That failure and transcript remain unchanged in `calibrated-run-01/`.

For this corrected continuation, the successful Mission 1 and Mission 2 semantic operations were replayed into a fresh Workspace. Its revision-4 semantic fingerprint matched the preserved recovery checkpoint. A new model conversation received the checkpoint and current tools without prior conversational turns. The gateway comparison baseline was rebuilt after Mission 2's age update. The model created and committed `IS_ADULT` at revision 5.

- Genuine Mission 3: 5 turns, 5 tool calls, 19445 prompt tokens, 1660 completion tokens, 17631 provider-reported cached prompt tokens, 38220.308 ms.
- Host validation: True.
- Boundary tests: True.
- Fresh-workspace replay: True with 24 remapped identities.

The model session itself is preserved byte-for-byte in `mission-3-is-adult/agent-session.json`. `history.jsonl` labels captured model tool actions, host checks and replay as separate actors.

## Reproduction

```sh
python3 experiments/basic-workspace/scripts/provider-preflight.py --probe-timeout 90
python3 experiments/basic-workspace/scripts/resume-longitudinal-mission3.py --source-run experiments/basic-workspace/results/semantic-replay/longitudinal-01/calibrated-run-01 --output-dir experiments/basic-workspace/results/semantic-replay/longitudinal-01/<new-run>
python3 experiments/basic-workspace/scripts/finalize-longitudinal-resume.py --source-run experiments/basic-workspace/results/semantic-replay/longitudinal-01/calibrated-run-01 --resume-run experiments/basic-workspace/results/semantic-replay/longitudinal-01/<new-run>
```
