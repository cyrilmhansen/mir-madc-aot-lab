"""JSON-RPC 2.0 service, one request/response JSON object per stdin/stdout line."""
from __future__ import annotations

import json
import sys

from .model import Workspace, WorkspaceError
from .mir_execution import MirExecutionService


def serve() -> None:
    workspace = Workspace()
    mir_execution = MirExecutionService()
    for raw in sys.stdin:
        request: dict = {}
        try:
            request = json.loads(raw)
            if not isinstance(request, dict) or request.get("jsonrpc") != "2.0":
                raise WorkspaceError("INVALID_REQUEST", "Expected JSON-RPC 2.0 request")
            method = request.get("method")
            params = request.get("params") or {}
            if method == "execute_function":
                document_id = params["document_id"]
                function_id = params["function_id"]
                if not workspace.symbol_was_discovered(document_id, function_id):
                    raise WorkspaceError("SYMBOL_NOT_DISCOVERED", "Discover the function through workspace_symbols or workspace_structure first")
                result = mir_execution.execute_function(
                    workspace, document_id, params["expected_revision"], function_id,
                    params.get("arguments", []), params.get("engine", "interp"))
            else:
                result = workspace.protocol_call(method, params)
            response = {"jsonrpc": "2.0", "id": request.get("id"), "result": result}
        except WorkspaceError as exc:
            response = {"jsonrpc": "2.0", "id": request.get("id"),
                        "error": {"code": -32000, "message": exc.message,
                                  "data": exc.json()}}
        except Exception as exc:  # protocol boundary: never terminate on a bad request
            response = {"jsonrpc": "2.0", "id": request.get("id"),
                        "error": {"code": -32602, "message": str(exc)}}
        sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    serve()
