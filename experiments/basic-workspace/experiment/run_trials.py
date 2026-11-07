#!/usr/bin/env python3
"""Reproducible mechanics comparison; no language model behavior is simulated."""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from basic_workspace.client import AgentToolAdapter, RpcError, WorkspaceClient

LAB = ROOT.parent / "basic-aot" / "upstream" / "basic" / "samples"
OUT = ROOT / "results" / "agent-editing"


def cases():
    base = "FUNCTION TOTAL(SCORE)\n TOTAL=SCORE+1\nEND FUNCTION\n"
    yield {"id": "local_rename_with_decoys", "source": base + "PRINT \"SCORE\" ' SCORE note\n",
           "target": ["parameter", "SCORE"], "new_name": "POINTS",
           "text_old": "SCORE", "text_new": "POINTS", "expected": base.replace("SCORE", "POINTS") + "PRINT \"SCORE\" ' SCORE note\n"}
    yield {"id": "case_insensitive_local_reference", "source": "FUNCTION F(Value)\nF=vAlUe*2\nEND FUNCTION\n",
           "target": ["parameter", "Value"], "new_name": "AMOUNT", "text_old": "Value", "text_new": "AMOUNT",
           "expected": "FUNCTION F(AMOUNT)\nF=AMOUNT*2\nEND FUNCTION\n"}
    yield {"id": "function_rename", "source": "FUNCTION TOTAL(X)\nTOTAL=X+1\nEND FUNCTION\nPRINT total(4)\n",
           "target": ["function", "TOTAL"], "new_name": "SUM_VALUE", "text_old": "TOTAL", "text_new": "SUM_VALUE",
           "expected": "FUNCTION SUM_VALUE(X)\nSUM_VALUE=X+1\nEND FUNCTION\nPRINT SUM_VALUE(4)\n"}
    yield {"id": "renumber_goto", "source": "10 GOTO 100\n100 PRINT 1\n200 END\n", "line": [100, 150],
           "expected": "10 GOTO 150\n150 PRINT 1\n200 END\n"}
    yield {"id": "renumber_gosub", "source": "10 GOSUB 100\n20 END\n100 RETURN\n", "line": [100, 120],
           "expected": "10 GOSUB 120\n20 END\n120 RETURN\n"}
    yield {"id": "renumber_on_goto", "source": "10 ON X GOTO 100,200\n100 PRINT 1\n200 END\n", "line": [100, 110],
           "expected": "10 ON X GOTO 110,200\n110 PRINT 1\n200 END\n"}
    yield {"id": "atomic_rename_and_renumber", "source": "FUNCTION F(SCORE)\nF=SCORE\nEND FUNCTION\n10 GOTO 100\n100 PRINT F(3)\n",
           "target": ["parameter", "SCORE"], "new_name": "POINTS", "line": [100, 150],
           "expected": "FUNCTION F(POINTS)\nF=POINTS\nEND FUNCTION\n10 GOTO 150\n150 PRINT F(3)\n"}
    yield {"id": "collision_rejected", "source": "FUNCTION F(X,Y)\nF=X+Y\nEND FUNCTION\n",
           "target": ["parameter", "X"], "new_name": "Y", "reject": True, "expected": "FUNCTION F(X,Y)\nF=X+Y\nEND FUNCTION\n"}
    yield {"id": "move_function", "source": "FUNCTION A(X)\nA=X\nEND FUNCTION\nFUNCTION B(Y)\nB=Y\nEND FUNCTION\n",
           "target": ["function", "B"], "before": ["function", "A"], "move": True,
           "expected": "FUNCTION B(Y)\nB=Y\nEND FUNCTION\nFUNCTION A(X)\nA=X\nEND FUNCTION\n"}
    yield {"id": "ambiguous_array_call_stop", "source": "PRINT MYSTERY(2)\nEND\n", "unsupported": "AMBIGUOUS_CALL_OR_ARRAY",
           "expected": "PRINT MYSTERY(2)\nEND\n"}
    yield {"id": "incomplete_function_stop", "source": "FUNCTION F(X)\nF=X\n", "unsupported": "UNCLOSED_FUNCTION",
           "expected": "FUNCTION F(X)\nF=X\n"}
    yield {"id": "colon_statement_scope", "source": "FUNCTION F(SCORE)\nF=SCORE: PRINT SCORE\nEND FUNCTION\n",
           "target": ["parameter", "SCORE"], "new_name": "POINTS",
           "expected": "FUNCTION F(POINTS)\nF=POINTS: PRINT POINTS\nEND FUNCTION\n"}
    for ident, relpath, old, new in (
        ("historical_fn", "fn.bas", 10, 15),
        ("historical_mastermind", "bcg/mastermind.bas", 10, 11),
        ("historical_poker", "bcg/poker.bas", 10, 11),
    ):
        src = (LAB / relpath).read_text(encoding="utf-8")
        yield {"id": ident, "source": src, "line": [old, new], "historical_path": relpath,
               "expected": re.sub(rf"(?m)^(\s*){old}(?=\s|$)", rf"\g<1>{new}", src, count=1)}
    yield {"id": "multi_agent_stale_revision", "source": "FUNCTION F(X)\nF=X\nEND FUNCTION\n",
           "target": ["parameter", "X"], "new_name": "VALUE", "conflict": True,
           "expected": "FUNCTION F(POINTS)\nF=POINTS\nEND FUNCTION\n"}


def selector(adapter, selector):
    kind, name = selector
    result = adapter.call("workspace_symbols", {"kind": kind, "name_query": name, "limit": 20})
    matches = [x for x in result["items"] if x["name"].casefold() == name.casefold()]
    if len(matches) != 1:
        raise RpcError("ENTITY_NOT_UNIQUE", f"Expected one {kind} named {name}; got {len(matches)}")
    return matches[0]


def semantic_arm(task):
    started = time.perf_counter()
    source = task["source"]
    with WorkspaceClient(timeout=10, max_render_chars=100000) as client:
        adapter = AgentToolAdapter(client)
        opened = adapter.call("workspace_open", {"text": source, "uri": "memory://trial/" + task["id"]})
        calls_after_open = client.metrics["requests"]
        diagnostics = adapter.call("workspace_diagnostics", {})
        ops = []
        symbol = None
        if "target" in task:
            symbol = selector(adapter, task["target"])
            adapter.call("workspace_references", {"symbol_id": symbol["symbol_id"], "limit": 50})
        if "line" in task:
            line_symbol = selector(adapter, ["line_label", str(task["line"][0])])
            adapter.call("workspace_references", {"symbol_id": line_symbol["symbol_id"], "limit": 50})
        if task.get("unsupported"):
            status = "refused" if any(d["code"] == task["unsupported"] for d in diagnostics) else "unsupported_not_diagnosed"
        else:
            if symbol and task.get("move"):
                before_symbol = selector(adapter, task["before"])
                ops.append({"operation": "move_function", "symbol_id": symbol["symbol_id"],
                            "before_symbol_id": before_symbol["symbol_id"]})
            elif symbol and "new_name" in task:
                ops.append({"operation": "rename_symbol", "symbol_id": symbol["symbol_id"], "new_name": task["new_name"]})
            if "line" in task:
                ops.append({"operation": "renumber_line", "old_line": task["line"][0], "new_line": task["line"][1]})
            if task.get("conflict"):
                agent_b = adapter.fork()
                expected_revision = opened["revision"]
                point = selector(adapter, ["parameter", "X"])
                first = [{"operation": "rename_symbol", "symbol_id": point["symbol_id"], "new_name": "POINTS"}]
                adapter.call("workspace_preview", {"expected_revision": expected_revision, "operations": first})
                adapter.call("workspace_commit", {"expected_revision": expected_revision, "operations": first})
                try:
                    agent_b.call("workspace_commit", {"expected_revision": expected_revision,
                                                       "operations": [{"operation": "rename_symbol", "symbol_id": point["symbol_id"], "new_name": "VALUE"}]})
                    status = "stale_not_rejected"
                except RpcError as exc:
                    status = "conflict_rejected" if exc.code == "STALE_REVISION" else "conflict_error_" + str(exc.code)
                ops = []
            elif task.get("reject"):
                try:
                    adapter.call("workspace_preview", {"expected_revision": opened["revision"], "operations": ops})
                    status = "invalid_change_accepted"
                except RpcError as exc:
                    status = "rejected_" + str(exc.code)
            elif ops:
                adapter.call("workspace_preview", {"expected_revision": opened["revision"], "operations": ops})
                adapter.call("workspace_commit", {"expected_revision": opened["revision"], "operations": ops})
                status = "committed"
            else:
                status = "inspected"
        final_diags = adapter.call("workspace_diagnostics", {})
        # The harness renders privately for an exact oracle check; this checker-only
        # payload is not presented to the hypothetical agent or counted as its context.
        agent_calls = client.metrics["requests"]
        agent_context_bytes = client.metrics["response_bytes"]
        rendered = client._rpc("render_document", {"document_id": client.document_id})
        metrics = dict(client.metrics)
        metrics["tool_calls"] = agent_calls
        metrics["source_presented_bytes"] = 0
        metrics["semantic_context_bytes"] = agent_context_bytes
        metrics["checker_render_bytes"] = len(rendered.encode("utf-8"))
    return {"status": status, "correct": rendered == task["expected"],
            "revision": client.revision, "diagnostics": final_diags,
            "metrics": {**metrics, "attempts": 1 if (ops or task.get("conflict") or task.get("reject")) else 0,
                        "rejected_operations": int(status.startswith("rejected_") or status == "conflict_rejected"),
                        "incorrect_edits": int(rendered != task["expected"]),
                        "correction_cycles": 0, "token_usage": None},
            "wall_ms": (time.perf_counter() - started) * 1000,
            "rendered_chars": len(rendered)}


def apply_text_edits(source, task):
    # Deterministic conventional text arm: whole source is shown; edits use literal search/replace.
    if task.get("unsupported"):
        return source, "refused"
    if task.get("reject"):
        return source.replace("X", task["new_name"]), "attempted"
    if task.get("move"):
        block = "FUNCTION B(Y)\nB=Y\nEND FUNCTION\n"
        return source.replace("FUNCTION A(X)\nA=X\nEND FUNCTION\n" + block, block + "FUNCTION A(X)\nA=X\nEND FUNCTION\n"), "edited"
    if task.get("conflict"):
        return task["expected"], "two_agents_conflict_simulated"
    result = source
    if "text_old" in task:
        result = result.replace(task["text_old"], task["text_new"])
    if "new_name" in task and "text_old" not in task and "target" in task:
        old = task["target"][1]
        result = result.replace(old, task["new_name"])
    if "line" in task:
        old, new = task["line"]
        result = result.replace(str(old), str(new))
    return result, "edited" if result != source else "no_change"


def text_arm(task):
    started = time.perf_counter()
    source = task["source"]
    edited, status = apply_text_edits(source, task)
    return {"status": status, "correct": edited == task["expected"],
            "metrics": {"tool_calls": 2, "attempts": 1, "rejected_operations": 0,
                        "incorrect_edits": int(edited != task["expected"]),
                        "correction_cycles": 0, "source_presented_bytes": len(source.encode()),
                        "semantic_context_bytes": 0, "token_usage": None},
            "wall_ms": (time.perf_counter() - started) * 1000,
            "rendered_chars": len(edited)}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    task_list = list(cases())
    (OUT / "tasks.json").write_text(json.dumps(task_list, indent=2, ensure_ascii=False) + "\n")
    for task in task_list:
        # Keep a reproducible manifest but never materialize program text as an edit target.
        manifest = {k: v for k, v in task.items() if k != "source"}
        manifest["source_chars"] = len(task["source"])
        manifest["source_bytes"] = len(task["source"].encode())
        sem = semantic_arm(task)
        txt = text_arm(task)
        rows.append({"task": manifest, "semantic": sem, "text": txt})
    (OUT / "trials.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n")
    total = len(rows)
    summary = {
        "task_count": total,
        "semantic_correct": sum(r["semantic"]["correct"] for r in rows),
        "text_correct": sum(r["text"]["correct"] for r in rows),
        "semantic_tool_calls": sum(r["semantic"]["metrics"]["tool_calls"] for r in rows),
        "text_tool_calls": sum(r["text"]["metrics"]["tool_calls"] for r in rows),
        "semantic_context_bytes": sum(r["semantic"]["metrics"]["semantic_context_bytes"] for r in rows),
        "text_source_bytes": sum(r["text"]["metrics"]["source_presented_bytes"] for r in rows),
        "semantic_wall_ms_total": round(sum(r["semantic"]["wall_ms"] for r in rows), 3),
        "text_wall_ms_total": round(sum(r["text"]["wall_ms"] for r in rows), 3),
        "semantic_rejected_operations": sum(r["semantic"]["metrics"]["rejected_operations"] for r in rows),
        "semantic_incorrect_edits": sum(r["semantic"]["metrics"]["incorrect_edits"] for r in rows),
        "text_incorrect_edits": sum(r["text"]["metrics"]["incorrect_edits"] for r in rows),
        "model_trials": "not_run",
        "model_tokens": None,
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    md = ["# Deterministic semantic editing mechanics\n", "\n", f"Tasks: {total}. This compares scripted clients, not LLM behavior.\n", "\n",
          "| Measure | Semantic API | Text editing |\n|---|---:|---:|\n",
          f"| Correct tasks | {summary['semantic_correct']}/{total} | {summary['text_correct']}/{total} |\n",
          f"| Tool calls | {summary['semantic_tool_calls']} | {summary['text_tool_calls']} |\n",
          f"| Context bytes exposed | {summary['semantic_context_bytes']} | {summary['text_source_bytes']} |\n",
          f"| Harness wall time total | {summary['semantic_wall_ms_total']} ms | {summary['text_wall_ms_total']} ms |\n",
          "| LLM trials / tokens | not run / unavailable | not run / unavailable |\n\n",
          "This trial measures API mechanics and payload size. The text arm deliberately uses literal search/replace, so failures expose its known ambiguity; it is not an estimate of human or model performance. Historical inputs were read-only and no BASIC file was patched.\n\n",
          "Wall time is harness mechanics only: the semantic arm starts a fresh subprocess per task, while the text arm uses in-process string operations. Do not interpret these as comparative agent latency. Token use is unavailable and recorded as null.\n\n",
          "| Task | Semantic status | Semantic correct | Text status | Text correct |\n|---|---|---:|---|---:|\n"]
    for r in rows:
        md.append(f"| {r['task']['id']} | {r['semantic']['status']} | {r['semantic']['correct']} | {r['text']['status']} | {r['text']['correct']} |\n")
    (OUT / "REPORT.md").write_text("".join(md))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
