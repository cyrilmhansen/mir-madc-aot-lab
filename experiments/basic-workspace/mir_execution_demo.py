#!/usr/bin/env python3
"""Show semantic editing followed by direct in-memory MIR interpreter/JIT runs."""
from __future__ import annotations

import json

from basic_workspace.client import WorkspaceClient


SOURCE = """FUNCTION SCALE(X)
  SCALE = (X + 1) * 2
END FUNCTION
FUNCTION APPLY(Y)
  APPLY = SCALE(Y) + 3
END FUNCTION
"""


def main() -> None:
    with WorkspaceClient() as client:
        opened = client.workspace_open(SOURCE)
        document_id = opened["document_id"]
        structure = client.workspace_structure()
        scale, apply = structure["functions"]
        before = client.workspace_execute_function(1, scale["symbol_id"], [8], "interp")

        parameter = client.workspace_symbols(kind="parameter", exact_name="X", unique=True)["unique_symbol"]
        ops = [{"operation": "rename_symbol", "symbol_id": parameter["symbol_id"],
                "new_name": "POINTS"}]
        preview = client.workspace_preview(1, ops, include_diff=True)
        committed = client.workspace_commit(1, ops)
        after_parameter_edit = client.workspace_execute_function(
            committed["revision"], scale["symbol_id"], [8], "jit")

        scale_symbol = client.workspace_symbols(kind="function", exact_name="SCALE",
                                                unique=True)["unique_symbol"]
        rename = [{"operation": "rename_symbol", "symbol_id": scale_symbol["symbol_id"],
                   "new_name": "MULTIPLY_SHIFT"}]
        committed_function = client.workspace_commit(2, rename)
        after_function_edit = client.workspace_execute_function(
            committed_function["revision"], apply["symbol_id"], [8], "interp")
        rendered = client.workspace_render()
        print(json.dumps({
            "document_id": document_id,
            "revisions": [1, preview["expected_result_revision"], committed_function["revision"]],
            "function_identity_preserved": scale["symbol_id"] == scale_symbol["symbol_id"],
            "before": before["result"],
            "after_parameter_rename": after_parameter_edit["result"],
            "after_function_rename_and_bound_call_update": after_function_edit["result"],
            "rendered_source_after_explicit_request": rendered["text"],
            "engine_timings_ms": {"before": before["timings_ms"],
                                  "after_parameter_edit": after_parameter_edit["timings_ms"],
                                  "after_function_edit": after_function_edit["timings_ms"]},
        }, indent=2))


if __name__ == "__main__":
    main()
