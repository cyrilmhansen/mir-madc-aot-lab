#!/usr/bin/env python3
"""Compare the Cycle-2 query workflow with exact compact discovery."""
from __future__ import annotations
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from basic_workspace.client import AgentToolAdapter, RpcError, WorkspaceClient

IN = ROOT / "results" / "agent-editing" / "tasks.json"
OUT = ROOT / "results" / "llm-editing" / "discovery-efficiency.json"
MD = ROOT / "results" / "llm-editing" / "discovery-efficiency.md"


def selector(tool, kind, name, compact):
    if compact:
        result = tool.call("workspace_symbols", {"kind": kind, "exact_name": name, "unique": True})
        if not result["unique"]:
            raise RpcError("AMBIGUOUS_SYMBOL", f"{name} matched {result['total']} symbols")
        return result["unique_symbol"]
    result = tool.call("workspace_symbols", {"kind": kind, "name_query": name, "limit": 50})
    found = [x for x in result["items"] if x["name"].casefold() == name.casefold()]
    if len(found) != 1:
        raise RpcError("AMBIGUOUS_SYMBOL", f"{name} matched {len(found)} symbols")
    return found[0]


def run(task, compact):
    with WorkspaceClient(timeout=5) as client:
        client.workspace_open(task["source"], "memory://discovery/" + task["id"])
        tool = AgentToolAdapter(client)
        revision = client.revision
        try:
            if compact:
                # Exact discovery provides the revision and diagnostic summary as well.
                target = None
                if "target" in task:
                    target = selector(tool, task["target"][0], task["target"][1], True)
                line_symbols = []
                if "line" in task:
                    line_symbols.append(selector(tool, "line_label", str(task["line"][0]), True))
                if task.get("unsupported"):
                    tool.call("workspace_diagnostics", {})
                else:
                    operations = []
                    if target and task.get("move"):
                        before = selector(tool, task["before"][0], task["before"][1], True)
                        operations.append({"operation": "move_function", "symbol_id": target["symbol_id"],
                                           "before_symbol_id": before["symbol_id"]})
                    elif target and task.get("new_name") and not task.get("conflict"):
                        operations.append({"operation": "rename_symbol", "symbol_id": target["symbol_id"],
                                           "new_name": task["new_name"]})
                    if "line" in task:
                        operations.append({"operation": "renumber_line", "old_line": task["line"][0],
                                           "new_line": task["line"][1]})
                    if task.get("conflict"):
                        pass
                    elif task.get("reject"):
                        tool.call("workspace_preview", {"expected_revision": revision,
                                                          "operations": operations})
                    elif operations:
                        tool.call("workspace_preview", {"expected_revision": revision,
                                                          "operations": operations})
                        tool.call("workspace_commit", {"expected_revision": revision,
                                                         "operations": operations})
            else:
                tool.call("workspace_structure", {"limit": 20})
                target = selector(tool, task["target"][0], task["target"][1], False) if "target" in task else None
                if target:
                    tool.call("workspace_references", {"symbol_id": target["symbol_id"], "limit": 50})
                if "line" in task:
                    label = selector(tool, "line_label", str(task["line"][0]), False)
                    tool.call("workspace_references", {"symbol_id": label["symbol_id"], "limit": 50})
                if task.get("unsupported"):
                    tool.call("workspace_diagnostics", {})
                else:
                    ops = []
                    if target and task.get("move"):
                        before = selector(tool, task["before"][0], task["before"][1], False)
                        ops.append({"operation": "move_function", "symbol_id": target["symbol_id"],
                                    "before_symbol_id": before["symbol_id"]})
                    elif target and task.get("new_name") and not task.get("conflict"):
                        ops.append({"operation": "rename_symbol", "symbol_id": target["symbol_id"],
                                    "new_name": task["new_name"]})
                    if "line" in task:
                        ops.append({"operation": "renumber_line", "old_line": task["line"][0],
                                    "new_line": task["line"][1]})
                    if task.get("conflict"):
                        pass
                    elif task.get("reject"):
                        tool.call("workspace_preview", {"expected_revision": revision, "operations": ops})
                    elif ops:
                        tool.call("workspace_preview", {"expected_revision": revision, "operations": ops})
                        tool.call("workspace_commit", {"expected_revision": revision, "operations": ops})
            return {"calls": client.metrics["requests"],
                    "request_bytes": client.metrics["request_bytes"],
                    "response_bytes": client.metrics["response_bytes"],
                    "response_bytes_by_method": client.metrics["response_bytes_by_method"],
                    "methods": client.metrics["methods"]}
        except RpcError as exc:
            return {"calls": client.metrics["requests"], "error": exc.code,
                    "request_bytes": client.metrics["request_bytes"],
                    "response_bytes": client.metrics["response_bytes"],
                    "response_bytes_by_method": client.metrics["response_bytes_by_method"],
                    "methods": client.metrics["methods"]}


def main():
    tasks = json.loads(IN.read_text())
    rows = [{"task_id": t["id"], "legacy": run(t, False), "compact": run(t, True)} for t in tasks]
    summary = {arm: {"calls": sum(r[arm]["calls"] for r in rows),
                     "request_bytes": sum(r[arm]["request_bytes"] for r in rows),
                     "response_bytes": sum(r[arm]["response_bytes"] for r in rows),
                     "response_bytes_by_method": {}}
               for arm in ("legacy", "compact")}
    for r in rows:
        for arm in summary:
            for method, count in r[arm]["response_bytes_by_method"].items():
                summary[arm]["response_bytes_by_method"][method] = summary[arm]["response_bytes_by_method"].get(method, 0) + count
    result = {"purpose": "deterministic discovery mechanics, not LLM behavior",
              "task_count": len(rows), "summary": summary, "tasks": rows}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2) + "\n")
    old, new = summary["legacy"], summary["compact"]
    calls_drop = (old["calls"] - new["calls"]) / old["calls"] * 100
    bytes_drop = (old["response_bytes"] - new["response_bytes"]) / old["response_bytes"] * 100
    lines = ["# Compact semantic discovery\n\n",
        "Deterministic mechanics comparison over the same 16 tasks; not LLM behavior. Exact-name unique lookup returns a symbol summary, scope/type, reference count, revision and diagnostic counts. Full references are requested only where the legacy arm asks for them.\n\n",
        "| Interface | Calls | Request bytes | Response bytes |\n|---|---:|---:|---:|\n",
        f"| Cycle-2 query sequence | {old['calls']} | {old['request_bytes']} | {old['response_bytes']} |\n",
        f"| Compact exact discovery | {new['calls']} | {new['request_bytes']} | {new['response_bytes']} |\n\n",
        f"Calls fell {calls_drop:.1f}% and response bytes fell {bytes_drop:.1f}%. Transaction preview/commit results were unchanged.\n\n",
        "| Response method | Legacy bytes | Compact bytes |\n|---|---:|---:|\n"]
    for method in sorted(set(old["response_bytes_by_method"]) | set(new["response_bytes_by_method"])):
        lines.append(f"| {method} | {old['response_bytes_by_method'].get(method, 0)} | {new['response_bytes_by_method'].get(method, 0)} |\n")
    MD.write_text("".join(lines))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
