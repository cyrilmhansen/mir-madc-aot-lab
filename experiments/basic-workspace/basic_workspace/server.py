"""JSON-RPC 2.0 service, one request/response JSON object per stdin/stdout line."""
from __future__ import annotations

import json
import sys

from .model import Workspace, WorkspaceError


def serve() -> None:
    workspace = Workspace()
    for raw in sys.stdin:
        request: dict = {}
        try:
            request = json.loads(raw)
            if not isinstance(request, dict) or request.get("jsonrpc") != "2.0":
                raise WorkspaceError("INVALID_REQUEST", "Expected JSON-RPC 2.0 request")
            method = request.get("method")
            params = request.get("params") or {}
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
