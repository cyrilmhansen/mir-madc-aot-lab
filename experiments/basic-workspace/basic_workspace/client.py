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
        self.metrics = {"requests": 0, "request_bytes": 0, "response_bytes": 0,
                        "wall_ms": 0.0, "methods": {}}

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
                          limit: int = 50) -> dict[str, Any]:
        params = self._doc_params(offset=offset, limit=limit)
        for k, v in (("kind", kind), ("name_query", name_query), ("scope_id", scope_id)):
            if v is not None:
                params[k] = v
        result = self._rpc("list_symbols_page", params)
        for row in result["items"]:
            self._known_symbols.add(row["symbol_id"])
            if row["kind"] == "line_label" and row["name"].isdigit():
                self._known_lines.add(int(row["name"]))
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
        # Re-querying obtains identities valid at the new revision; stable IDs are retained by model.
        return result

    def workspace_diagnostics(self) -> list[dict[str, Any]]:
        return self._rpc("get_diagnostics", self._doc_params())

    def workspace_render(self, max_chars: int | None = None) -> dict[str, Any]:
        text = self._rpc("render_document", self._doc_params())
        limit = self.max_render_chars if max_chars is None else max_chars
        return {"text": text[:limit], "total_chars": len(text), "truncated": len(text) > limit}

    def _doc_params(self, **kwargs: Any) -> dict[str, Any]:
        if not self.document_id:
            raise RpcError("NO_DOCUMENT", "Open a document before querying it")
        return {"document_id": self.document_id, **kwargs}

    def _require_symbol(self, symbol_id: str) -> None:
        if symbol_id not in self._known_symbols:
            raise RpcError("UNKNOWN_SYMBOL_ID", "Discover the symbol through workspace_symbols first")

    def _validate_ops(self, revision: int, operations: list[dict[str, Any]]) -> None:
        if self.revision is None or revision != self.revision:
            raise RpcError("STALE_LOCAL_REVISION", "Refresh workspace state before preview or commit")
        self._validate_operation_symbols(operations)

    def _validate_operation_symbols(self, operations: list[dict[str, Any]]) -> None:
        for op in operations:
            if "symbol_id" in op:
                self._require_symbol(op["symbol_id"])
            if "before_symbol_id" in op and op["before_symbol_id"] is not None:
                self._require_symbol(op["before_symbol_id"])
            if op.get("operation") == "renumber_line" and int(op["old_line"]) not in self._known_lines:
                raise RpcError("UNKNOWN_LINE_LABEL", "Discover the line label through workspace_structure or workspace_symbols first")


TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "workspace_open": {"required": ["text"], "optional": ["uri"]},
    "workspace_structure": {"required": [], "optional": ["offset", "limit"]},
    "workspace_symbols": {"required": [], "optional": ["kind", "name_query", "scope_id", "offset", "limit"]},
    "workspace_references": {"required": ["symbol_id"], "optional": ["offset", "limit"]},
    "workspace_preview": {"required": ["expected_revision", "operations"], "optional": ["include_diff"]},
    "workspace_commit": {"required": ["expected_revision", "operations"], "optional": []},
    "workspace_diagnostics": {"required": [], "optional": []},
    "workspace_render": {"required": [], "optional": ["max_chars"]},
}


class AgentToolAdapter:
    """Small, explicit structured surface intended for an agent tool host."""
    def __init__(self, client: WorkspaceClient):
        self.client = client
        self.observed_revision = client.revision

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
            self.client._validate_operation_symbols(args["operations"])
            result = self.client._rpc("apply_transaction", self.client._doc_params(
                expected_revision=expected, operations=args["operations"]))
            self.client.revision = result["revision"]
            self.observed_revision = result["revision"]
            return result
        if name == "workspace_preview":
            expected = args["expected_revision"]
            if self.observed_revision is None or expected != self.observed_revision:
                raise RpcError("STALE_LOCAL_REVISION", "Transaction does not match this agent's observed revision")
            self.client._validate_operation_symbols(args["operations"])
            return self.client._rpc("preview_transaction", self.client._doc_params(**args))
        result = getattr(self.client, name)(**args)
        if name == "workspace_open":
            self.observed_revision = result["revision"]
        elif name == "workspace_structure":
            self.observed_revision = result["revision"]
        return result
