# Cycle 14 — Longitudinal session: preflight stop

## Outcome

No mission model session was started. The requested Sushi/Qwen provider was available in its model listing, but a bounded chat tool-call preflight did not establish usable tool calling: the first request exhausted a 24-token cap without a tool call, and a follow-up with a 128-token cap timed out after 45.1 seconds. Per the campaign stop rule, no mission requests were sent and no scripted construction was substituted for model actions.

The candidate configuration is saved locally in the ignored file `experiments/basic-workspace/.agent-provider.json`. Its endpoint and any credentials are deliberately absent from this report and the committed preflight record.

## Preflight details

- Model listing: HTTP 200; one model advertised; requested identifier found.
- Tool probe 1: 13.15 s; 296 prompt tokens, 24 completion tokens; finish reason `length`; no tool call.
- Tool probe 2: timed out at 45.10 s; no response bytes and no tool call.
- Model campaign turns/calls/commits: none.
- Missions completed: 0 of 3.
- Recovery checkpoint and constructive replay: not produced.

See `provider-preflight.json` for sanitized machine-readable evidence. This is endpoint preflight evidence, not a failed or successful agent mission transcript.

## Configuration work

The Workspace now has a shared local provider resolver, explicit conflict detection for current/legacy endpoint and model aliases, optional API-key environment references, sampling and timeout validation, and a bounded preflight command. The existing Cycle 12 age-edit and Cycle 13 function-composition runners use the shared resolver. The local provider file is ignored by Git.

Run the next preflight with:

```sh
python3 experiments/basic-workspace/scripts/provider-preflight.py \
  --output experiments/basic-workspace/results/semantic-replay/longitudinal-01/provider-preflight-next.json
```

Only after it reports `status: ok` should a longitudinal campaign begin. The command makes one model-list request and one required-tool request with a 128-token cap and no retries.

## Remaining work

Missions 1–3, checkpoint validation, deliberate context reset, portable reconstruction, and longitudinal visualization remain unexecuted. The central acceptance question therefore remains unanswered. A responsive, tool-compatible provider is required before those experiments can proceed.
