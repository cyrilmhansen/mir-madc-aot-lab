# Cycle 13B — Real model preflight

**Status: blocked before inference.** No chat-completions request was made.

The current shell has neither the prior Cycle 12 variables (`BASIC_WORKSPACE_LLM_ENDPOINT`, `BASIC_WORKSPACE_LLM_MODEL`) nor the Cycle 13 variables (`BASIC_WS_CHAT_COMPLETIONS_URL`, `BASIC_WS_MODEL`). The relevant API-key variables are also unset. The Cycle 13 campaign script accepts no endpoint/model CLI override, so there is no alternate configured source to use. Since both naming conventions are absent, there is no conflict to resolve.

Cycle 12's saved transcript identifies `gemma4:latest` and classifies its endpoint as loopback, but intentionally omits the endpoint URL. That historical model name is recorded for context only. It was not used as a substitute, and reachability, model availability, OpenAI-compatible format, and tool-calling support were not probed.

No real agent session, tool interaction, mission preview/commit, post-model validation, or real-agent replay exists for this attempt. `preflight.json` records the checks and the reason inference did not start. The existing scripted-mechanics campaign and prior Cycle 12 transcript remain untouched.

To resume this trial, provide both `BASIC_WS_CHAT_COMPLETIONS_URL` and `BASIC_WS_MODEL` in the process environment (and the configured key environment variable if authentication is required), then run the campaign once with `--output-dir experiments/basic-workspace/results/semantic-replay/is-senior/real-model-01`. The campaign will not substitute the Cycle 12 model or endpoint automatically.
