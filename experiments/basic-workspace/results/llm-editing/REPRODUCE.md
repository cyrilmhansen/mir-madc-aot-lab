# Reproduce the LLM editing trials

The runner uses Python's standard library only. It talks to an explicitly
configured OpenAI-compatible chat/completions endpoint and records provider
usage where returned. It never stores authorization headers or API key values.
The endpoint metadata in result files records only the host class and API path.

## Offline harness checks

    python3 -m unittest discover -s experiments/basic-workspace/tests -v
    python3 experiments/basic-workspace/experiment/llm_runner.py --fixture-test

The protocol fixture is not an LLM trial.

## Local Ollama example

The recorded local trial used gemma4:latest, temperature 0, 1024 output tokens
per turn, 8 iterations, 14 model tool calls per session, a 120-second request
timeout, tool timeout 10 seconds and seed 17. The endpoint was Ollama's local
OpenAI-compatible API. The exact host is intentionally not stored in results.

    python3 experiments/basic-workspace/experiment/llm_runner.py \
      --endpoint-url http://127.0.0.1:11434/v1/chat/completions \
      --model gemma4:latest \
      --request-timeout 120 \
      --max-output-tokens 1024 \
      --max-iterations 8 \
      --max-tool-calls 14 \
      --seed 17 \
      --think off

By default, all 15 non-conflict corpus tasks run in both arms; the conflict task
has a dedicated two-agent schedule. Use --limit 1 for a pilot. For another
OpenAI-compatible provider, pass its endpoint and model. To supply a key, set
an environment variable and pass only its name, for example
--api-key-env OPENAI_API_KEY; result files record whether authentication was
configured, never the value. Omit --seed if the endpoint does not support it.

## Outputs

- run.json: per-task raw assistant/tool traces, provider usage, correctness,
  failures, schema bytes, response bytes, inference waiting and tool time.
- trials.csv and SUMMARY.md: tabular outcomes and consolidated analysis.
- config.json: model/settings and redacted endpoint metadata.
- tool-definitions.json: exact function schemas sent to the model.
- discovery-efficiency.json / .md: scripted legacy-versus-compact query
  measurement, clearly separate from agent trials.
- multi-agent.json: scheduled shared-document conflict trial; the earlier
  rebase pilot is retained in multi-agent-pilot-rebased.json and is not counted
  as a stale-rejection success.

The completed batch ran all 15 non-conflict tasks once in each arm. To run only
the scheduled shared-document trial with the same explicit local settings:

    python3 experiments/basic-workspace/experiment/llm_runner.py \
      --endpoint-url http://127.0.0.1:11434/v1/chat/completions \
      --model gemma4:latest --request-timeout 120 \
      --max-output-tokens 1024 --max-iterations 8 --max-tool-calls 14 \
      --seed 17 --think off --multi-agent-only

Source text and expected outputs are read from the in-repository task corpus.
The model sees task text and tool results, never the expected field. Trials
use in-memory document/buffer state. Raw traces can include source excerpts
returned by tools, but contain no service authorization data.

## Fairness and interpretation

Both arms use the same model, task objective, temperature, response-token
limit, iteration limit, tool-call limit, seed and request timeout. The semantic
document and text buffer are fixture-loaded before the model starts; neither
agent receives source text directly in its initial prompt. The text agent must
read it through its tools. Both tool sets and schemas are included in measured
provider token accounting when the endpoint reports usage.

The semantic arm's compact exact symbol query avoids full reference dumps and
large structure pages unless the agent requests them. It does not include a
text replacement operation. The text arm can read ranges, search, apply one
unique exact-context patch with a version, inspect diffs and obtain subset
diagnostics. A stale or ambiguous patch fails without mutation.

Compiler execution is not automatically invoked for each model trial.
text_diagnostics/validate_program use the Workspace subset parser and do not
establish compiler-level behavioral equivalence. This avoids launching
interactive or side-effecting historical demos.
