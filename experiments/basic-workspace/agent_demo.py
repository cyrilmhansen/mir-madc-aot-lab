#!/usr/bin/env python3
"""Worked in-memory semantic edit over the constrained agent tool surface."""
from __future__ import annotations

import json

from basic_workspace.client import AgentToolAdapter, WorkspaceClient


def main() -> None:
    source = ('FUNCTION TOTAL(SCORE)\n'
              '  TOTAL = SCORE + 1\n'
              'END FUNCTION\n')
    with WorkspaceClient() as client:
        tools = AgentToolAdapter(client)
        trace = []
        opened = tools.call("workspace_open", {"text": source, "uri": "memory://demo/total.bas"})
        trace.append({"step": "load in memory", "revision": opened["revision"]})
        structure = tools.call("workspace_structure", {"limit": 10})
        trace.append({"step": "inspect structure", "functions": structure["functions"],
                      "line_count": structure["page"]["physical_line_total"]})
        symbols = tools.call("workspace_symbols", {"kind": "parameter", "name_query": "score"})
        score = symbols["items"][0]
        trace.append({"step": "discover parameter", "symbol": score})
        refs = tools.call("workspace_references", {"symbol_id": score["symbol_id"]})
        trace.append({"step": "inspect references", "items": refs["items"]})
        operations = [{"operation": "rename_symbol", "symbol_id": score["symbol_id"],
                       "new_name": "POINTS"}]
        preview = tools.call("workspace_preview", {"expected_revision": opened["revision"],
                                                    "operations": operations})
        trace.append({"step": "preview", "valid": preview["valid"],
                      "affected_entities": preview["affected_entities"],
                      "expected_result_revision": preview["expected_result_revision"]})
        committed = tools.call("workspace_commit", {"expected_revision": opened["revision"],
                                                     "operations": operations})
        diagnostics = tools.call("workspace_diagnostics", {})
        trace.append({"step": "commit and verify", "revision": committed["revision"],
                      "diagnostics": diagnostics})
        # Render only when a caller explicitly needs a textual export.
        rendered = tools.call("workspace_render", {"max_chars": 1000})
        trace.append({"step": "optional render", "text": rendered["text"]})
        print(json.dumps({"trace": trace, "transport": client.metrics}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
