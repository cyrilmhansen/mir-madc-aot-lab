"""JSON-RPC 2.0 service, one request/response JSON object per stdin/stdout line."""
from __future__ import annotations

import json
import sys

from .model import Workspace, WorkspaceError
from .mir_execution import MirExecutionService


def _check_discovered_expression(workspace: Workspace, document_id: str, expression: dict) -> None:
    if not isinstance(expression, dict):
        return
    kind = expression.get("kind")
    if kind == "symbol_ref":
        sid = expression.get("symbol_id")
        if not workspace.symbol_was_discovered(document_id, sid):
            raise WorkspaceError("SYMBOL_NOT_DISCOVERED", "Discover expression symbols before using their identities")
    elif kind == "call":
        sid = expression.get("function_id")
        if not workspace.symbol_was_discovered(document_id, sid):
            raise WorkspaceError("SYMBOL_NOT_DISCOVERED", "Discover called functions before using their identities")
        for child in expression.get("arguments", []):
            _check_discovered_expression(workspace, document_id, child)
    elif kind == "unary":
        _check_discovered_expression(workspace, document_id, expression.get("operand"))
    elif kind == "binary":
        _check_discovered_expression(workspace, document_id, expression.get("left"))
        _check_discovered_expression(workspace, document_id, expression.get("right"))
    elif kind == "array_element":
        array_ref = expression.get("array_ref", {})
        if isinstance(array_ref, dict) and array_ref.get("kind") == "symbol_ref":
            if not workspace.symbol_was_discovered(document_id, array_ref.get("symbol_id")):
                raise WorkspaceError("SYMBOL_NOT_DISCOVERED", "Discover arrays before using their identities")
        _check_discovered_expression(workspace, document_id, expression.get("index"))


def _check_discovered_operations(workspace: Workspace, document_id: str,
                                 operations: list[dict]) -> None:
    for operation in operations:
        kind = operation.get("operation")
        if kind == "edit_assignment_expression":
            if not workspace.statement_was_discovered(document_id, operation.get("statement_id")):
                raise WorkspaceError("STATEMENT_NOT_DISCOVERED", "Discover the assignment through workspace_statements first")
        elif kind == "insert_numeric_assignment":
            if not workspace.symbol_was_discovered(document_id, operation.get("function_id")):
                raise WorkspaceError("SYMBOL_NOT_DISCOVERED", "Discover the function before inserting an assignment")
            before = operation.get("before_statement_id")
            if before is not None and not workspace.statement_was_discovered(document_id, before):
                raise WorkspaceError("STATEMENT_NOT_DISCOVERED", "Discover the insertion point first")
        if "expression" in operation:
            _check_discovered_expression(workspace, document_id, operation["expression"])
        if kind == "create_numeric_function":
            for local in operation.get("locals", []):
                if isinstance(local, dict) and "expression" in local:
                    _check_discovered_expression(workspace, document_id, local["expression"])
            for assignment in operation.get("array_assignments", []):
                if isinstance(assignment, dict):
                    ref = assignment.get("array_ref", {})
                    if isinstance(ref, dict) and ref.get("kind") == "symbol_ref":
                        sid = ref.get("symbol_id")
                        if not workspace.symbol_was_discovered(document_id, sid):
                            raise WorkspaceError("SYMBOL_NOT_DISCOVERED", "Discover arrays before using their identities")
                    for field in ("index", "expression"):
                        if field in assignment:
                            _check_discovered_expression(workspace, document_id, assignment[field])


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
            elif method == "list_function_statements":
                document_id = params["document_id"]
                if not workspace.symbol_was_discovered(document_id, params["function_id"]):
                    raise WorkspaceError("SYMBOL_NOT_DISCOVERED", "Discover the function before querying statements")
                result = workspace.protocol_call(method, params)
            elif method == "create_numeric_function":
                document_id = params["document_id"]
                if "expression" in params:
                    _check_discovered_expression(workspace, document_id, params["expression"])
                for local in params.get("locals", []):
                    if isinstance(local, dict) and "expression" in local:
                        _check_discovered_expression(workspace, document_id, local["expression"])
                for assignment in params.get("array_assignments", []):
                    if isinstance(assignment, dict):
                        ref = assignment.get("array_ref", {})
                        if isinstance(ref, dict) and ref.get("kind") == "symbol_ref":
                            sid = ref.get("symbol_id")
                            if not workspace.symbol_was_discovered(document_id, sid):
                                raise WorkspaceError("SYMBOL_NOT_DISCOVERED", "Discover arrays before using their identities")
                        for field in ("index", "expression"):
                            if field in assignment:
                                _check_discovered_expression(workspace, document_id, assignment[field])
                result = workspace.protocol_call(method, params)
            elif method in ("edit_assignment_expression", "insert_numeric_assignment"):
                document_id = params["document_id"]
                operation = {"operation": method, **{k: v for k, v in params.items()
                                                       if k not in ("document_id", "expected_revision")}}
                _check_discovered_operations(workspace, document_id, [operation])
                result = workspace.protocol_call(method, params)
            elif method in ("apply_transaction", "preview_transaction"):
                document_id = params["document_id"]
                _check_discovered_operations(workspace, document_id, params["operations"])
                result = workspace.protocol_call(method, params)
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
