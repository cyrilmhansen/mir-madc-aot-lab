"""Bounded agent client for the line-oriented BASIC Workspace JSON-RPC service."""
from __future__ import annotations

from collections import deque
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
from typing import Any


class RpcError(RuntimeError):
    def __init__(self, code: str | int, message: str, details: Any = None):
        super().__init__(message)
        self.code, self.message, self.details = code, message, details


class WorkspaceClient:
    """One persistent server process; edits are only semantic JSON-RPC calls."""
    def __init__(self, timeout: float = 5.0, max_render_chars: int = 12000):
        self.timeout = timeout
        self.max_render_chars = max_render_chars
        self.proc: subprocess.Popen[str] | None = None
        self._responses: queue.Queue[dict[str, Any] | BaseException] = queue.Queue(maxsize=128)
        self._next_id = 0
        self._lock = threading.Lock()
        self._stderr: deque[str] = deque(maxlen=40)
        self.document_id: str | None = None
        self.revision: int | None = None
        self._known_symbols: set[str] = set()
        self._known_lines: set[int] = set()
        self._known_statements: set[str] = set()
        self.metrics = {"requests": 0, "request_bytes": 0, "response_bytes": 0,
                        "response_bytes_by_method": {}, "wall_ms": 0.0, "methods": {}}

    def start(self) -> "WorkspaceClient":
        if self.proc is not None:
            return self
        root = Path(__file__).resolve().parents[1]
        env = os.environ.copy()
        env["PYTHONPATH"] = str(root) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        self.proc = subprocess.Popen([sys.executable, "-m", "basic_workspace.server"], cwd=root,
                                     env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, text=True, encoding="utf-8", bufsize=1)
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()
        return self

    def _read_stdout(self) -> None:
        assert self.proc and self.proc.stdout
        try:
            for line in self.proc.stdout:
                try:
                    self._responses.put(json.loads(line), timeout=self.timeout)
                except queue.Full:
                    try:
                        self._responses.put_nowait(RpcError("RESPONSE_QUEUE_FULL", "Too many unconsumed service responses"))
                    except queue.Full:
                        pass
                    return
        except BaseException as exc:
            try:
                self._responses.put_nowait(exc)
            except queue.Full:
                pass

    def _read_stderr(self) -> None:
        assert self.proc and self.proc.stderr
        for line in self.proc.stderr:
            self._stderr.append(line[:1000].rstrip())

    def close(self) -> None:
        proc, self.proc = self.proc, None
        if not proc:
            return
        if proc.stdin:
            proc.stdin.close()
        try:
            proc.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                proc.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        for stream in (proc.stdout, proc.stderr):
            if stream:
                stream.close()

    def __enter__(self) -> "WorkspaceClient":
        return self.start()

    def __exit__(self, *_: Any) -> None:
        self.close()

    def _rpc(self, method: str, params: dict[str, Any] | None = None) -> Any:
        self.start()
        with self._lock:
            assert self.proc and self.proc.stdin
            self._next_id += 1
            req = {"jsonrpc": "2.0", "id": self._next_id, "method": method, "params": params or {}}
            encoded = json.dumps(req, separators=(",", ":"), ensure_ascii=False)
            started = time.perf_counter()
            self.metrics["requests"] += 1
            self.metrics["request_bytes"] += len(encoded.encode("utf-8"))
            counts = self.metrics["methods"]
            counts[method] = counts.get(method, 0) + 1
            self.proc.stdin.write(encoded + "\n")
            self.proc.stdin.flush()
            try:
                response = self._responses.get(timeout=self.timeout)
            except queue.Empty as exc:
                self.close()  # discard a late response so it cannot poison the next request ID
                raise RpcError("TIMEOUT", f"Workspace request {method} exceeded {self.timeout}s",
                               {"stderr_tail": list(self._stderr)}) from exc
            self.metrics["wall_ms"] += (time.perf_counter() - started) * 1000
            if isinstance(response, BaseException):
                raise RpcError("PROCESS_IO", str(response), {"stderr_tail": list(self._stderr)})
            raw = json.dumps(response, separators=(",", ":"), ensure_ascii=False)
            self.metrics["response_bytes"] += len(raw.encode("utf-8"))
            by_method = self.metrics["response_bytes_by_method"]
            by_method[method] = by_method.get(method, 0) + len(raw.encode("utf-8"))
            if response.get("id") != self._next_id:
                raise RpcError("RESPONSE_ID_MISMATCH", "JSON-RPC response ID did not match request")
            if "error" in response:
                err = response["error"]
                details = err.get("data")
                code = details.get("code", err.get("code")) if isinstance(details, dict) else err.get("code")
                raise RpcError(code, err.get("message", "Workspace request failed"), details)
            return response.get("result")

    def workspace_open(self, text: str, uri: str | None = None) -> dict[str, Any]:
        result = self._rpc("open_document_from_string", {"text": text, "uri": uri})
        self.document_id, self.revision = result["document_id"], result["revision"]
        self._known_symbols.clear()
        self._known_lines.clear()
        self._known_statements.clear()
        return result

    def workspace_create_empty(self, uri: str | None = None) -> dict[str, Any]:
        result = self._rpc("create_empty_document", {"uri": uri})
        self.document_id, self.revision = result["document_id"], result["revision"]
        self._known_symbols.clear()
        self._known_lines.clear()
        self._known_statements.clear()
        return result

    def workspace_structure(self, offset: int = 0, limit: int = 50) -> dict[str, Any]:
        result = self._rpc("get_document_structure_page", self._doc_params(offset=offset, limit=limit))
        self.revision = result["revision"]
        for row in result["functions"] + result["line_labels"]:
            if row.get("symbol_id"):
                self._known_symbols.add(row["symbol_id"])
        self._known_lines.update(int(row["line"]) for row in result["line_labels"])
        return result

    def workspace_symbols(self, kind: str | None = None, name_query: str | None = None,
                          scope_id: str | None = None, offset: int = 0,
                          limit: int = 50, exact_name: str | None = None,
                          unique: bool = False) -> dict[str, Any]:
        params = self._doc_params(offset=offset, limit=limit)
        for k, v in (("kind", kind), ("name_query", name_query), ("scope_id", scope_id),
                     ("exact_name", exact_name), ("unique", unique)):
            if v is not None:
                params[k] = v
        result = self._rpc("list_symbols_page", params)
        for row in result["items"]:
            self._known_symbols.add(row["symbol_id"])
            if row["kind"] == "line_label" and row["name"].isdigit():
                self._known_lines.add(int(row["name"]))
        if result.get("unique_symbol"):
            row = result["unique_symbol"]
            self._known_symbols.add(row["symbol_id"])
            if row["kind"] == "line_label" and row["name"].isdigit():
                self._known_lines.add(int(row["name"]))
        if "revision" in result:
            self.revision = result["revision"]
        return result

    def workspace_statements(self, function_id: str, offset: int = 0,
                             limit: int = 50) -> dict[str, Any]:
        self._require_symbol(function_id)
        result = self._rpc("list_function_statements", self._doc_params(
            function_id=function_id, offset=offset, limit=limit))
        self.revision = result["revision"]
        for row in result["items"]:
            self._known_statements.add(row["statement_id"])
            self._known_symbols.add(row["target_symbol_id"])
            self._known_symbols.update(row["referenced_symbol_ids"])
        return result

    def workspace_references(self, symbol_id: str, offset: int = 0, limit: int = 100) -> dict[str, Any]:
        self._require_symbol(symbol_id)
        return self._rpc("find_references_page", self._doc_params(symbol_id=symbol_id,
                                                                   offset=offset, limit=limit))

    def workspace_preview(self, expected_revision: int, operations: list[dict[str, Any]],
                          include_diff: bool = False) -> dict[str, Any]:
        self._validate_ops(expected_revision, operations)
        return self._rpc("preview_transaction", self._doc_params(expected_revision=expected_revision,
                                                                   operations=operations,
                                                                   include_diff=include_diff))

    def workspace_commit(self, expected_revision: int, operations: list[dict[str, Any]]) -> dict[str, Any]:
        self._validate_ops(expected_revision, operations)
        result = self._rpc("apply_transaction", self._doc_params(expected_revision=expected_revision,
                                                                   operations=operations))
        self.revision = result["revision"]
        self._remember_created(result)
        # Re-querying obtains identities valid at the new revision; stable IDs are retained by model.
        return result

    def workspace_create_function(self, expected_revision: int, name: str,
                                  parameters: list[str], expression: Any = None,
                                  locals: list[dict[str, Any]] | None = None,
                                  arrays: list[dict[str, Any]] | None = None,
                                  array_assignments: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        self._check_expected_revision(expected_revision)
        if expression is not None:
            self._validate_expression_symbols(expression, allow_local_ref=True)
        for local in locals or []:
            if isinstance(local, dict) and "expression" in local:
                self._validate_expression_symbols(local["expression"], allow_local_ref=True)
        for assignment in array_assignments or []:
            if isinstance(assignment, dict):
                self._validate_array_reference(assignment.get("array_ref"), True)
                for field in ("index", "expression"):
                    if field in assignment:
                        self._validate_expression_symbols(assignment[field], allow_local_ref=True)
        params = {"expected_revision": expected_revision, "name": name,
                  "parameters": parameters}
        if expression is not None:
            params["expression"] = expression
        if locals is not None:
            params["locals"] = locals
        if arrays is not None:
            params["arrays"] = arrays
        if array_assignments is not None:
            params["array_assignments"] = array_assignments
        result = self._rpc("create_numeric_function", self._doc_params(**params))
        self.revision = result["revision"]
        self._remember_created(result)
        return result

    def workspace_edit_expression(self, expected_revision: int, statement_id: str,
                                  expression: dict[str, Any]) -> dict[str, Any]:
        self._check_expected_revision(expected_revision)
        if statement_id not in self._known_statements:
            raise RpcError("UNKNOWN_STATEMENT_ID", "Discover the assignment through workspace_statements first")
        self._validate_expression_symbols(expression)
        result = self._rpc("edit_assignment_expression", self._doc_params(
            expected_revision=expected_revision, statement_id=statement_id,
            expression=expression))
        self.revision = result["revision"]
        self._remember_created(result)
        return result

    def workspace_insert_assignment(self, expected_revision: int, function_id: str,
                                    target: dict[str, Any], expression: dict[str, Any],
                                    before_statement_id: str | None = None) -> dict[str, Any]:
        self._check_expected_revision(expected_revision)
        self._require_symbol(function_id)
        if before_statement_id is not None and before_statement_id not in self._known_statements:
            raise RpcError("UNKNOWN_STATEMENT_ID", "Discover the insertion point through workspace_statements first")
        self._validate_expression_symbols(expression)
        params = self._doc_params(expected_revision=expected_revision, function_id=function_id,
                                  target=target, expression=expression)
        if before_statement_id is not None:
            params["before_statement_id"] = before_statement_id
        result = self._rpc("insert_numeric_assignment", params)
        self.revision = result["revision"]
        self._remember_created(result)
        return result

    def workspace_diagnostics(self) -> list[dict[str, Any]]:
        return self._rpc("get_diagnostics", self._doc_params())

    def workspace_render(self, max_chars: int | None = None) -> dict[str, Any]:
        text = self._rpc("render_document", self._doc_params())
        limit = self.max_render_chars if max_chars is None else max_chars
        return {"text": text[:limit], "total_chars": len(text), "truncated": len(text) > limit}

    def workspace_execute_function(self, expected_revision: int, function_id: str,
                                   arguments: list[Any], engine: str = "interp") -> dict[str, Any]:
        self._require_symbol(function_id)
        return self._rpc("execute_function", self._doc_params(
            expected_revision=expected_revision, function_id=function_id,
            arguments=arguments, engine=engine))

    def _doc_params(self, **kwargs: Any) -> dict[str, Any]:
        if not self.document_id:
            raise RpcError("NO_DOCUMENT", "Open a document before querying it")
        return {"document_id": self.document_id, **kwargs}

    def _require_symbol(self, symbol_id: str) -> None:
        if symbol_id not in self._known_symbols:
            raise RpcError("UNKNOWN_SYMBOL_ID", "Discover the symbol through workspace_symbols first")

    def _validate_ops(self, revision: int, operations: list[dict[str, Any]]) -> None:
        self._check_expected_revision(revision)
        self._validate_operation_symbols(operations)

    def _check_expected_revision(self, revision: int) -> None:
        if self.revision is None or revision != self.revision:
            raise RpcError("STALE_LOCAL_REVISION", "Refresh workspace state before preview or commit")

    def _validate_operation_symbols(self, operations: list[dict[str, Any]]) -> None:
        for op in operations:
            if "symbol_id" in op:
                self._require_symbol(op["symbol_id"])
            if "before_symbol_id" in op and op["before_symbol_id"] is not None:
                self._require_symbol(op["before_symbol_id"])
            if op.get("operation") == "renumber_line" and int(op["old_line"]) not in self._known_lines:
                raise RpcError("UNKNOWN_LINE_LABEL", "Discover the line label through workspace_structure or workspace_symbols first")
            if op.get("operation") == "edit_assignment_expression" and op.get("statement_id") not in self._known_statements:
                raise RpcError("UNKNOWN_STATEMENT_ID", "Discover the assignment through workspace_statements first")
            if op.get("operation") == "insert_numeric_assignment":
                if op.get("function_id") not in self._known_symbols:
                    raise RpcError("UNKNOWN_SYMBOL_ID", "Discover the function before inserting an assignment")
                before = op.get("before_statement_id")
                if before is not None and before not in self._known_statements:
                    raise RpcError("UNKNOWN_STATEMENT_ID", "Discover the insertion point first")
            if "expression" in op:
                self._validate_expression_symbols(op["expression"],
                    allow_local_ref=op.get("operation") == "create_numeric_function")
            if op.get("operation") == "create_numeric_function":
                for local in op.get("locals", []):
                    if isinstance(local, dict) and "expression" in local:
                        self._validate_expression_symbols(local["expression"], allow_local_ref=True)
                for assignment in op.get("array_assignments", []):
                    if isinstance(assignment, dict):
                        self._validate_array_reference(assignment.get("array_ref"), True)
                        for field in ("index", "expression"):
                            if field in assignment:
                                self._validate_expression_symbols(assignment[field], allow_local_ref=True)

    def _validate_expression_symbols(self, expression: Any, allow_local_ref: bool = False) -> None:
        if not isinstance(expression, dict):
            raise RpcError("INVALID_EXPRESSION", "Expression must be a typed object")
        kind = expression.get("kind")
        if kind == "symbol_ref":
            if expression.get("symbol_id") not in self._known_symbols:
                raise RpcError("UNKNOWN_SYMBOL_ID", "Discover expression symbols before using their identities")
        elif kind == "call":
            if expression.get("function_id") not in self._known_symbols:
                raise RpcError("UNKNOWN_SYMBOL_ID", "Discover called functions before using their identities")
            for child in expression.get("arguments", []):
                self._validate_expression_symbols(child, allow_local_ref)
        elif kind == "unary":
            self._validate_expression_symbols(expression.get("operand"), allow_local_ref)
        elif kind == "binary":
            self._validate_expression_symbols(expression.get("left"), allow_local_ref)
            self._validate_expression_symbols(expression.get("right"), allow_local_ref)
        elif kind == "array_element":
            if set(expression) != {"kind", "array_ref", "index"}:
                raise RpcError("INVALID_EXPRESSION", "array_element requires array_ref and index")
            self._validate_array_reference(expression.get("array_ref"), allow_local_ref)
            self._validate_expression_symbols(expression.get("index"), allow_local_ref)
        elif kind == "local_ref" and allow_local_ref:
            if not isinstance(expression.get("name"), str):
                raise RpcError("INVALID_TRANSACTION_HANDLE", "local_ref requires a name")
        elif kind != "number":
            raise RpcError("UNSUPPORTED_EXPRESSION", f"Unknown typed expression kind {kind!r}")

    def _validate_array_reference(self, reference: Any, allow_local_ref: bool = False) -> None:
        if not isinstance(reference, dict):
            raise RpcError("INVALID_ARRAY_REFERENCE", "array_ref must be a typed reference")
        if reference.get("kind") == "symbol_ref" and set(reference) == {"kind", "symbol_id"}:
            if reference["symbol_id"] not in self._known_symbols:
                raise RpcError("UNKNOWN_SYMBOL_ID", "Discover arrays before using their identities")
            return
        if (allow_local_ref and reference.get("kind") == "local_ref"
                and set(reference) == {"kind", "name"} and isinstance(reference.get("name"), str)):
            return
        raise RpcError("INVALID_ARRAY_REFERENCE", "Use a discovered array ID or constructor-local name")

    def _remember_created(self, result: dict[str, Any]) -> None:
        self._known_symbols.update(x["symbol_id"] for x in result.get("created_entities", []))
        self._known_statements.update(x["statement_id"] for x in result.get("created_statements", []))
        self._known_statements.update(result.get("affected_statement_ids", []))


TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "workspace_create_empty": {"required": [], "optional": ["uri"]},
    "workspace_open": {"required": ["text"], "optional": ["uri"]},
    "workspace_structure": {"required": [], "optional": ["offset", "limit"]},
    "workspace_symbols": {"required": [], "optional": ["kind", "name_query", "exact_name", "unique", "scope_id", "offset", "limit"]},
    "workspace_references": {"required": ["symbol_id"], "optional": ["offset", "limit"]},
    "workspace_preview": {"required": ["expected_revision", "operations"], "optional": ["include_diff"]},
    "workspace_commit": {"required": ["expected_revision", "operations"], "optional": []},
    "workspace_diagnostics": {"required": [], "optional": []},
    "workspace_render": {"required": [], "optional": ["max_chars"]},
    "workspace_execute_function": {"required": ["expected_revision", "function_id", "arguments"],
                                   "optional": ["engine"]},
    "workspace_create_function": {"required": ["expected_revision", "name", "parameters"],
                                   "optional": ["expression", "locals", "arrays", "array_assignments"]},
    "workspace_statements": {"required": ["function_id"], "optional": ["offset", "limit"]},
    "workspace_edit_expression": {"required": ["expected_revision", "statement_id", "expression"], "optional": []},
    "workspace_insert_assignment": {"required": ["expected_revision", "function_id", "target", "expression"],
                                    "optional": ["before_statement_id"]},
}


class AgentToolAdapter:
    """Small, explicit structured surface intended for an agent tool host."""
    def __init__(self, client: WorkspaceClient):
        self.client = client
        self.observed_revision = client.revision
        self.known_symbols: set[str] = set()
        self.known_lines: set[int] = set()
        self.known_statements: set[str] = set()

    def fork(self) -> "AgentToolAdapter":
        """Create another agent view over the same persistent workspace process."""
        other = AgentToolAdapter(self.client)
        other.observed_revision = self.observed_revision
        return other

    def call(self, name: str, args: dict[str, Any]) -> Any:
        schema = TOOL_SCHEMAS.get(name)
        if schema is None:
            raise RpcError("TOOL_NOT_FOUND", f"Unsupported workspace tool {name}")
        allowed = set(schema["required"] + schema["optional"])
        if set(args) - allowed or set(schema["required"]) - set(args):
            raise RpcError("INVALID_TOOL_ARGUMENTS", "Tool arguments do not match the declared schema")
        if name == "workspace_commit":
            expected = args["expected_revision"]
            if self.observed_revision is None or expected != self.observed_revision:
                raise RpcError("STALE_LOCAL_REVISION", "Transaction does not match this agent's observed revision")
            self._validate_discovered_operations(args["operations"])
            self.client._validate_operation_symbols(args["operations"])
            result = self.client._rpc("apply_transaction", self.client._doc_params(
                expected_revision=expected, operations=args["operations"]))
            self.client.revision = result["revision"]
            self.client._remember_created(result)
            self.observed_revision = result["revision"]
            self.known_symbols.update(x["symbol_id"] for x in result.get("created_entities", []))
            self.known_statements.update(x["statement_id"] for x in result.get("created_statements", []))
            self.known_statements.update(result.get("affected_statement_ids", []))
            return result
        if name == "workspace_preview":
            expected = args["expected_revision"]
            if self.observed_revision is None or expected != self.observed_revision:
                raise RpcError("STALE_LOCAL_REVISION", "Transaction does not match this agent's observed revision")
            self._validate_discovered_operations(args["operations"])
            self.client._validate_operation_symbols(args["operations"])
            return self.client._rpc("preview_transaction", self.client._doc_params(**args))
        if name == "workspace_references":
            if args.get("symbol_id") not in self.known_symbols:
                raise RpcError("UNKNOWN_SYMBOL_ID", "This agent must discover the symbol before requesting its references")
        if name == "workspace_execute_function":
            if args.get("function_id") not in self.known_symbols:
                raise RpcError("UNKNOWN_SYMBOL_ID", "This agent must discover the function before executing it")
        if name == "workspace_statements" and args.get("function_id") not in self.known_symbols:
            raise RpcError("UNKNOWN_SYMBOL_ID", "This agent must discover the function before querying its statements")
        if name in ("workspace_create_function", "workspace_edit_expression", "workspace_insert_assignment"):
            if self.observed_revision is None or args["expected_revision"] != self.observed_revision:
                raise RpcError("STALE_LOCAL_REVISION", "Construction request does not match this agent's observed revision")
            if name == "workspace_edit_expression" and args["statement_id"] not in self.known_statements:
                raise RpcError("UNKNOWN_STATEMENT_ID", "Discover the assignment before editing it")
            if name == "workspace_insert_assignment":
                if args["function_id"] not in self.known_symbols:
                    raise RpcError("UNKNOWN_SYMBOL_ID", "Discover the function before inserting an assignment")
                before = args.get("before_statement_id")
                if before is not None and before not in self.known_statements:
                    raise RpcError("UNKNOWN_STATEMENT_ID", "Discover the insertion point first")
            if name == "workspace_create_function":
                if "expression" in args:
                    self._validate_expression_symbols(args["expression"], allow_local_ref=True)
                for local in args.get("locals", []):
                    if isinstance(local, dict) and "expression" in local:
                        self._validate_expression_symbols(local["expression"], allow_local_ref=True)
                for assignment in args.get("array_assignments", []):
                    if isinstance(assignment, dict):
                        self._validate_array_reference(assignment.get("array_ref"), True)
                        for field in ("index", "expression"):
                            if field in assignment:
                                self._validate_expression_symbols(assignment[field], allow_local_ref=True)
            else:
                self._validate_expression_symbols(args["expression"])
        result = getattr(self.client, name)(**args)
        if name in ("workspace_open", "workspace_create_empty"):
            self.observed_revision = result["revision"]
            self.known_symbols.clear()
            self.known_lines.clear()
            self.known_statements.clear()
        elif name == "workspace_structure":
            self.observed_revision = result["revision"]
            self.known_symbols.update(x.get("symbol_id") for x in result["functions"] + result["line_labels"] if x.get("symbol_id"))
            self.known_lines.update(int(x["line"]) for x in result["line_labels"])
        elif name == "workspace_symbols" and "revision" in result:
            self.observed_revision = result["revision"]
        elif name == "workspace_statements":
            self.observed_revision = result["revision"]
            for row in result["items"]:
                self.known_statements.add(row["statement_id"])
                self.known_symbols.add(row["target_symbol_id"])
                self.known_symbols.update(row["referenced_symbol_ids"])
        elif name in ("workspace_create_function", "workspace_edit_expression", "workspace_insert_assignment"):
            self.observed_revision = result["revision"]
            self.known_symbols.update(x["symbol_id"] for x in result.get("created_entities", []))
            self.known_statements.update(x["statement_id"] for x in result.get("created_statements", []))
            self.known_statements.update(result.get("affected_statement_ids", []))
        if name == "workspace_symbols":
            self.known_symbols.update(x["symbol_id"] for x in result.get("items", []))
            symbol = result.get("unique_symbol")
            if symbol:
                self.known_symbols.add(symbol["symbol_id"])
                if symbol["kind"] == "line_label" and symbol["name"].isdigit():
                    self.known_lines.add(int(symbol["name"]))
            for row in result.get("items", []):
                if row["kind"] == "line_label" and row["name"].isdigit():
                    self.known_lines.add(int(row["name"]))
        return result

    def _validate_discovered_operations(self, operations: list[dict[str, Any]]) -> None:
        for operation in operations:
            for key in ("symbol_id", "before_symbol_id"):
                symbol_id = operation.get(key)
                if symbol_id is not None and symbol_id not in self.known_symbols:
                    raise RpcError("UNKNOWN_SYMBOL_ID", "This agent must discover each symbol before editing")
            if (operation.get("operation") == "renumber_line" and
                    int(operation["old_line"]) not in self.known_lines):
                raise RpcError("UNKNOWN_LINE_LABEL", "This agent must discover the line label before renumbering")
            if (operation.get("operation") == "edit_assignment_expression" and
                    operation.get("statement_id") not in self.known_statements):
                raise RpcError("UNKNOWN_STATEMENT_ID", "This agent must discover the assignment before editing it")
            if operation.get("operation") == "insert_numeric_assignment":
                if operation.get("function_id") not in self.known_symbols:
                    raise RpcError("UNKNOWN_SYMBOL_ID", "This agent must discover the containing function")
                before = operation.get("before_statement_id")
                if before is not None and before not in self.known_statements:
                    raise RpcError("UNKNOWN_STATEMENT_ID", "This agent must discover the insertion position")
            if "expression" in operation:
                self._validate_expression_symbols(operation["expression"],
                    allow_local_ref=operation.get("operation") == "create_numeric_function")
            if operation.get("operation") == "create_numeric_function":
                for local in operation.get("locals", []):
                    if isinstance(local, dict) and "expression" in local:
                        self._validate_expression_symbols(local["expression"], True)
                for assignment in operation.get("array_assignments", []):
                    if isinstance(assignment, dict):
                        self._validate_array_reference(assignment.get("array_ref"), True)
                        for field in ("index", "expression"):
                            if field in assignment:
                                self._validate_expression_symbols(assignment[field], True)

    def _validate_expression_symbols(self, expression: Any, allow_local_ref: bool = False) -> None:
        if not isinstance(expression, dict):
            raise RpcError("INVALID_EXPRESSION", "Expression must be a typed object")
        kind = expression.get("kind")
        if kind == "symbol_ref":
            if expression.get("symbol_id") not in self.known_symbols:
                raise RpcError("UNKNOWN_SYMBOL_ID", "This agent must discover expression symbols first")
        elif kind == "call":
            if expression.get("function_id") not in self.known_symbols:
                raise RpcError("UNKNOWN_SYMBOL_ID", "This agent must discover called functions first")
            for child in expression.get("arguments", []):
                self._validate_expression_symbols(child, allow_local_ref)
        elif kind == "unary":
            self._validate_expression_symbols(expression.get("operand"), allow_local_ref)
        elif kind == "binary":
            self._validate_expression_symbols(expression.get("left"), allow_local_ref)
            self._validate_expression_symbols(expression.get("right"), allow_local_ref)
        elif kind == "array_element":
            if set(expression) != {"kind", "array_ref", "index"}:
                raise RpcError("INVALID_EXPRESSION", "array_element requires array_ref and index")
            self._validate_array_reference(expression.get("array_ref"), allow_local_ref)
            self._validate_expression_symbols(expression.get("index"), allow_local_ref)
        elif kind == "local_ref" and allow_local_ref:
            if not isinstance(expression.get("name"), str):
                raise RpcError("INVALID_TRANSACTION_HANDLE", "local_ref requires a name")
        elif kind != "number":
            raise RpcError("UNSUPPORTED_EXPRESSION", f"Unsupported typed expression {kind!r}")

    def _validate_array_reference(self, reference: Any, allow_local_ref: bool = False) -> None:
        if not isinstance(reference, dict):
            raise RpcError("INVALID_ARRAY_REFERENCE", "array_ref must be a typed reference")
        if reference.get("kind") == "symbol_ref" and set(reference) == {"kind", "symbol_id"}:
            if reference["symbol_id"] not in self.known_symbols:
                raise RpcError("UNKNOWN_SYMBOL_ID", "Discover arrays before using their identities")
            return
        if (allow_local_ref and reference.get("kind") == "local_ref"
                and set(reference) == {"kind", "name"} and isinstance(reference.get("name"), str)):
            return
        raise RpcError("INVALID_ARRAY_REFERENCE", "Use a discovered array ID or constructor-local name")
