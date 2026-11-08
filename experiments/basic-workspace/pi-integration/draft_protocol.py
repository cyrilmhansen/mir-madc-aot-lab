"""Small mission-scoped typed draft builder; never edits the canonical Workspace."""
from __future__ import annotations

import copy
import math
import re
import uuid
from dataclasses import dataclass, field
from typing import Any


OPERATORS = {"+", "-", "*", "/", "=", "<>", "<", "<=", ">", ">="}
HANDLE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,47}$")
MAX_BATCH = 16
MAX_OPS = 128


class DraftError(Exception):
    def __init__(self, code: str, message: str, *, op_id: str | None = None,
                 path: str | None = None, expected: Any = None, received: Any = None):
        super().__init__(message)
        self.code, self.op_id, self.path = code, op_id, path
        self.expected, self.received = expected, received

    def diagnostic(self, draft_revision: int, *, changed: bool = False) -> dict[str, Any]:
        result = {"ok": False, "code": self.code, "message": str(self),
                  "draft_revision": draft_revision, "draft_changed": changed,
                  "authoritative_workspace_changed": False}
        if self.op_id is not None: result["operation_id"] = self.op_id
        if self.path is not None: result["path"] = self.path
        if self.expected is not None: result["expected"] = self.expected
        if self.received is not None: result["received"] = self.received
        return result


@dataclass
class Draft:
    draft_id: str
    mission_id: str
    base_revision: int
    name: str
    parameters: list[str]
    callee_handle: str
    revision: int = 0
    nodes: dict[str, dict[str, Any]] = field(default_factory=dict)
    blocks: dict[str, list[str]] = field(default_factory=lambda: {"root": []})
    statements: dict[str, dict[str, Any]] = field(default_factory=dict)
    operation_ids: set[str] = field(default_factory=set)
    history: list[dict[str, Any]] = field(default_factory=list)
    accepted_preview: dict[str, Any] | None = None
    committed: bool = False

    @property
    def handles(self) -> set[str]:
        return set(self.nodes) | set(self.blocks) | set(self.statements)

    def snapshot(self) -> dict[str, Any]:
        return copy.deepcopy(self.__dict__)


class DraftProtocol:
    """Build typed expression/statement graphs with atomic, revisioned batches."""
    def __init__(self) -> None:
        self.drafts: dict[str, Draft] = {}

    def begin(self, *, mission_id: str, base_revision: int, name: str,
              parameters: list[str], callee_handle: str,
              allowed_name: str, allowed_parameters: list[str],
              allowed_callee_handle: str) -> dict[str, Any]:
        if not isinstance(base_revision, int) or base_revision < 0:
            raise DraftError("INVALID_BASE_REVISION", "base_revision must be a non-negative integer")
        if not isinstance(name, str) or name != allowed_name:
            raise DraftError("MISSION_SCOPE_DENIED", "Function name is outside the mission's permitted scope")
        if parameters != allowed_parameters:
            raise DraftError("INVALID_SIGNATURE", "Function signature is outside the mission's permitted scope")
        if callee_handle != allowed_callee_handle:
            raise DraftError("UNKNOWN_PORTABLE_FUNCTION", "The draft must call the permitted discovered function handle",
                             path="callee_handle", expected=allowed_callee_handle, received=callee_handle)
        draft_id = "draft_" + uuid.uuid4().hex
        draft = Draft(draft_id, mission_id, base_revision, name, list(parameters), callee_handle)
        self.drafts[draft_id] = draft
        return {"ok": True, "draft_id": draft_id, "draft_revision": 0,
                "base_revision": base_revision, "mission_id": mission_id,
                "root_block": "root", "authoritative_workspace_changed": False}

    def get(self, draft_id: str) -> Draft:
        draft = self.drafts.get(draft_id)
        if draft is None: raise DraftError("DRAFT_NOT_FOUND", "Unknown draft ID")
        return draft

    @staticmethod
    def _handle(draft: Draft, value: Any, op_id: str, path: str) -> str:
        if not isinstance(value, str) or not HANDLE.fullmatch(value):
            raise DraftError("INVALID_DRAFT_HANDLE", "Handle must be a short portable draft-local identifier",
                             op_id=op_id, path=path, expected="handle string", received=value)
        if value in draft.handles:
            raise DraftError("DUPLICATE_DRAFT_HANDLE", "Draft handle already exists",
                             op_id=op_id, path=path, expected="unused handle", received=value)
        return value

    @staticmethod
    def _expr(draft: Draft, handle: Any, op_id: str, path: str) -> dict[str, Any]:
        if not isinstance(handle, str) or handle not in draft.nodes:
            if isinstance(handle, str) and handle in draft.blocks | draft.statements:
                raise DraftError("DRAFT_TYPE_ERROR", "Handle refers to a statement or block, not a numeric expression",
                                 op_id=op_id, path=path, expected="numeric expression handle", received="block or statement handle")
            raise DraftError("UNKNOWN_EXPRESSION_HANDLE", "Expression handle must refer to an earlier draft node",
                             op_id=op_id, path=path, expected="earlier numeric expression handle", received=handle)
        node = draft.nodes[handle]
        return {k: copy.deepcopy(v) for k, v in node.items() if k != "node_type"}

    def _apply_one(self, draft: Draft, operation: Any) -> dict[str, Any]:
        if not isinstance(operation, dict):
            raise DraftError("INVALID_DRAFT_OPERATION", "Operation must be an object", path="operation", expected="object", received=type(operation).__name__)
        op_id, kind = operation.get("op_id"), operation.get("kind")
        if not isinstance(op_id, str) or not HANDLE.fullmatch(op_id):
            raise DraftError("INVALID_OPERATION_ID", "Every draft operation needs a valid op_id", path="op_id", expected="string", received=op_id)
        if op_id in draft.operation_ids:
            raise DraftError("DUPLICATE_OPERATION_ID", "Operation ID has already been used in this draft", op_id=op_id, path="op_id", expected="unique", received=op_id)
        fields: dict[str, set[str]] = {
            "define_number": {"op_id", "kind", "handle", "value"},
            "define_parameter_ref": {"op_id", "kind", "handle", "name"},
            "define_function_call": {"op_id", "kind", "handle", "function_handle", "arguments"},
            "define_unary_expression": {"op_id", "kind", "handle", "operator", "operand"},
            "define_binary_expression": {"op_id", "kind", "handle", "operator", "left", "right"},
            "append_result_assignment": {"op_id", "kind", "handle", "block", "expression"},
            "append_if_block": {"op_id", "kind", "handle", "block", "condition", "then_block", "else_block"},
        }
        if kind not in fields:
            raise DraftError("UNSUPPORTED_DRAFT_OPERATION", "Unsupported draft operation kind", op_id=op_id, path="kind", expected=sorted(fields), received=kind)
        if set(operation) != fields[kind]:
            raise DraftError("INVALID_DRAFT_OPERATION", "Operation fields do not match its kind", op_id=op_id,
                             path="operation", expected=sorted(fields[kind]), received=sorted(operation))
        result: dict[str, Any] = {"op_id": op_id, "kind": kind}
        if kind == "define_number":
            handle = self._handle(draft, operation["handle"], op_id, "handle")
            value = operation["value"]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise DraftError("DRAFT_TYPE_ERROR", "Numeric literal must be finite", op_id=op_id, path="value", expected="finite number", received=value)
            draft.nodes[handle] = {"node_type": "numeric", "kind": "number", "value": float(value)}
            result["created_handle"] = handle
        elif kind == "define_parameter_ref":
            handle = self._handle(draft, operation["handle"], op_id, "handle")
            name = operation["name"]
            if name not in draft.parameters:
                raise DraftError("UNKNOWN_PARAMETER", "Parameter reference is outside the draft function signature", op_id=op_id, path="name", expected=draft.parameters, received=name)
            draft.nodes[handle] = {"node_type": "numeric", "kind": "local_ref", "name": name}
            result["created_handle"] = handle
        elif kind == "define_function_call":
            handle = self._handle(draft, operation["handle"], op_id, "handle")
            target, args = operation["function_handle"], operation["arguments"]
            if target != draft.callee_handle:
                raise DraftError("UNKNOWN_PORTABLE_FUNCTION", "Call target must be the discovered function handle", op_id=op_id, path="function_handle", expected=draft.callee_handle, received=target)
            if not isinstance(args, list) or len(args) != 1:
                raise DraftError("ARITY_MISMATCH", "AGE_BY_ID takes exactly one argument", op_id=op_id, path="arguments", expected=1, received=len(args) if isinstance(args, list) else type(args).__name__)
            arg = self._expr(draft, args[0], op_id, "arguments[0]")
            draft.nodes[handle] = {"node_type": "numeric", "kind": "call", "function_handle": target, "arguments": [arg]}
            result["created_handle"] = handle
        elif kind == "define_binary_expression":
            handle = self._handle(draft, operation["handle"], op_id, "handle")
            if operation["operator"] not in OPERATORS:
                raise DraftError("INVALID_OPERATOR", "Operator is not in the supported numeric subset", op_id=op_id, path="operator", expected=sorted(OPERATORS), received=operation["operator"])
            left = self._expr(draft, operation["left"], op_id, "left")
            right = self._expr(draft, operation["right"], op_id, "right")
            draft.nodes[handle] = {"node_type": "numeric", "kind": "binary", "operator": operation["operator"], "left": left, "right": right}
            result["created_handle"] = handle
        elif kind == "define_unary_expression":
            handle = self._handle(draft, operation["handle"], op_id, "handle")
            if operation["operator"] not in ("+", "-"):
                raise DraftError("INVALID_OPERATOR", "Unary operator must be + or -", op_id=op_id, path="operator", expected=["+", "-"], received=operation["operator"])
            operand = self._expr(draft, operation["operand"], op_id, "operand")
            draft.nodes[handle] = {"node_type": "numeric", "kind": "unary", "operator": operation["operator"], "operand": operand}
            result["created_handle"] = handle
        elif kind == "append_result_assignment":
            handle = self._handle(draft, operation["handle"], op_id, "handle")
            block, expr = operation["block"], operation["expression"]
            if block not in draft.blocks:
                raise DraftError("INVALID_PARENT_BLOCK", "Parent block does not exist", op_id=op_id, path="block", expected=sorted(draft.blocks), received=block)
            expression = self._expr(draft, expr, op_id, "expression")
            statement = {"statement_type": "assignment", "handle": handle, "expression": expression}
            draft.statements[handle] = statement; draft.blocks[block].append(handle)
            result["created_handle"] = handle
        elif kind == "append_if_block":
            handle = self._handle(draft, operation["handle"], op_id, "handle")
            block, condition = operation["block"], operation["condition"]
            if block not in draft.blocks:
                raise DraftError("INVALID_PARENT_BLOCK", "Parent block does not exist", op_id=op_id, path="block", expected=sorted(draft.blocks), received=block)
            then_block = self._handle(draft, operation["then_block"], op_id, "then_block")
            else_block = self._handle(draft, operation["else_block"], op_id, "else_block")
            if then_block == else_block: raise DraftError("DUPLICATE_DRAFT_HANDLE", "IF branches require distinct block handles", op_id=op_id, path="else_block", expected="distinct handle", received=else_block)
            expression = self._expr(draft, condition, op_id, "condition")
            draft.blocks[then_block] = []; draft.blocks[else_block] = []
            draft.statements[handle] = {"statement_type": "if", "handle": handle, "condition": expression,
                                        "then_block": then_block, "else_block": else_block}
            draft.blocks[block].append(handle)
            result.update({"created_handle": handle, "then_block": then_block, "else_block": else_block})
        draft.operation_ids.add(op_id)
        draft.history.append(copy.deepcopy(operation))
        return result

    def apply_batch(self, draft_id: str, expected_revision: int, operations: Any) -> dict[str, Any]:
        draft = self.get(draft_id)
        if draft.committed:
            return DraftError("DRAFT_ALREADY_COMMITTED", "Draft cannot be changed after commit").diagnostic(draft.revision)
        if expected_revision != draft.revision:
            return DraftError("STALE_DRAFT_REVISION", "Draft revision does not match", expected=expected_revision, received=draft.revision).diagnostic(draft.revision)
        if not isinstance(operations, list) or not operations or len(operations) > MAX_BATCH:
            return DraftError("INVALID_BATCH_SIZE", f"Batch must contain 1..{MAX_BATCH} operations", expected=f"1..{MAX_BATCH}", received=len(operations) if isinstance(operations, list) else type(operations).__name__).diagnostic(draft.revision)
        if len(draft.history) + len(operations) > MAX_OPS:
            return DraftError("DRAFT_OPERATION_LIMIT", "Draft operation history limit exceeded", expected=MAX_OPS).diagnostic(draft.revision)
        staged = copy.deepcopy(draft); results = []; progress = []
        for index, operation in enumerate(operations):
            try:
                result=self._apply_one(staged, operation); results.append(result); staged.revision+=1
                progress.append({"draft_revision":staged.revision,"operation_id":result["op_id"],
                    "operation_kind":result["kind"],
                    "created_handles":[result[k] for k in ("created_handle","then_block","else_block") if k in result],
                    "request":self.request_from_draft(staged,allow_empty=True)})
            except DraftError as exc:
                exc.path = f"operations[{index}]" + (f".{exc.path}" if exc.path else "")
                return exc.diagnostic(draft.revision)
        staged.accepted_preview = None
        self.drafts[draft_id] = staged
        return {"ok": True, "draft_id": draft_id, "base_revision": staged.base_revision,
                "draft_revision": staged.revision, "operations_applied": len(operations),
                "operation_results": results, "_progress_states":progress,
                "authoritative_workspace_changed": False}

    def inspect(self, draft_id: str) -> dict[str, Any]:
        d = self.get(draft_id)
        return {"ok": True, "draft_id": d.draft_id, "mission_id": d.mission_id,
                "base_revision": d.base_revision, "draft_revision": d.revision,
                "function": {"name": d.name, "parameters": d.parameters, "callee_handle": d.callee_handle},
                "expression_handles": sorted(d.nodes), "block_handles": sorted(d.blocks),
                "statement_handles": sorted(d.statements), "operation_count": len(d.history),
                "preview_accepted": bool(d.accepted_preview), "committed": d.committed,
                "authoritative_workspace_changed": False}

    def function_request(self, draft_id: str, *, allow_empty: bool = False) -> dict[str, Any]:
        return self.request_from_draft(self.get(draft_id),allow_empty=allow_empty)

    @staticmethod
    def request_from_draft(d: Draft, *, allow_empty: bool = False) -> dict[str, Any]:
        if not d.blocks["root"] and not allow_empty:
            raise DraftError("EMPTY_DRAFT_BODY", "Draft function body is empty")
        def render_block(handle: str, depth: int = 0) -> list[dict[str, Any]]:
            if depth > 2: raise DraftError("DRAFT_NESTING_LIMIT", "IF nesting exceeds the supported level")
            out=[]
            for stmt_id in d.blocks[handle]:
                s=d.statements[stmt_id]
                if s["statement_type"] == "assignment":
                    out.append({"kind":"assign","target":{"kind":"result"},"expression":copy.deepcopy(s["expression"])})
                else:
                    out.append({"kind":"if","condition":copy.deepcopy(s["condition"]),
                                "then":render_block(s["then_block"],depth+1),
                                "else":render_block(s["else_block"],depth+1)})
            return out
        return {"name":d.name,"parameters":list(d.parameters),"body":render_block("root")}

    def operation_history(self, draft_id: str) -> list[dict[str, Any]]:
        return copy.deepcopy(self.get(draft_id).history)
