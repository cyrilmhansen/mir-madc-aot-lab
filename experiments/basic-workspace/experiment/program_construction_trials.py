#!/usr/bin/env python3
"""Run real LLM construction tasks through semantic and text tool arms."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import time

from llm_runner import (ChatEndpoint, ToolRunner, CONSTRUCTION_SEMANTIC_TOOLS,
    CONSTRUCTION_TEXT_TOOLS, endpoint_metadata, run_session)
from basic_workspace.client import AgentToolAdapter, WorkspaceClient


ROOT = Path(__file__).resolve().parents[1]
TASKS_PATH = ROOT / "results/program-construction/tasks.json"
RESULTS = ROOT / "results/program-construction/llm-trials"


def args_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint-url", required=True, help="OpenAI-compatible /chat/completions endpoint")
    parser.add_argument("--model", required=True)
    parser.add_argument("--api-key-env", default=None, help="Environment variable name; value is never stored")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-output-tokens", type=int, default=1024)
    parser.add_argument("--max-tool-calls", type=int, default=20)
    parser.add_argument("--max-iterations", type=int, default=14)
    parser.add_argument("--request-timeout", type=float, default=120)
    parser.add_argument("--tool-timeout", type=float, default=10)
    parser.add_argument("--max-context-bytes", type=int, default=64000)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--think", choices=("on", "off", "endpoint-default"), default="endpoint-default")
    parser.add_argument("--limit", type=int, default=None, help="Run first N tasks as a pilot")
    parser.add_argument("--output-dir", type=Path, default=RESULTS,
                        help="Directory for raw trial results (defaults to the construction experiment results)")
    return parser.parse_args()


def main():
    args = args_parser()
    endpoint_url = args.endpoint_url.rstrip("/")
    if not endpoint_url.endswith("/chat/completions"):
        endpoint_url += "/chat/completions"
    api_key = os.environ.get(args.api_key_env) if args.api_key_env else None
    think = True if args.think == "on" else False if args.think == "off" else None
    endpoint = ChatEndpoint(endpoint_url, args.model, api_key, args.temperature,
                            args.max_output_tokens, args.request_timeout, args.seed, think)
    tasks = json.loads(TASKS_PATH.read_text(encoding="utf-8"))
    if args.limit:
        tasks = tasks[:args.limit]
    config = {"model_requested": args.model, "endpoint_metadata": endpoint_metadata(endpoint_url),
              "authentication_configured": bool(api_key),
              "api_key_env_name": args.api_key_env if api_key else None,
              "temperature": args.temperature, "max_output_tokens": args.max_output_tokens,
              "max_tool_calls": args.max_tool_calls, "max_iterations": args.max_iterations,
              "max_context_bytes": args.max_context_bytes, "request_timeout_seconds": args.request_timeout,
              "tool_timeout_seconds": args.tool_timeout, "seed": args.seed,
              "think_mode": args.think, "tasks": [x["id"] for x in tasks],
              "arms": ["semantic", "text"]}
    results_dir = args.output_dir
    results_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / "tool-definitions.json").write_text(json.dumps({
        "semantic": CONSTRUCTION_SEMANTIC_TOOLS, "text": CONSTRUCTION_TEXT_TOOLS},
        indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    trials = []
    batch_started = time.perf_counter()
    with WorkspaceClient(timeout=args.tool_timeout, max_render_chars=20000) as client:
        for task in tasks:
            for arm in ("semantic", "text"):
                if arm == "semantic":
                    # The host establishes the empty document before the model
                    # turn, so the agent never has to guess/create its target.
                    client.workspace_create_empty()
                    adapter = AgentToolAdapter(client)
                    runner = ToolRunner(arm, client=client, adapter=adapter, source="")
                else:
                    runner = ToolRunner(arm, source="")
                runner.construction_stale_once = bool(task.get("stale_conflict"))
                trial = run_session(endpoint, arm, task, runner, args.max_tool_calls,
                    args.max_iterations, construction=True,
                    max_context_bytes=args.max_context_bytes)
                trial["task_category"] = "must_refuse" if task.get("must_refuse") else (
                    "stale_conflict" if task.get("stale_conflict") else "valid_construction")
                trials.append(trial)
                snapshot = {"status": "in_progress", "configuration": config,
                            "summary": summarize(trials), "trials": trials}
                (results_dir / "trials.json").write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n",
                                                      encoding="utf-8")
    result = {"status": "completed", "configuration": config,
              "summary": summarize(trials),
              "batch_wall_ms": round((time.perf_counter() - batch_started) * 1000, 3),
              "schema_bytes": {"semantic": len(json.dumps(CONSTRUCTION_SEMANTIC_TOOLS,
                                                              separators=(",", ":")).encode()),
                               "text": len(json.dumps(CONSTRUCTION_TEXT_TOOLS,
                                                          separators=(",", ":")).encode())},
              "trials": trials}
    (results_dir / "trials.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n",
                                          encoding="utf-8")
    print(json.dumps({"status": result["status"], "summary": result["summary"],
                      "batch_wall_ms": result["batch_wall_ms"],
                      "schema_bytes": result["schema_bytes"]}, indent=2))


def summarize(trials):
    arms = {}
    for arm in ("semantic", "text"):
        rows = [x for x in trials if x["arm"] == arm]
        correct = sum(bool(x["correct"]) for x in rows)
        arms[arm] = {"tasks": len(rows), "correct": correct,
                     "accuracy": correct / len(rows) if rows else None,
                     "mean_tool_calls": sum(x["model_tool_calls"] for x in rows) / len(rows) if rows else None,
                     "mean_turns": sum(x["model_turns"] for x in rows) / len(rows) if rows else None,
                     "mean_inference_wait_ms": sum(x["inference_wait_ms"] for x in rows) / len(rows) if rows else None,
                     "mean_tool_response_bytes": sum(x["tool_response_bytes"] for x in rows) / len(rows) if rows else None,
                     "mean_schema_bytes": sum(x["schema_bytes"] for x in rows) / len(rows) if rows else None,
                     "provider_token_totals": {key: sum((x.get("provider_usage") or {}).get(key, 0)
                         for x in rows) for key in ("prompt_tokens", "completion_tokens", "total_tokens")
                         if any((x.get("provider_usage") or {}).get(key) is not None for x in rows)}}
    return {"arms": arms}


if __name__ == "__main__":
    main()
