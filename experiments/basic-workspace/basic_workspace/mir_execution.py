"""Revision-checked projection serialization and isolated MIR worker execution."""
from __future__ import annotations

import math
import os
from pathlib import Path
import struct
import subprocess
import time
from typing import Any

from .model import Workspace, WorkspaceError
from .projection import (Assignment, CompilableProjection, Expr, ForLoop,
                         FunctionProjection, IfBlock, ProjectedStatement,
                         build_projection)


WORKER_TIMEOUT_SECONDS = 2.0
MAX_ARGUMENTS = 6
MAX_ARRAYS_PER_FUNCTION = 32
MAX_ARRAY_ELEMENTS = 256
MAX_TOTAL_ARRAY_ELEMENTS = 4096
MAX_LOOP_ITERATIONS = 10000
MAX_STRING_BYTES = 4096


class MirExecutionService:
    def __init__(self, worker: str | None = None, timeout: float = WORKER_TIMEOUT_SECONDS):
        root = Path(__file__).resolve().parents[1]
        self.worker = Path(worker or os.environ.get(
            "BASIC_WORKSPACE_MIR_WORKER", root / "native" / "build" / "mir-worker")).resolve()
        self.timeout = timeout

    def execute_function(self, workspace: Workspace, document_id: str, expected_revision: int,
                         function_id: str, arguments: list[Any], engine: str = "interp") -> dict[str, Any]:
        if engine not in ("interp", "jit"):
            raise WorkspaceError("INVALID_ENGINE", "engine must be 'interp' or 'jit'")
        if not isinstance(arguments, list):
            raise WorkspaceError("INVALID_ARGUMENTS", "arguments must be an array")
        if not self.worker.is_file() or not os.access(self.worker, os.X_OK):
            raise WorkspaceError("MIR_WORKER_NOT_BUILT", f"MIR worker is unavailable at {self.worker}")

        projection_started = time.perf_counter()
        projection = build_projection(workspace, document_id, expected_revision)
        projection_ms = (time.perf_counter() - projection_started) * 1000
        by_id = {f.symbol_id: (i, f) for i, f in enumerate(projection.functions)}
        if function_id not in by_id:
            d = workspace._doc(document_id)
            if function_id not in d.symbols:
                raise WorkspaceError("SYMBOL_NOT_FOUND", "Unknown function identity")
            raise WorkspaceError("NOT_EXECUTABLE", "This identity is not a supported FUNCTION")
        target_index, target = by_id[function_id]
        if len(arguments) != len(target.parameter_ids):
            raise WorkspaceError("ARGUMENT_COUNT", f"Function {target.name} expects {len(target.parameter_ids)} arguments, got {len(arguments)}")
        if len(arguments) > MAX_ARGUMENTS:
            raise WorkspaceError("UNSUPPORTED_ARITY", f"The initial MIR ABI supports at most {MAX_ARGUMENTS} arguments")
        numbers: list[float] = []
        for index, value in enumerate(arguments):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise WorkspaceError("INVALID_ARGUMENT_TYPE", f"Argument {index} must be a number")
            number = float(value)
            if not math.isfinite(number):
                raise WorkspaceError("NON_FINITE_ARGUMENT", f"Argument {index} must be finite")
            numbers.append(number)

        encode_started = time.perf_counter()
        payload = encode_projection(projection, target_index, numbers, engine)
        encode_ms = (time.perf_counter() - encode_started) * 1000
        command_started = time.perf_counter()
        try:
            completed = subprocess.run([str(self.worker)], input=payload, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, timeout=self.timeout, check=False)
        except subprocess.TimeoutExpired as exc:
            raise WorkspaceError("EXECUTION_TIMEOUT", f"MIR {engine} execution exceeded {self.timeout:g}s") from exc
        worker_ms = (time.perf_counter() - command_started) * 1000
        if completed.returncode != 0:
            stderr = completed.stderr.decode("utf-8", "replace")[-2000:]
            raise WorkspaceError("MIR_WORKER_FAILED", f"MIR worker exited with status {completed.returncode}",
                                 {"stderr": stderr})
        try:
            response = __import__("json").loads(completed.stdout.decode("utf-8"))
        except Exception as exc:
            raise WorkspaceError("MIR_WORKER_PROTOCOL", "MIR worker returned malformed output",
                                 {"stdout": completed.stdout[:500].decode("utf-8", "replace")}) from exc
        if not response.get("ok"):
            raise WorkspaceError(response.get("code", "MIR_BUILD_FAILED"),
                                 response.get("message", "MIR worker failed"))
        if target.return_type == "string":
            result = response.get("result")
            if not isinstance(result, str):
                raise WorkspaceError("MIR_WORKER_PROTOCOL", "MIR worker omitted a valid string result")
            result_type = "string"
        else:
            try:
                result = float.fromhex(response["result_hex"])
            except (KeyError, TypeError, ValueError) as exc:
                raise WorkspaceError("MIR_WORKER_PROTOCOL", "MIR worker omitted a valid numeric result") from exc
            if not math.isfinite(result):
                raise WorkspaceError("NON_FINITE_RESULT", "MIR execution produced a non-finite double result")
            result_type = "double"
        return {"document_id": document_id, "revision": projection.revision,
                "function_id": function_id, "engine": engine, "result_type": result_type,
                "result": result, "result_utf8_bytes": len(result.encode("utf-8")) if isinstance(result, str) else None,
                "transport_bytes": len(payload), "worker_response_bytes": len(completed.stdout),
                "cache": "none", "worker_maxrss_kib": response.get("maxrss_kib"), "timings_ms": {
                    "projection": round(projection_ms, 3), "serialization": round(encode_ms, 3),
                    "worker_compile_and_execute": round(worker_ms, 3),
                    **{f"mir_{key}" if key in ("build", "link", "jit_compile", "invoke") else key:
                       round(float(value), 6)
                       for key, value in response.get("timings_ms", {}).items()}}}


def _u32(value: int) -> bytes:
    if not 0 <= value <= 0xFFFFFFFF:
        raise WorkspaceError("PROJECTION_LIMIT", "Projection integer exceeds the binary format")
    return struct.pack("<I", value)


def _encode_expr(expr: Expr, function_slots: dict[str, int], local_slots: dict[str, int],
                 array_slots: dict[str, int], result_symbol_id: str) -> bytes:
    if expr.kind == "number":
        number = float(expr.value)
        if not math.isfinite(number):
            raise WorkspaceError("NON_FINITE_CONSTANT", "Numeric constants must be finite doubles")
        return b"\x01" + struct.pack("<d", number)
    if expr.kind == "string":
        data = str(expr.value).encode("utf-8", "strict")
        if b"\0" in data or len(data) > MAX_STRING_BYTES:
            raise WorkspaceError("STRING_LIMIT", "String literal contains NUL or exceeds 4096 UTF-8 bytes")
        return b"\x11" + _u32(len(data)) + data
    if expr.kind in ("variable", "variable_string"):
        try:
            slot = local_slots[str(expr.value)]
        except KeyError as exc:
            raise WorkspaceError("UNRESOLVED_SYMBOL", "Variable identity is absent from the projection") from exc
        return b"\x02" + _u32(slot)
    if expr.kind in ("result", "result_string"):
        return b"\x03"
    if expr.kind == "unary_minus":
        return b"\x08" + _encode_expr(expr.children[0], function_slots, local_slots,
                                       array_slots, result_symbol_id)
    if expr.kind == "binary" or expr.kind == "compare":
        opcodes = {"+": b"\x04", "-": b"\x05", "*": b"\x06", "/": b"\x07"}
        opcodes.update({"=": b"\x0b", "<>": b"\x0c", "<": b"\x0d",
                        "<=": b"\x0e", ">": b"\x0f", ">=": b"\x10"})
        if expr.value not in opcodes:
            raise WorkspaceError("UNSUPPORTED_OPERATOR", f"Unsupported arithmetic operator {expr.value}")
        return (opcodes[str(expr.value)] +
                _encode_expr(expr.children[0], function_slots, local_slots, array_slots, result_symbol_id) +
                _encode_expr(expr.children[1], function_slots, local_slots, array_slots, result_symbol_id))
    if expr.kind == "call":
        try:
            callee = function_slots[str(expr.value)]
        except KeyError as exc:
            raise WorkspaceError("UNSUPPORTED_CALL", "Call target is absent from the projection") from exc
        if len(expr.children) > MAX_ARGUMENTS:
            raise WorkspaceError("UNSUPPORTED_ARITY", f"Numeric calls support at most {MAX_ARGUMENTS} arguments")
        encoded = bytearray(b"\x09" + _u32(callee) + _u32(len(expr.children)))
        for child in expr.children:
            encoded.extend(_encode_expr(child, function_slots, local_slots, array_slots, result_symbol_id))
        return bytes(encoded)
    if expr.kind in ("array_element", "array_element_string"):
        try:
            array_slot = array_slots[str(expr.value)]
        except KeyError as exc:
            raise WorkspaceError("UNRESOLVED_ARRAY", "Array identity is absent from the function projection") from exc
        return (b"\x0a" + _u32(array_slot) +
                _encode_expr(expr.children[0], function_slots, local_slots, array_slots, result_symbol_id))
    raise WorkspaceError("UNSUPPORTED_EXPRESSION", f"Unsupported projection expression kind {expr.kind}")


def _encode_statement(statement: ProjectedStatement, function_slots: dict[str, int],
                      local_slots: dict[str, int], array_slots: dict[str, int],
                      result_symbol_id: str) -> bytes:
    if isinstance(statement, Assignment):
        if statement.target_is_array:
            target_kind, slot = 2, array_slots.get(statement.target_symbol_id, -1)
        elif statement.target_is_result:
            target_kind, slot = 1, 0
        else:
            target_kind, slot = 0, local_slots.get(statement.target_symbol_id, -1)
        if slot < 0:
            raise WorkspaceError("UNRESOLVED_SYMBOL", "Structured assignment target is absent from projection")
        output = bytearray(struct.pack("<BBHI", 0, target_kind, 0, slot))
        if statement.target_is_array:
            if statement.target_index is None:
                raise WorkspaceError("INVALID_ARRAY_ASSIGNMENT", "Array assignment has no index")
            output.extend(_encode_expr(statement.target_index, function_slots, local_slots,
                                       array_slots, result_symbol_id))
        output.extend(_encode_expr(statement.expression, function_slots, local_slots,
                                   array_slots, result_symbol_id))
        return bytes(output)
    if isinstance(statement, IfBlock):
        output = bytearray(struct.pack("<BBHI", 1, 0, 0, 0))
        output.extend(_encode_expr(statement.condition, function_slots, local_slots,
                                   array_slots, result_symbol_id))
        output.extend(_u32(len(statement.then_body)))
        for child in statement.then_body:
            output.extend(_encode_statement(child, function_slots, local_slots, array_slots,
                                            result_symbol_id))
        output.extend(_u32(len(statement.else_body)))
        for child in statement.else_body:
            output.extend(_encode_statement(child, function_slots, local_slots, array_slots,
                                            result_symbol_id))
        return bytes(output)
    if isinstance(statement, ForLoop):
        try:
            slot = local_slots[statement.variable_id]
        except KeyError as exc:
            raise WorkspaceError("INVALID_LOOP_VARIABLE", "FOR variable is absent from function locals") from exc
        if not 1 <= statement.iteration_limit <= MAX_LOOP_ITERATIONS:
            raise WorkspaceError("LOOP_LIMIT", "Static FOR iteration limit exceeds worker policy")
        output = bytearray(struct.pack("<BBHI", 2, 0, 0, slot))
        for value in (statement.start, statement.end, statement.step):
            output.extend(_encode_expr(Expr("number", value), function_slots, local_slots,
                                       array_slots, result_symbol_id))
        output.extend(_u32(statement.iteration_limit))
        output.extend(_u32(len(statement.body)))
        for child in statement.body:
            output.extend(_encode_statement(child, function_slots, local_slots, array_slots,
                                            result_symbol_id))
        return bytes(output)
    raise WorkspaceError("UNSUPPORTED_STATEMENT", f"Unsupported projection statement {type(statement).__name__}")


def encode_projection(projection: CompilableProjection, target_index: int,
                      arguments: list[float], engine: str = "interp") -> bytes:
    function_slots = {f.symbol_id: i for i, f in enumerate(projection.functions)}
    if not 0 <= target_index < len(projection.functions):
        raise WorkspaceError("SYMBOL_NOT_FOUND", "Requested function is absent from this projection")
    output = bytearray(b"BWM4")
    output.extend(struct.pack("<IIII", 4, 0 if engine == "interp" else 1,
                              target_index, len(projection.functions)))
    for function in projection.functions:
        argc = len(function.parameter_ids)
        if argc > MAX_ARGUMENTS:
            raise WorkspaceError("UNSUPPORTED_ARITY", f"Function {function.name} exceeds {MAX_ARGUMENTS} parameters")
        local_slots = {sid: argc + i for i, sid in enumerate(function.local_ids)}
        local_slots.update({sid: i for i, sid in enumerate(function.parameter_ids)})
        if len(function.arrays) > MAX_ARRAYS_PER_FUNCTION:
            raise WorkspaceError("ARRAY_LIMIT", f"Function {function.name} exceeds {MAX_ARRAYS_PER_FUNCTION} arrays")
        total_elements = 0
        for array in function.arrays:
            capacity = array.upper_bound - array.lower_bound + 1
            if (array.lower_bound != 0 or capacity < 1 or capacity > MAX_ARRAY_ELEMENTS):
                raise WorkspaceError("ARRAY_LIMIT", f"Array {array.name} is outside the supported zero-based capacity")
            total_elements += capacity
        if total_elements > MAX_TOTAL_ARRAY_ELEMENTS:
            raise WorkspaceError("ARRAY_LIMIT", f"Function {function.name} exceeds {MAX_TOTAL_ARRAY_ELEMENTS} total array elements")
        output.extend(struct.pack("<IIII", argc, len(function.local_ids),
                                  len(function.arrays), len(function.statements)))
        output.extend(_u32(1 if function.return_type == "string" else 0))
        slot_types = tuple("numeric" for _ in function.parameter_ids) + function.local_types
        if len(slot_types) != argc + len(function.local_ids):
            raise WorkspaceError("INVALID_PROJECTION", "Projection local type table is incomplete")
        output.extend(bytes(1 if item == "string" else 0 for item in slot_types))
        array_slots = {array.symbol_id: i for i, array in enumerate(function.arrays)}
        for array in function.arrays:
            output.extend(_u32(array.lower_bound))
            output.extend(_u32(array.upper_bound))
            output.append(1 if array.element_type == "string" else 0)
        for statement in function.statements:
            output.extend(_encode_statement(statement, function_slots, local_slots,
                                            array_slots, function.symbol_id))
    output.extend(_u32(target_index))
    output.extend(_u32(len(arguments)))
    for value in arguments:
        output.extend(struct.pack("<d", value))
    return bytes(output)
