"""Revision-checked projection serialization and isolated MIR worker execution."""
from __future__ import annotations

import math
import os
import json
import select
from pathlib import Path
import struct
import subprocess
import time
import threading
import uuid
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
MAX_PERSISTENT_MODULES = 16
MAX_PERSISTENT_INSTANCES = 32


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


class _PreparedModule:
    def __init__(self, projection: CompilableProjection, engine: str, projection_ms: float):
        self.projection = projection
        self.engine = engine
        self.projection_ms = projection_ms
        self.instances: set[str] = set()


class _PersistentInstance:
    def __init__(self, module_id: str, module: _PreparedModule, proc: subprocess.Popen[bytes]):
        self.module_id = module_id
        self.document_id = module.projection.document_id
        self.revision = module.projection.revision
        self.engine = module.engine
        self.proc = proc
        self.status = "ready"
        self.sequence = 0
        self.lock = threading.Lock()
        self.stdout_buffer = bytearray()
        self.call_count = 0
        self.initializer_function_id: str | None = None
        self.initializing = False
        self.startup_ms = 0.0
        self.stderr_tail = ""


class PersistentExecutionService:
    """One persistent native MIR process per instance; compiled per process."""
    def __init__(self, worker: str | None = None, timeout: float = WORKER_TIMEOUT_SECONDS):
        root = Path(__file__).resolve().parents[1]
        self.worker = Path(worker or os.environ.get(
            "BASIC_WORKSPACE_MIR_WORKER", root / "native" / "build" / "mir-worker")).resolve()
        self.timeout = timeout
        self.modules: dict[str, _PreparedModule] = {}
        self.instances: dict[str, _PersistentInstance] = {}
        self.lock = threading.RLock()

    def prepare_module(self, workspace: Workspace, document_id: str,
                       expected_revision: int, engine: str = "interp") -> dict[str, Any]:
        if engine not in ("interp", "jit"):
            raise WorkspaceError("INVALID_ENGINE", "engine must be 'interp' or 'jit'")
        started = time.perf_counter()
        projection = build_projection(workspace, document_id, expected_revision)
        projection_ms = (time.perf_counter() - started) * 1000
        module_id = "mod_" + uuid.uuid4().hex
        module = _PreparedModule(projection, engine, projection_ms)
        with self.lock:
            if len(self.modules) >= MAX_PERSISTENT_MODULES:
                raise WorkspaceError("MODULE_LIMIT", f"At most {MAX_PERSISTENT_MODULES} prepared modules may be live")
            self.modules[module_id] = module
        return {"module_id": module_id, "document_id": document_id,
                "revision": projection.revision, "engine": engine,
                "function_count": len(projection.functions),
                "compiled": False, "compiled_per_instance": True,
                "projection_ms": round(projection_ms, 3)}

    @staticmethod
    def _frame(payload: bytes) -> bytes:
        if not payload or len(payload) > 16 * 1024 * 1024:
            raise WorkspaceError("PROJECTION_LIMIT", "persistent frame is empty or exceeds 16 MiB")
        return struct.pack("<I", len(payload)) + payload

    @staticmethod
    def _readline(instance: _PersistentInstance, timeout: float) -> bytes:
        deadline = time.monotonic() + timeout
        while True:
            newline = instance.stdout_buffer.find(b"\n")
            if newline >= 0:
                line = bytes(instance.stdout_buffer[:newline])
                del instance.stdout_buffer[:newline + 1]
                return line
            left = deadline - time.monotonic()
            if left <= 0:
                raise TimeoutError("persistent MIR response timeout")
            if instance.proc.poll() is not None:
                raise BrokenPipeError(f"worker exited with status {instance.proc.returncode}")
            ready, _, _ = select.select([instance.proc.stdout], [], [], left)
            if not ready:
                raise TimeoutError("persistent MIR response timeout")
            chunk = os.read(instance.proc.stdout.fileno(), 4096)
            if not chunk:
                raise BrokenPipeError("worker closed stdout")
            instance.stdout_buffer.extend(chunk)
            if len(instance.stdout_buffer) > 65536:
                raise WorkspaceError("MIR_WORKER_PROTOCOL", "response exceeded 64 KiB")

    def create_instance(self, module_id: str, initializer_function_id: str | None = None) -> dict[str, Any]:
        with self.lock:
            module = self.modules.get(module_id)
            if len(self.instances) >= MAX_PERSISTENT_INSTANCES:
                raise WorkspaceError("INSTANCE_LIMIT", f"At most {MAX_PERSISTENT_INSTANCES} instances may be live")
        if module is None:
            raise WorkspaceError("MODULE_NOT_FOUND", "Unknown prepared module")
        if not self.worker.is_file() or not os.access(self.worker, os.X_OK):
            raise WorkspaceError("MIR_WORKER_NOT_BUILT", f"MIR worker unavailable at {self.worker}")
        first = module.projection.functions[0]
        # BWM4's invocation tail is consumed during module validation. The
        # persistent worker ignores it and accepts calls in subsequent frames.
        payload = encode_projection(module.projection, 0,
                                   [0.0] * len(first.parameter_ids), module.engine)
        env = os.environ.copy()
        env["BASIC_WORKSPACE_PERSISTENT"] = "1"
        startup_started = time.perf_counter()
        proc = subprocess.Popen([str(self.worker)], stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                env=env, bufsize=0)
        instance_id = "inst_" + uuid.uuid4().hex
        instance = _PersistentInstance(module_id, module, proc)
        try:
            proc.stdin.write(self._frame(payload)); proc.stdin.flush()
            ready = json.loads(self._readline(instance, self.timeout).decode("utf-8"))
            if not ready.get("ready") or ready.get("engine") != module.engine:
                raise WorkspaceError("MIR_WORKER_PROTOCOL", "invalid persistent worker startup response", ready)
            instance.worker_timings = ready.get("timings_ms", {})
            instance.mir_build_count = ready.get("mir_build_count")
            instance.mir_link_count = ready.get("mir_link_count")
            instance.startup_ms = (time.perf_counter() - startup_started) * 1000
            with self.lock:
                self.instances[instance_id] = instance
                module.instances.add(instance_id)
        except Exception:
            proc.kill(); proc.wait()
            raise
        if initializer_function_id is not None:
            try:
                instance.initializer_function_id = initializer_function_id
                instance.initializing = True
                init_result = self.call_instance_function(instance_id, initializer_function_id, [],
                                                          module.projection.revision)
                if init_result["result"] != 0.0:
                    raise WorkspaceError("INSTANCE_INITIALIZATION_FAILED", "Initializer must return numeric zero")
                instance.initializing = False
            except Exception as exc:
                self.destroy_instance(instance_id)
                if isinstance(exc, WorkspaceError):
                    raise WorkspaceError("INSTANCE_INITIALIZATION_FAILED", "Instance initializer failed; instance was destroyed",
                                         {"cause": exc.code}) from exc
                raise
        return self.get_instance_info(instance_id)

    @staticmethod
    def _numbers(arguments: list[Any], expected: int) -> list[float]:
        if not isinstance(arguments, list) or len(arguments) != expected:
            raise WorkspaceError("ARGUMENT_COUNT", f"Expected {expected} numeric arguments")
        result = []
        for i, value in enumerate(arguments):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise WorkspaceError("INVALID_ARGUMENT_TYPE", f"Argument {i} must be finite numeric")
            result.append(float(value))
        return result

    def call_instance_function(self, instance_id: str, function_id: str,
                               arguments: list[Any], expected_revision: int | None = None) -> dict[str, Any]:
        with self.lock:
            instance = self.instances.get(instance_id)
            module = self.modules.get(instance.module_id) if instance else None
        if instance is None:
            raise WorkspaceError("INSTANCE_NOT_FOUND", "Unknown execution instance")
        if instance.status != "ready" or module is None:
            raise WorkspaceError("INSTANCE_INVALID", "Execution instance is not ready")
        if expected_revision is not None and expected_revision != instance.revision:
            raise WorkspaceError("STALE_REVISION", f"Instance is bound to revision {instance.revision}")
        slots = {f.symbol_id: (i, f) for i, f in enumerate(module.projection.functions)}
        if function_id not in slots:
            raise WorkspaceError("FUNCTION_NOT_IN_MODULE", "Function identity is not in the bound revision")
        target, function = slots[function_id]
        if function_id == instance.initializer_function_id and not instance.initializing:
            raise WorkspaceError("INITIALIZER_ALREADY_RAN", "The instance initializer runs only during instance creation")
        if function.return_type != "numeric":
            raise WorkspaceError("PERSISTENT_NUMERIC_ONLY", "Persistent calls currently support numeric results")
        numbers = self._numbers(arguments, len(function.parameter_ids))
        with instance.lock:
            if instance.status != "ready" or instance.proc.poll() is not None:
                instance.status = "dead"
                raise WorkspaceError("INSTANCE_INVALID", "Worker exited")
            instance.sequence += 1
            reqid = instance.sequence
            frame = bytearray(struct.pack("<BIII", 1, reqid, target, len(numbers)))
            for number in numbers:
                frame.extend(struct.pack("<d", number))
            started = time.perf_counter()
            try:
                instance.proc.stdin.write(self._frame(bytes(frame))); instance.proc.stdin.flush()
                response = json.loads(self._readline(instance, self.timeout).decode("utf-8"))
            except TimeoutError as exc:
                self._invalidate(instance)
                raise WorkspaceError("INSTANCE_TIMEOUT", "Call timed out; instance invalidated") from exc
            except Exception as exc:
                self._invalidate(instance)
                raise WorkspaceError("INSTANCE_WORKER_FAILED", "Worker failed; instance invalidated",
                                     {"error": str(exc)[:1000]}) from exc
            if response.get("request_id") != reqid:
                self._invalidate(instance)
                raise WorkspaceError("MIR_WORKER_PROTOCOL", "Response ID mismatch; instance invalidated")
            if not response.get("ok"):
                raise WorkspaceError(response.get("code", "MIR_EXECUTION_FAILED"), response.get("message", "Call failed"))
            value = float.fromhex(response["result_hex"])
            if not math.isfinite(value):
                raise WorkspaceError("NON_FINITE_RESULT", "MIR returned a non-finite result")
            instance.call_count += 1
            elapsed = (time.perf_counter() - started) * 1000
        return {"instance_id": instance_id, "module_id": instance.module_id,
                "document_id": instance.document_id, "revision": instance.revision,
                "function_id": function_id, "engine": instance.engine,
                "result_type": "double", "result": value,
                "call_count": instance.call_count,
                "startup_ms": round(instance.startup_ms, 3),
                "timings_ms": {"round_trip": round(elapsed, 3)}}

    @staticmethod
    def _invalidate(instance: _PersistentInstance) -> None:
        instance.status = "dead"
        if instance.proc.poll() is None:
            instance.proc.kill(); instance.proc.wait()

    def get_instance_info(self, instance_id: str) -> dict[str, Any]:
        with self.lock:
            instance = self.instances.get(instance_id)
            module = self.modules.get(instance.module_id) if instance else None
        if instance is None:
            raise WorkspaceError("INSTANCE_NOT_FOUND", "Unknown execution instance")
        if instance.proc.poll() is not None and instance.status == "ready":
            instance.status = "dead"
        return {"instance_id": instance_id, "module_id": instance.module_id,
                "document_id": instance.document_id, "revision": instance.revision,
                "engine": instance.engine, "status": instance.status,
                "call_count": instance.call_count,
                "startup_ms": round(instance.startup_ms, 3),
                "projection_ms": round(module.projection_ms, 3) if module else None,
                "mir_build_count": instance.mir_build_count,
                "mir_link_count": instance.mir_link_count,
                "worker_timings_ms": instance.worker_timings,
                "worker_exit_code": instance.proc.poll(),
                "stderr_tail": instance.stderr_tail[-2000:]}

    def destroy_instance(self, instance_id: str) -> dict[str, Any]:
        with self.lock:
            instance = self.instances.get(instance_id)
        if instance is None:
            return {"instance_id": instance_id, "destroyed": False}
        with instance.lock:
            if instance.status == "ready" and instance.proc.poll() is None:
                instance.sequence += 1
                try:
                    frame = self._frame(struct.pack("<BI", 2, instance.sequence))
                    instance.proc.stdin.write(frame); instance.proc.stdin.flush()
                    ack = json.loads(self._readline(instance, self.timeout).decode("utf-8"))
                    if ack.get("request_id") != instance.sequence or not ack.get("shutdown"):
                        raise ValueError("bad shutdown acknowledgment")
                except Exception:
                    self._invalidate(instance)
            if instance.proc.poll() is None:
                try: instance.proc.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    instance.proc.terminate()
                    try: instance.proc.wait(timeout=0.5)
                    except subprocess.TimeoutExpired: instance.proc.kill(); instance.proc.wait()
            if instance.proc.stderr is not None:
                try:
                    instance.stderr_tail = instance.proc.stderr.read().decode("utf-8", "replace")[-2000:]
                except OSError:
                    pass
            instance.status = "destroyed"
            for stream in (instance.proc.stdin, instance.proc.stdout, instance.proc.stderr):
                if stream is not None: stream.close()
        with self.lock:
            self.instances.pop(instance_id, None)
            module = self.modules.get(instance.module_id)
            if module: module.instances.discard(instance_id)
        return {"instance_id": instance_id, "destroyed": True}

    def release_module(self, module_id: str) -> dict[str, Any]:
        with self.lock:
            module = self.modules.get(module_id)
            if module is None: return {"module_id": module_id, "released": False}
            if module.instances: raise WorkspaceError("MODULE_IN_USE", "Destroy bound instances first")
            del self.modules[module_id]
        return {"module_id": module_id, "released": True}

    def close(self) -> None:
        for instance_id in list(self.instances): self.destroy_instance(instance_id)
        self.modules.clear()


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
    version5 = any(array.shared for function in projection.functions for array in function.arrays)
    version = 5 if version5 else 4
    output = bytearray(b"BWM5" if version5 else b"BWM4")
    output.extend(struct.pack("<IIII", version, 0 if engine == "interp" else 1,
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
            if version5:
                if array.shared and array.shared_slot < 0:
                    raise WorkspaceError("INVALID_PROJECTION", "Shared array is missing its module slot")
                output.append(1 if array.shared else 0)
                output.extend(_u32(array.shared_slot if array.shared else 0xFFFFFFFF))
        for statement in function.statements:
            output.extend(_encode_statement(statement, function_slots, local_slots,
                                            array_slots, function.symbol_id))
    output.extend(_u32(target_index))
    output.extend(_u32(len(arguments)))
    for value in arguments:
        output.extend(struct.pack("<d", value))
    return bytes(output)
