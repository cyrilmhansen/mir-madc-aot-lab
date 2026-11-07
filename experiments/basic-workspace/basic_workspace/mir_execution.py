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
from .projection import CompilableProjection, Expr, FunctionProjection, build_projection


WORKER_TIMEOUT_SECONDS = 2.0
MAX_ARGUMENTS = 6


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
            raise WorkspaceError("INVALID_ARGUMENTS", "arguments must be an array of numbers")
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
            raise WorkspaceError("NOT_EXECUTABLE", "This identity is not a supported numeric FUNCTION")
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
        try:
            result = float.fromhex(response["result_hex"])
        except (KeyError, TypeError, ValueError) as exc:
            raise WorkspaceError("MIR_WORKER_PROTOCOL", "MIR worker omitted a valid numeric result") from exc
        if not math.isfinite(result):
            raise WorkspaceError("NON_FINITE_RESULT", "MIR execution produced a non-finite double result")
        return {"document_id": document_id, "revision": projection.revision,
                "function_id": function_id, "engine": engine, "result_type": "double",
                "result": result, "cache": "none", "worker_maxrss_kib": response.get("maxrss_kib"), "timings_ms": {
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
                 result_symbol_id: str) -> bytes:
    if expr.kind == "number":
        number = float(expr.value)
        if not math.isfinite(number):
            raise WorkspaceError("NON_FINITE_CONSTANT", "Numeric constants must be finite doubles")
        return b"\x01" + struct.pack("<d", number)
    if expr.kind == "variable":
        try:
            slot = local_slots[str(expr.value)]
        except KeyError as exc:
            raise WorkspaceError("UNRESOLVED_SYMBOL", "Variable identity is absent from the projection") from exc
        return b"\x02" + _u32(slot)
    if expr.kind == "result":
        return b"\x03"
    if expr.kind == "unary_minus":
        return b"\x08" + _encode_expr(expr.children[0], function_slots, local_slots, result_symbol_id)
    if expr.kind == "binary":
        opcodes = {"+": b"\x04", "-": b"\x05", "*": b"\x06", "/": b"\x07"}
        if expr.value not in opcodes:
            raise WorkspaceError("UNSUPPORTED_OPERATOR", f"Unsupported arithmetic operator {expr.value}")
        return (opcodes[str(expr.value)] +
                _encode_expr(expr.children[0], function_slots, local_slots, result_symbol_id) +
                _encode_expr(expr.children[1], function_slots, local_slots, result_symbol_id))
    if expr.kind == "call":
        try:
            callee = function_slots[str(expr.value)]
        except KeyError as exc:
            raise WorkspaceError("UNSUPPORTED_CALL", "Call target is absent from the projection") from exc
        if len(expr.children) > MAX_ARGUMENTS:
            raise WorkspaceError("UNSUPPORTED_ARITY", f"Numeric calls support at most {MAX_ARGUMENTS} arguments")
        encoded = bytearray(b"\x09" + _u32(callee) + _u32(len(expr.children)))
        for child in expr.children:
            encoded.extend(_encode_expr(child, function_slots, local_slots, result_symbol_id))
        return bytes(encoded)
    raise WorkspaceError("UNSUPPORTED_EXPRESSION", f"Unsupported projection expression kind {expr.kind}")


def encode_projection(projection: CompilableProjection, target_index: int,
                      arguments: list[float], engine: str = "interp") -> bytes:
    function_slots = {f.symbol_id: i for i, f in enumerate(projection.functions)}
    if not 0 <= target_index < len(projection.functions):
        raise WorkspaceError("SYMBOL_NOT_FOUND", "Requested function is absent from this projection")
    output = bytearray(b"BWM1")
    output.extend(struct.pack("<IIII", 1, 0 if engine == "interp" else 1,
                              target_index, len(projection.functions)))
    for function in projection.functions:
        argc = len(function.parameter_ids)
        if argc > MAX_ARGUMENTS:
            raise WorkspaceError("UNSUPPORTED_ARITY", f"Function {function.name} exceeds {MAX_ARGUMENTS} parameters")
        local_slots = {sid: argc + i for i, sid in enumerate(function.local_ids)}
        local_slots.update({sid: i for i, sid in enumerate(function.parameter_ids)})
        output.extend(struct.pack("<III", argc, len(function.local_ids), len(function.statements)))
        for statement in function.statements:
            if statement.target_is_result:
                target_kind, slot = 1, 0
            else:
                target_kind, slot = 0, local_slots.get(statement.target_symbol_id, -1)
                if slot < 0:
                    raise WorkspaceError("UNRESOLVED_SYMBOL", "Assignment target identity is absent from the projection")
            output.extend(struct.pack("<B3xI", target_kind, slot))
            output.extend(_encode_expr(statement.expression, function_slots, local_slots,
                                       function.symbol_id))
    output.extend(_u32(target_index))
    output.extend(_u32(len(arguments)))
    for value in arguments:
        output.extend(struct.pack("<d", value))
    return bytes(output)
