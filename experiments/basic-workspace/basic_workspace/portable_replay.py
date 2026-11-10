"""Deterministic replay of the bounded portable BASIC constructive metafile.

This module interprets only the six operation families emitted by the
semantic campaigns.  Workspace remains the mutation authority: every replay
step is applied through its revision checked public transaction operations.
Campaign authorization and historical evidence attestation live elsewhere.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Any

from .model import Workspace, WorkspaceError
from .projection import Assignment, ForLoop, IfBlock, build_projection, projection_semantics


SUPPORTED_OPERATIONS = frozenset({
    "create_numeric_function", "edit_numeric_literals", "insert_typed_if_block",
    "rename_symbol", "edit_typed_if_condition", "replace_typed_if_block",
})


@dataclass
class ReplayResult:
    document_id: str
    revision: int
    live_handles: dict[str, str]
    retired_handles: dict[str, dict[str, Any]]
    identity_events: list[dict[str, Any]]
    operation_events: list[dict[str, Any]]

    def evidence(self) -> dict[str, Any]:
        return {
            "schema": "basic-workspace.portable-replay-evidence",
            "version": 1,
            "final_revision": self.revision,
            "live_handles": dict(sorted(self.live_handles.items())),
            "retired_handles": dict(sorted(self.retired_handles.items())),
            "identity_events": self.identity_events,
            "operations": self.operation_events,
        }


def _fingerprint(value: Any) -> str:
    body = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                       allow_nan=False).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


class PortableReplay:
    """Replay portable operations into an empty or caller-supplied Workspace."""

    def __init__(self, workspace: Workspace, document_id: str):
        self.ws, self.doc = workspace, document_id
        self.aliases: dict[str, str] = {}
        self.retired: dict[str, dict[str, Any]] = {}
        self.ever_seen: set[str] = set()
        self.identity_events: list[dict[str, Any]] = []
        self.operation_events: list[dict[str, Any]] = []

    @classmethod
    def replay_constructive_stream(cls, workspace: Workspace, document_id: str,
                                   operations: list[dict[str, Any]], *,
                                   expected_final_handles: list[str] | None = None,
                                   expected_retired_handles: list[str] | None = None,
                                   expected_start_revision: int | None = None) -> ReplayResult:
        runner = cls(workspace, document_id)
        revision = workspace.get_revision(document_id)
        if expected_start_revision is not None and revision != expected_start_revision:
            raise WorkspaceError("REPLAY_START_REVISION", f"Expected revision {expected_start_revision}, got {revision}")
        if not isinstance(operations, list):
            raise WorkspaceError("REPLAY_STREAM_INVALID", "operations must be an ordered array")
        for index, item in enumerate(operations):
            runner.apply_operation(item, index=index)
        revision = workspace.get_revision(document_id)
        if expected_final_handles is not None and sorted(runner.aliases) != sorted(expected_final_handles):
            raise WorkspaceError("REPLAY_HANDLE_LEDGER", "Final live portable handles differ from the stream ledger")
        if expected_retired_handles is not None and sorted(runner.retired) != sorted(expected_retired_handles):
            raise WorkspaceError("REPLAY_RETIREMENT_LEDGER", "Final retired portable handles differ from the stream ledger")
        return ReplayResult(document_id, revision, runner.aliases, runner.retired,
                            runner.identity_events, runner.operation_events)

    def _require_live(self, handle: Any, role: str) -> str:
        if not isinstance(handle, str) or not handle:
            raise WorkspaceError("REPLAY_HANDLE_INVALID", f"{role} must be a portable handle")
        if handle in self.retired:
            raise WorkspaceError("REPLAY_HANDLE_RETIRED", f"{role} refers to retired handle {handle!r}")
        value = self.aliases.get(handle)
        if value is None:
            raise WorkspaceError("REPLAY_HANDLE_MISSING", f"{role} refers to unknown or not-yet-created handle {handle!r}")
        return value

    def _fresh_handle(self, handle: Any, role: str) -> str:
        if not isinstance(handle, str) or not handle:
            raise WorkspaceError("REPLAY_HANDLE_INVALID", f"{role} must be a portable handle")
        if handle in self.ever_seen:
            raise WorkspaceError("REPLAY_IDENTITY_REUSE", f"Portable handle {handle!r} has already been used")
        return handle

    def _symbol_ref(self, function_id: str, name: str) -> dict[str, Any]:
        fn = next((row for row in self.ws.documents[self.doc].functions if row["symbol_id"] == function_id), None)
        if fn is None:
            raise WorkspaceError("REPLAY_FUNCTION_MISSING", "Typed expression owner function is missing")
        symbols = self.ws.documents[self.doc].symbols
        matches = [sid for sid in fn["parameters"] if symbols[sid].name.casefold() == str(name).casefold()]
        if len(matches) != 1:
            raise WorkspaceError("REPLAY_PARAMETER_MISSING", f"Local parameter {name!r} is unresolved or ambiguous")
        return {"kind": "symbol_ref", "symbol_id": matches[0]}

    def _expr(self, value: Any, function_id: str) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise WorkspaceError("REPLAY_TYPED_SHAPE", "Portable expression must be an object")
        kind = value.get("kind")
        if kind == "number" and set(value) == {"kind", "value"}:
            number = value["value"]
            if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(float(number)):
                raise WorkspaceError("REPLAY_TYPED_SHAPE", "Portable numeric literal must be finite")
            return {"kind": "number", "value": number}
        if kind == "local_ref" and set(value) == {"kind", "name"}:
            return self._symbol_ref(function_id, value["name"])
        if kind == "call" and set(value) == {"kind", "function_handle", "arguments"}:
            callee = self._require_live(value["function_handle"], "call")
            if not isinstance(value["arguments"], list):
                raise WorkspaceError("REPLAY_TYPED_SHAPE", "Call arguments must be an array")
            declaration = next((row for row in self.ws.documents[self.doc].functions if row["symbol_id"] == callee), None)
            if declaration is None or len(declaration["parameters"]) != len(value["arguments"]):
                raise WorkspaceError("REPLAY_SIGNATURE_MISMATCH", "Call arity differs from the referenced function")
            return {"kind": "call", "function_id": callee,
                    "arguments": [self._expr(arg, function_id) for arg in value["arguments"]]}
        if kind == "binary" and set(value) == {"kind", "operator", "left", "right"}:
            return {"kind": "binary", "operator": value["operator"],
                    "left": self._expr(value["left"], function_id),
                    "right": self._expr(value["right"], function_id)}
        raise WorkspaceError("REPLAY_TYPED_SHAPE", f"Unsupported portable expression kind {kind!r}")

    def _constructor_calls(self, value: Any) -> Any:
        """Resolve constructor call handles while retaining constructor local_ref syntax."""
        if isinstance(value, list):
            return [self._constructor_calls(item) for item in value]
        if isinstance(value, dict):
            if value.get("kind") == "call":
                if set(value) != {"kind", "function_handle", "arguments"} or not isinstance(value["arguments"], list):
                    raise WorkspaceError("REPLAY_TYPED_SHAPE", "Constructor call has an invalid portable shape")
                callee = self._require_live(value["function_handle"], "constructor call")
                declaration = next((row for row in self.ws.documents[self.doc].functions if row["symbol_id"] == callee), None)
                if declaration is None or len(declaration["parameters"]) != len(value["arguments"]):
                    raise WorkspaceError("REPLAY_SIGNATURE_MISMATCH", "Constructor call arity differs from target")
                return {"kind": "call", "function_id": callee,
                        "arguments": [self._constructor_calls(arg) for arg in value["arguments"]]}
            return {key: self._constructor_calls(child) for key, child in value.items()}
        return value

    def _statement(self, value: Any, function_id: str) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise WorkspaceError("REPLAY_TYPED_SHAPE", "Portable statement must be an object")
        if value.get("kind") == "assign" and set(value) == {"kind", "target", "expression"} and value["target"] == {"kind": "result"}:
            return {"kind": "assign", "target": {"kind": "result"}, "expression": self._expr(value["expression"], function_id)}
        if value.get("kind") == "if" and set(value).issubset({"kind", "condition", "then", "else"}) and {"kind", "condition", "then"}.issubset(value):
            then = value["then"]
            otherwise = value.get("else", [])
            if not isinstance(then, list) or not isinstance(otherwise, list):
                raise WorkspaceError("REPLAY_TYPED_SHAPE", "IF branches must be arrays")
            return {"kind": "if", "condition": self._expr(value["condition"], function_id),
                    "then": [self._statement(row, function_id) for row in then],
                    "else": [self._statement(row, function_id) for row in otherwise]}
        raise WorkspaceError("REPLAY_TYPED_SHAPE", "Only result assignments and structured IF blocks are portable")

    def _portable_expr(self, expr: Any) -> dict[str, Any]:
        if expr.kind == "number":
            return {"kind": "number", "value": expr.value}
        if expr.kind in ("variable", "result"):
            sid = str(expr.value)
            sym = self.ws.documents[self.doc].symbols.get(sid)
            if sym is None or not any(sid in row["parameters"] for row in self.ws.documents[self.doc].functions):
                raise WorkspaceError("REPLAY_UNPORTABLE_REFERENCE", "Selected block references a non-parameter symbol")
            return {"kind": "local_ref", "name": sym.name}
        if expr.kind == "call":
            handle = next((key for key, sid in self.aliases.items() if sid == str(expr.value)), None)
            if handle is None or handle in self.retired:
                raise WorkspaceError("REPLAY_UNPORTABLE_REFERENCE", "Selected call has no live portable function handle")
            return {"kind": "call", "function_handle": handle,
                    "arguments": [self._portable_expr(child) for child in expr.children]}
        if expr.kind in ("compare", "binary"):
            return {"kind": "binary", "operator": str(expr.value),
                    "left": self._portable_expr(expr.children[0]), "right": self._portable_expr(expr.children[1])}
        raise WorkspaceError("REPLAY_UNPORTABLE_REFERENCE", f"Unsupported projected expression kind {expr.kind!r}")

    def _portable_block(self, statement: Any) -> dict[str, Any]:
        if not isinstance(statement, IfBlock):
            raise WorkspaceError("REPLAY_BLOCK_KIND", "Expected an IF block")
        def branch(items):
            result = []
            for child in items:
                if isinstance(child, Assignment):
                    if not child.target_is_result:
                        raise WorkspaceError("REPLAY_BLOCK_KIND", "Only result assignments are portable")
                    handle = next((h for h, sid in self.aliases.items() if sid == child.statement_id), None)
                    result.append({"kind": "assign", "target": {"kind": "result"},
                                   "expression": self._portable_expr(child.expression), "statement_handle": handle})
                elif isinstance(child, IfBlock):
                    result.append(self._portable_block(child))
                elif isinstance(child, ForLoop):
                    raise WorkspaceError("REPLAY_BLOCK_KIND", "FOR blocks are outside the verified portable grammar")
                else:
                    raise WorkspaceError("REPLAY_BLOCK_KIND", "Unsupported projected statement")
            return result
        return {"kind": "if", "condition": self._portable_expr(statement.condition),
                "then": branch(statement.then_body), "else": branch(statement.else_body)}

    def apply_operation(self, item: dict[str, Any], *, index: int | None = None) -> dict[str, Any]:
        """Apply one ordered operation. Earlier successful steps remain applied on later failure."""
        if index is None:
            index = len(self.operation_events)
        if not isinstance(item, dict) or not isinstance(item.get("operation"), str):
            raise WorkspaceError("REPLAY_OPERATION_INVALID", f"Operation {index} lacks an operation discriminator")
        kind = item["operation"]
        if kind not in SUPPORTED_OPERATIONS:
            raise WorkspaceError("REPLAY_OPERATION_UNSUPPORTED", f"Unsupported constructive operation {kind!r} at index {index}")
        before = self.ws.get_revision(self.doc)
        if kind == "create_numeric_function":
            if set(item) - {"operation", "portable_handle", "arguments", "callee_handle"} or not isinstance(item.get("arguments"), dict):
                raise WorkspaceError("REPLAY_OPERATION_INVALID", "Constructor operation has unsupported fields")
            handle = self._fresh_handle(item.get("portable_handle"), "function")
            if not handle.endswith(".function"):
                raise WorkspaceError("REPLAY_HANDLE_INVALID", "Created function handles must end in .function")
            args_keys = set(item["arguments"])
            if args_keys != {"name", "parameters", "body"} or not isinstance(item["arguments"].get("name"), str) or \
                    not isinstance(item["arguments"].get("parameters"), list) or len(item["arguments"]["parameters"]) != 1 or \
                    not isinstance(item["arguments"].get("body"), list):
                raise WorkspaceError("REPLAY_FUNCTION_SHAPE", "Portable constructors require a name, one parameter and a typed body")
            args = self._constructor_calls(item["arguments"])
            calls = _portable_call_handles(item["arguments"])
            if "callee_handle" in item:
                if item["callee_handle"] not in calls:
                    raise WorkspaceError("REPLAY_OPERATION_INVALID", "Legacy callee_handle must match a call in the typed body")
            applied = self.ws.apply_transaction(self.doc, before, [{"operation": kind, **args}])
            raw = projection_semantics(build_projection(self.ws, self.doc, applied["revision"]))
            rows = [row for row in raw["functions"] if row["name"].casefold() == str(args.get("name", "")).casefold()]
            if len(rows) != 1 or len(rows[0]["parameter_ids"]) != 1 or rows[0]["local_ids"] or rows[0]["arrays"]:
                raise WorkspaceError("REPLAY_FUNCTION_SHAPE", "Portable function handles require one numeric parameter and no locals/arrays")
            stem = handle.rsplit(".", 1)[0]
            self.aliases[handle] = rows[0]["symbol_id"]
            param_handle = f"{stem}.parameter.id"
            self._fresh_handle(param_handle, "parameter")
            self.aliases[param_handle] = rows[0]["parameter_ids"][0]
            self.ever_seen.update((handle, param_handle))
            stmt_ids = _statement_ids(rows[0]["statements"])
            for n, sid in enumerate(stmt_ids):
                stmt_handle = f"{stem}.statement.{n}"
                self._fresh_handle(stmt_handle, "statement")
                self.aliases[stmt_handle] = sid
                self.ever_seen.add(stmt_handle)
            self.identity_events.extend([
                {"revision": applied["revision"], "event": "created", "portable_handle": h, "workspace_id": self.aliases[h]}
                for h in [handle, param_handle] + [f"{stem}.statement.{n}" for n in range(len(stmt_ids))]])
        elif kind == "edit_numeric_literals":
            legacy_shape = {"operation", "mission_id", "function_handle", "edits"}
            scoped_shape = {"operation", "mission_id", "scope_mode", "edits"}
            if set(item) == legacy_shape:
                # Historical v1 envelope: retained byte-for-byte for existing streams.
                legacy_function_handle = item["function_handle"]
                self._require_live(legacy_function_handle, "edit function")
            elif set(item) == scoped_shape and item.get("scope_mode") == "per_target":
                # V2 makes each edit's portable function handle authoritative.
                # No single envelope handle may stand in for target resolution.
                legacy_function_handle = None
            else:
                raise WorkspaceError("REPLAY_OPERATION_INVALID", "Numeric edit operation has an invalid portable shape or scope mode")
            if not isinstance(item["edits"], list) or not item["edits"]:
                raise WorkspaceError("REPLAY_OPERATION_INVALID", "Numeric edit operation has an invalid portable shape")
            ops = []
            for edit in item["edits"]:
                if not isinstance(edit, dict) or set(edit) != {"target", "expected_value", "replacement_value"}:
                    raise WorkspaceError("REPLAY_OPERATION_INVALID", "Numeric edit requires target, expected_value and replacement_value")
                target = edit["target"]
                if not isinstance(target, dict) or "function_handle" not in target or "expression_path" not in target:
                    raise WorkspaceError("REPLAY_TARGET_INVALID", "Numeric edit target requires a function handle and expression path")
                target_keys=set(target)
                if target_keys not in ({"function_handle","expression_path","control_path"},
                                       {"function_handle","expression_path","statement_handle"}):
                    raise WorkspaceError("REPLAY_TARGET_INVALID", "Numeric edit target has unknown, missing or conflicting fields")
                if legacy_function_handle is not None and target["function_handle"] != legacy_function_handle:
                    raise WorkspaceError("REPLAY_TARGET_INVALID", "Legacy numeric edit targets must match their envelope function_handle")
                if not isinstance(edit["expected_value"],(int,float)) or isinstance(edit["expected_value"],bool) or not math.isfinite(float(edit["expected_value"])) or \
                        not isinstance(edit["replacement_value"],(int,float)) or isinstance(edit["replacement_value"],bool) or not math.isfinite(float(edit["replacement_value"])):
                    raise WorkspaceError("REPLAY_TARGET_INVALID", "Numeric edit values must be finite numbers")
                if not isinstance(target["expression_path"],list):
                    raise WorkspaceError("REPLAY_TARGET_INVALID", "Numeric expression_path must be an array, including [] for a root")
                fn_id = self._require_live(target["function_handle"], "edit target function")
                op = {"operation": "edit_numeric_literal_at_path", "function_id": fn_id,
                      "expression_path": target["expression_path"], "expected_value": edit["expected_value"],
                      "replacement_value": edit["replacement_value"]}
                if "control_path" in target:
                    op.update(target_kind="if_condition_rhs", control_path=target["control_path"])
                elif "statement_handle" in target:
                    op.update(target_kind="assignment_rhs", statement_id=self._require_live(target["statement_handle"], "edit statement"))
                else:
                    raise WorkspaceError("REPLAY_TARGET_INVALID", "Edit target must specify a control path or statement handle")
                ops.append(op)
            applied = self.ws.apply_transaction(self.doc, before, ops)
        elif kind == "rename_symbol":
            if set(item) != {"operation", "target_handle", "expected_name", "new_name"}:
                raise WorkspaceError("REPLAY_OPERATION_INVALID", "Rename operation has an invalid portable shape")
            sid = self._require_live(item["target_handle"], "rename target")
            symbol = self.ws.documents[self.doc].symbols.get(sid)
            if symbol is None or symbol.name != item["expected_name"]:
                raise WorkspaceError("REPLAY_RENAME_PRECONDITION", "Current source spelling differs from expected_name")
            applied = self.ws.apply_transaction(self.doc, before, [{"operation": "rename_symbol", "symbol_id": sid, "new_name": item["new_name"]}])
        elif kind == "insert_typed_if_block":
            if set(item)!={"operation","function_handle","insertion_anchor_handle","created_statement_handle","statement"}:
                raise WorkspaceError("REPLAY_OPERATION_INVALID", "IF insertion operation has unsupported or missing fields")
            fn = self._require_live(item.get("function_handle"), "IF function")
            anchor = self._require_live(item.get("insertion_anchor_handle"), "IF insertion anchor")
            new_handle = self._fresh_handle(item.get("created_statement_handle"), "created statement")
            statement = self._statement(item.get("statement"), fn)
            if _statement_assignment_count(statement) != 1:
                raise WorkspaceError("REPLAY_STATEMENT_IDENTITY", "This portable insertion form carries one assignment handle")
            applied = self.ws.apply_transaction(self.doc, before, [{"operation": kind, "function_id": fn,
                "before_statement_id": anchor, "statement": statement}])
            rows = [row for row in applied["created_statements"] if row["containing_function_id"] == fn]
            if len(rows) != 1:
                raise WorkspaceError("REPLAY_STATEMENT_IDENTITY", "IF insertion must create one semantic statement")
            self.aliases[new_handle] = rows[0]["statement_id"]
            self.ever_seen.add(new_handle)
            self.identity_events.append({"revision": applied["revision"], "event": "created", "portable_handle": new_handle, "workspace_id": rows[0]["statement_id"]})
        elif kind == "edit_typed_if_condition":
            required = {"operation", "mission_id", "function_handle", "control_path", "anchor_statement_handle", "expected_condition", "condition"}
            if set(item) != required:
                raise WorkspaceError("REPLAY_OPERATION_INVALID", "IF condition operation has an invalid portable shape")
            fn = self._require_live(item["function_handle"], "condition function")
            anchor = self._require_live(item["anchor_statement_handle"], "condition anchor")
            applied = self.ws.apply_transaction(self.doc, before, [{"operation": kind, "function_id": fn,
                "control_path": item["control_path"], "anchor_statement_id": anchor,
                "expected_condition": self._expr(item["expected_condition"], fn),
                "condition": self._expr(item["condition"], fn)}])
        elif kind == "replace_typed_if_block":
            required = {"operation", "function_handle", "control_path", "anchor_statement_handle", "expected_block",
                "expected_block_fingerprint", "expected_removed_statement_handles", "replacement_statements", "created_statement_handle"}
            if set(item) != required:
                raise WorkspaceError("REPLAY_OPERATION_INVALID", "Block replacement operation has an invalid portable shape")
            fn = self._require_live(item["function_handle"], "replacement function")
            anchor = self._require_live(item["anchor_statement_handle"], "replacement anchor")
            retired = item["expected_removed_statement_handles"]
            if not isinstance(retired, list) or not retired or len(retired) != len(set(retired)):
                raise WorkspaceError("REPLAY_RETIREMENT_MISMATCH", "Expected retired handle list must be nonempty and unique")
            retired_ids = [self._require_live(h, "retired statement") for h in retired]
            new_handle = self._fresh_handle(item["created_statement_handle"], "replacement statement")
            path = item["control_path"]
            if not isinstance(path, list) or len(path) != 1 or set(path[0]) != {"block", "index"} or path[0]["block"] != "body":
                raise WorkspaceError("REPLAY_TARGET_AMBIGUOUS", "Replacement must target one top-level body IF")
            projection = build_projection(self.ws, self.doc, before)
            function = next((row for row in projection.functions if row.symbol_id == fn), None)
            index_at = path[0]["index"]
            if function is None or isinstance(index_at, bool) or not isinstance(index_at, int) or not 0 <= index_at < len(function.statements):
                raise WorkspaceError("REPLAY_TARGET_AMBIGUOUS", "Replacement path does not resolve")
            selected = function.statements[index_at]
            portable_block = self._portable_block(selected)
            if portable_block != item["expected_block"] or _fingerprint(portable_block) != item["expected_block_fingerprint"]:
                raise WorkspaceError("REPLAY_BLOCK_MISMATCH", "Current block differs from the recorded expected block or fingerprint")
            removed_ids = _block_statement_ids(selected)
            if set(removed_ids) != set(retired_ids) or anchor not in retired_ids:
                raise WorkspaceError("REPLAY_RETIREMENT_MISMATCH", "Removed statements differ from the explicit retirement set")
            replacements = item["replacement_statements"]
            if not isinstance(replacements, list) or len(replacements) != 1:
                raise WorkspaceError("REPLAY_REPLACEMENT_SHAPE", "Replacement operation currently carries one portable statement handle")
            resolved = [self._statement(row, fn) for row in replacements]
            applied = self.ws.apply_transaction(self.doc, before, [{"operation": kind, "function_id": fn,
                "control_path": path, "anchor_statement_id": anchor,
                "expected_block_fingerprint": self.ws._typed_if_fingerprint(selected)[0],
                "expected_removed_statement_ids": retired_ids,
                "replacement_statements": resolved}])
            for handle, workspace_id in zip(retired, retired_ids):
                self.aliases.pop(handle)
                self.retired[handle] = {"retired_at_revision": applied["revision"],
                                         "reason": "replaced typed IF block", "workspace_id": workspace_id}
                self.identity_events.append({"revision": applied["revision"], "event": "retired",
                                             "portable_handle": handle, "workspace_id": workspace_id})
            created = [row for row in applied["created_statements"] if row["containing_function_id"] == fn]
            if len(created) != len(replacements):
                raise WorkspaceError("REPLAY_STATEMENT_IDENTITY", "Block replacement allocated an unexpected number of statements")
            if len(created) != 1:
                raise WorkspaceError("REPLAY_STATEMENT_IDENTITY", "Replacement format currently assigns one portable statement handle")
            self.aliases[new_handle] = created[0]["statement_id"]
            self.ever_seen.add(new_handle)
            self.identity_events.append({"revision": applied["revision"], "event": "created", "portable_handle": new_handle,
                                         "workspace_id": created[0]["statement_id"]})
        after = self.ws.get_revision(self.doc)
        if after != before + 1:
            raise WorkspaceError("REPLAY_REVISION_TRANSITION", f"Operation {index} did not advance exactly one revision")
        self.operation_events.append({"index": index, "operation": kind, "base_revision": before,
                                      "resulting_revision": after, "status": "applied"})
        return self.operation_events[-1]


def _statement_ids(rows: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for row in rows:
        if row.get("kind") in ("assignment", "array_assignment") and row.get("statement_id"):
            out.append(row["statement_id"])
        elif row.get("kind") == "if":
            out.extend(_statement_ids(row.get("then", [])))
            out.extend(_statement_ids(row.get("else", [])))
        elif row.get("kind") == "for":
            out.extend(_statement_ids(row.get("body", [])))
    return out


def _statement_assignment_count(statement: dict[str, Any]) -> int:
    if statement.get("kind") == "assign":
        return 1
    if statement.get("kind") == "if":
        return sum(_statement_assignment_count(row) for row in statement.get("then", [])) + \
               sum(_statement_assignment_count(row) for row in statement.get("else", []))
    return 0


def _portable_call_handles(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, list):
        for row in value:
            found.update(_portable_call_handles(row))
    elif isinstance(value, dict):
        if value.get("kind") == "call" and isinstance(value.get("function_handle"), str):
            found.add(value["function_handle"])
        for row in value.values():
            found.update(_portable_call_handles(row))
    return found


def _block_statement_ids(statement: Any) -> list[str]:
    out: list[str] = []
    def visit(rows):
        for row in rows:
            if isinstance(row, Assignment) and row.statement_id:
                out.append(row.statement_id)
            elif isinstance(row, IfBlock):
                visit(row.then_body); visit(row.else_body)
            elif isinstance(row, ForLoop):
                visit(row.body)
    if not isinstance(statement, IfBlock):
        raise WorkspaceError("REPLAY_BLOCK_KIND", "Selected statement is not an IF")
    visit(statement.then_body); visit(statement.else_body)
    return out


def replay_constructive_stream(workspace: Workspace, document_id: str,
                               operations: list[dict[str, Any]], **options: Any) -> ReplayResult:
    """Public function-shaped API for deterministic portable replay."""
    return PortableReplay.replay_constructive_stream(workspace, document_id, operations, **options)
