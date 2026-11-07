#!/usr/bin/env python3
"""OpenAI-compatible tool-calling trials over semantic and text tool arms."""
from __future__ import annotations

import argparse
import copy
import difflib
import json
import ipaddress
import os
from pathlib import Path
import statistics
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys_path = str(ROOT)
import sys
if sys_path not in sys.path:
    sys.path.insert(0, sys_path)
from basic_workspace.client import AgentToolAdapter, RpcError, WorkspaceClient
from basic_workspace.model import Workspace, WorkspaceError
from basic_workspace.mir_execution import MirExecutionService

RESULTS = ROOT / "results" / "llm-editing"
CORPUS = ROOT / "results" / "agent-editing" / "tasks.json"


def endpoint_metadata(value: str) -> dict[str, str]:
    parts = urlsplit(value)
    host = parts.hostname or ""
    try:
        addr = ipaddress.ip_address(host)
        category = "loopback" if addr.is_loopback else "private" if addr.is_private else "public"
    except ValueError:
        category = "local" if host.endswith((".local", ".localhost")) or host == "localhost" else "named-host"
    return {"scheme": parts.scheme, "host_class": category,
            "api_path": "chat/completions" if parts.path.endswith("/chat/completions") else "configured"}


def schema(name: str, description: str, props: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "function", "function": {"name": name, "description": description,
            "parameters": {"type": "object", "properties": props, "required": required,
                           "additionalProperties": False}}}


STR = {"type": "string"}
INT = {"type": "integer", "minimum": 0}
BOOL = {"type": "boolean"}
SEMANTIC_OPERATION = {"oneOf": [
    {"type": "object", "properties": {"operation": {"const": "rename_symbol"}, "symbol_id": STR, "new_name": STR}, "required": ["operation", "symbol_id", "new_name"], "additionalProperties": False},
    {"type": "object", "properties": {"operation": {"const": "renumber_line"}, "old_line": {"type": "integer"}, "new_line": {"type": "integer"}}, "required": ["operation", "old_line", "new_line"], "additionalProperties": False},
    {"type": "object", "properties": {"operation": {"const": "move_function"}, "symbol_id": STR, "before_symbol_id": {"type": ["string", "null"]}}, "required": ["operation", "symbol_id"], "additionalProperties": False},
]}
SEMANTIC_TOOLS = [
    schema("workspace_open", "Open source text in the in-memory BASIC workspace.",
           {"text": STR, "uri": STR}, ["text"]),
    schema("workspace_symbols", "Filter and page discovered BASIC symbols. IDs returned here can be used in edits.",
           {"kind": STR, "name_query": STR, "exact_name": STR, "unique": BOOL, "scope_id": STR, "offset": INT, "limit": {"type": "integer", "minimum": 1, "maximum": 100}}, []),
    schema("workspace_structure", "Get a bounded summary of lines, functions, labels, revision and diagnostics.",
           {"offset": INT, "limit": {"type": "integer", "minimum": 1, "maximum": 100}}, []),
    schema("workspace_references", "Get references to a symbol ID discovered in this document.",
           {"symbol_id": STR, "offset": INT, "limit": {"type": "integer", "minimum": 1, "maximum": 100}}, ["symbol_id"]),
    schema("workspace_preview", "Validate a semantic transaction on a private snapshot; preview does not reserve a revision. Before renumber_line, discover the exact line with workspace_symbols(kind=line_label, exact_name=old_line, unique=true) or workspace_structure.",
           {"expected_revision": INT, "operations": {"type": "array", "items": SEMANTIC_OPERATION}, "include_diff": BOOL}, ["expected_revision", "operations"]),
    schema("workspace_commit", "Revalidate and atomically commit semantic operations at the expected revision.",
           {"expected_revision": INT, "operations": {"type": "array", "items": SEMANTIC_OPERATION}}, ["expected_revision", "operations"]),
    schema("workspace_diagnostics", "Return current parser and semantic diagnostics.", {}, []),
    schema("workspace_render", "Explicitly export a bounded rendering of the current in-memory source.",
           {"max_chars": {"type": "integer", "minimum": 1, "maximum": 20000}}, []),
]

TEXT_TOOLS = [
    schema("read_source", "Read the in-memory BASIC buffer, optionally one-based line range.",
           {"start_line": INT, "end_line": INT, "max_chars": {"type": "integer", "minimum": 1, "maximum": 20000}}, []),
    schema("search_text", "Search source text and return bounded matching lines with context.",
           {"query": STR, "case_sensitive": BOOL, "context_lines": {"type": "integer", "minimum": 0, "maximum": 5}}, ["query"]),
    schema("apply_patch", "Replace one unique exact source context. Supply the observed buffer version; stale or ambiguous patches fail without mutation.",
           {"expected_version": INT, "old_text": STR, "new_text": STR}, ["expected_version", "old_text", "new_text"]),
    schema("inspect_diff", "Show the unified diff from the original buffer.", {}, []),
    schema("text_diagnostics", "Run the BASIC subset diagnostics on the current buffer without changing it.", {}, []),
    schema("validate_program", "Validate current buffer with the available BASIC subset parser; no compilation side effects.", {}, []),
]

EXPRESSION_SCHEMA = {"type": "object", "properties": {
    "kind": {"type": "string", "enum": ["number", "symbol_ref", "local_ref", "unary", "binary", "call"]},
    "value": {"type": "number"}, "symbol_id": STR, "function_id": STR, "name": STR,
    "operator": {"type": "string", "enum": ["+", "-", "*", "/"]},
    "left": {"type": "object"}, "right": {"type": "object"},
    "operand": {"type": "object"},
    "arguments": {"type": "array", "items": {"type": "object"}},
}, "required": ["kind"], "additionalProperties": False,
    "description": "Typed expression object: number(value), symbol_ref(symbol_id), unary(operator,operand), binary(operator,left,right), call(function_id,arguments). No source strings."}

CONSTRUCTION_SEMANTIC_TOOLS = [
    schema("workspace_structure", "Discover functions, line labels, revision, and diagnostics without returning source text.",
           {"offset": INT, "limit": {"type": "integer", "minimum": 1, "maximum": 100}}, []),
    schema("workspace_symbols", "Filter and discover semantic symbols and their opaque IDs.",
           {"kind": STR, "exact_name": STR, "unique": BOOL, "scope_id": STR,
            "offset": INT, "limit": {"type": "integer", "minimum": 1, "maximum": 100}}, []),
    schema("workspace_create_function", "Atomically create a complete numeric FUNCTION and body in one revision. In expression/local initializer trees use local_ref(name) for parameters or earlier locals declared by this request. Returns stable function, parameter, local, and statement IDs.",
           {"expected_revision": INT, "name": STR,
            "parameters": {"type": "array", "items": STR, "maxItems": 6},
            "expression": EXPRESSION_SCHEMA,
            "locals": {"type": "array", "maxItems": 16, "items": {"type": "object",
                "properties": {"name": STR, "expression": EXPRESSION_SCHEMA},
                "required": ["name", "expression"], "additionalProperties": False}}},
           ["expected_revision", "name", "parameters", "expression"]),
    schema("workspace_statements", "Discover bounded assignment statements in a discovered function, including stable IDs and referenced symbols.",
           {"function_id": STR, "offset": INT, "limit": {"type": "integer", "minimum": 1, "maximum": 200}}, ["function_id"]),
    schema("workspace_edit_expression", "Replace only a discovered assignment's typed right-hand expression; commits one revision atomically.",
           {"expected_revision": INT, "statement_id": STR, "expression": EXPRESSION_SCHEMA},
           ["expected_revision", "statement_id", "expression"]),
    schema("workspace_insert_assignment", "Insert a numeric local or function-result assignment at the end of a function or before a discovered statement.",
           {"expected_revision": INT, "function_id": STR,
            "target": {"type": "object", "properties": {"kind": {"type": "string", "enum": ["local", "result"]}, "name": STR}, "required": ["kind"], "additionalProperties": False},
            "expression": EXPRESSION_SCHEMA, "before_statement_id": STR},
           ["expected_revision", "function_id", "target", "expression"]),
    schema("workspace_execute_function", "Compile the current committed revision to MIR and execute a discovered numeric function using interp or jit.",
           {"expected_revision": INT, "function_id": STR,
            "arguments": {"type": "array", "items": {"type": "number"}},
            "engine": {"type": "string", "enum": ["interp", "jit"]}},
           ["expected_revision", "function_id", "arguments"]),
]

CONSTRUCTION_TEXT_TOOLS = TEXT_TOOLS + [
    schema("write_source", "Generate the initial BASIC source into the empty in-memory text buffer. Use no filesystem.",
           {"expected_version": INT, "source": STR}, ["expected_version", "source"]),
    schema("execute_program", "Compile the in-memory source with the same numeric BASIC/MIR subset as the semantic arm and execute a named numeric function.",
           {"function": STR, "arguments": {"type": "array", "items": {"type": "number"}},
            "engine": {"type": "string", "enum": ["interp", "jit"]}},
           ["function", "arguments", "engine"]),
]


class ChatEndpoint:
    def __init__(self, endpoint: str, model: str, api_key: str | None,
                 temperature: float, max_output_tokens: int, timeout: float,
                 seed: int | None, think: bool | None = None):
        self.endpoint, self.model, self.api_key = endpoint, model, api_key
        self.temperature, self.max_output_tokens = temperature, max_output_tokens
        self.timeout, self.seed, self.think = timeout, seed, think
        self.last_request_bytes = 0
        self.last_response_bytes = 0
        self.last_elapsed_ms = 0.0

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> tuple[dict[str, Any], float]:
        payload: dict[str, Any] = {"model": self.model, "messages": messages,
            "tools": tools, "tool_choice": "auto", "temperature": self.temperature,
            "max_tokens": self.max_output_tokens}
        if self.seed is not None:
            payload["seed"] = self.seed
        if self.think is not None:
            payload["think"] = self.think
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.last_request_bytes = len(body)
        self.last_response_bytes = 0
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = "Bearer " + self.api_key
        request = Request(self.endpoint, data=body, headers=headers, method="POST")
        started = time.perf_counter()
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read(8 * 1024 * 1024 + 1)
                self.last_response_bytes = len(raw)
                if len(raw) > 8 * 1024 * 1024:
                    raise RuntimeError("completion response exceeded 8 MiB")
                parsed = json.loads(raw)
        except HTTPError as exc:
            # Never include request headers or credentials in diagnostics.
            detail = exc.read(2000).decode("utf-8", "replace")
            raise RuntimeError(f"completion endpoint HTTP {exc.code}: {detail}") from None
        except URLError as exc:
            raise RuntimeError(f"completion endpoint unavailable: {exc.reason}") from None
        finally:
            self.last_elapsed_ms = (time.perf_counter() - started) * 1000
        return parsed, self.last_elapsed_ms


class ToolRunner:
    def __init__(self, arm: str, client: WorkspaceClient | None = None,
                 adapter: AgentToolAdapter | None = None, source: str = ""):
        self.arm, self.client, self.adapter = arm, client, adapter
        self.initial_source = source
        self.buffer = source
        self.original = source
        self.version = 1
        self.failed_calls = 0
        self.patch_attempts = 0
        self.repair_cycles = 0
        self.tool_time_ms = 0.0
        self.tool_calls = 0
        self.tool_errors: list[dict[str, Any]] = []
        self._previous_patch_failed = False
        self.block_commit = False
        self.require_stale_commit_revision: int | None = None
        self.stale_commit_rejected = False
        self.construction_stale_once = False
        self.construction_created: dict[str, Any] | None = None

    def call(self, name: str, arguments: dict[str, Any]) -> Any:
        started = time.perf_counter()
        self.tool_calls += 1
        try:
            if self.arm == "semantic":
                if not self.adapter:
                    raise RuntimeError("semantic adapter missing")
                if self.require_stale_commit_revision is not None and not self.stale_commit_rejected:
                    if name == "workspace_structure":
                        self.failed_calls += 1
                        result = {"ok": False, "code": "SCHEDULER_STALE_CHECK_REQUIRED",
                                  "message": "This agent has a prepared proposal based on revision "
                                  f"{self.require_stale_commit_revision}. Submit that proposal at its observed revision first; "
                                  "the scheduler will deliver the stale result before allowing a refresh."}
                        self.tool_errors.append(result)
                        return result
                    if name == "workspace_commit":
                        requested_revision = int(arguments.get("expected_revision", -1))
                        if requested_revision != self.require_stale_commit_revision:
                            self.failed_calls += 1
                            result = {"ok": False, "code": "SCHEDULER_BASE_REVISION_REQUIRED",
                                      "message": f"The prepared proposal is based on revision {self.require_stale_commit_revision}; "
                                      "attempt that revision before refreshing or rebasing."}
                            self.tool_errors.append(result)
                            return result
                if name == "workspace_commit" and self.block_commit:
                    self.failed_calls += 1
                    result = {"ok": False, "code": "SCHEDULER_HOLD",
                              "message": "The deterministic multi-agent scheduler has not released commits yet. Keep the proposal and wait."}
                    self.tool_errors.append(result)
                    return result
                if (self.construction_stale_once and name == "workspace_edit_expression"
                        and self.construction_created):
                    created = self.construction_created
                    parameter = next((x for x in created["created_entities"] if x["kind"] == "parameter"), None)
                    statement = next(iter(created.get("created_statements", [])), None)
                    if parameter and statement:
                        revision = self.client.revision
                        self.client._rpc("edit_assignment_expression", self.client._doc_params(
                            expected_revision=revision, statement_id=statement["statement_id"],
                            expression={"kind": "symbol_ref", "symbol_id": parameter["symbol_id"]}))
                        self.client.revision = revision + 1
                        self.construction_stale_once = False
                result = self.adapter.call(name, arguments)
                if name == "workspace_create_function":
                    self.construction_created = result
                if (self.arm == "semantic" and name == "workspace_commit" and
                        self.require_stale_commit_revision is not None and
                        isinstance(result, dict) and result.get("code") == "STALE_REVISION"):
                    self.stale_commit_rejected = True
            else:
                result = self._text_call(name, arguments)
            return result
        except (RpcError, WorkspaceError, ValueError, KeyError) as exc:
            self.failed_calls += 1
            error_code = getattr(exc, "code", "INVALID_ARGUMENT")
            if name == "workspace_commit" and error_code == "STALE_REVISION":
                self.stale_commit_rejected = True
            err = {"ok": False, "code": error_code,
                   "message": str(exc)}
            self.tool_errors.append(err)
            if name == "apply_patch":
                if self._previous_patch_failed:
                    self.repair_cycles += 1
                self._previous_patch_failed = True
            return err
        finally:
            self.tool_time_ms += (time.perf_counter() - started) * 1000

    def _text_call(self, name: str, a: dict[str, Any]) -> Any:
        if name == "write_source":
            expected = int(a["expected_version"])
            if expected != self.version:
                raise ValueError(f"STALE_VERSION: expected {expected}, current {self.version}")
            if self.buffer:
                raise ValueError("SOURCE_BUFFER_NOT_EMPTY")
            self.buffer = a["source"]
            self.version += 1
            reported_version = self.version
            if self.construction_stale_once:
                self.buffer += "' concurrent text edit\n"
                self.version += 1
                self.construction_stale_once = False
            return {"ok": True, "version": reported_version, "changed": True}
        if name == "read_source":
            lines = self.buffer.splitlines(keepends=True)
            start = max(1, int(a.get("start_line", 1)))
            end = min(len(lines), int(a.get("end_line", len(lines))))
            text = "".join(lines[start - 1:end])
            limit = min(20000, int(a.get("max_chars", 12000)))
            return {"version": self.version, "start_line": start, "end_line": end,
                    "text": text[:limit], "truncated": len(text) > limit,
                    "total_chars": len(text)}
        if name == "search_text":
            query = a["query"]
            case_sensitive = bool(a.get("case_sensitive", False))
            lines = self.buffer.splitlines()
            found = []
            for i, line in enumerate(lines):
                matches = query in line if case_sensitive else query.casefold() in line.casefold()
                if matches:
                    lo = max(0, i - int(a.get("context_lines", 1)))
                    hi = min(len(lines), i + int(a.get("context_lines", 1)) + 1)
                    found.append({"line": i + 1, "text": "\n".join(lines[lo:hi])})
            return {"version": self.version, "count": len(found), "matches": found[:100],
                    "truncated": len(found) > 100}
        if name == "apply_patch":
            self.patch_attempts += 1
            expected = int(a["expected_version"])
            if expected != self.version:
                raise ValueError(f"STALE_VERSION: expected {expected}, current {self.version}")
            old = a["old_text"]
            count = self.buffer.count(old)
            if not old:
                raise ValueError("EMPTY_PATCH_CONTEXT")
            if count != 1:
                raise ValueError(f"PATCH_CONTEXT_MATCH_COUNT: expected one exact context, found {count}")
            self.buffer = self.buffer.replace(old, a["new_text"], 1)
            self.version += 1
            self._previous_patch_failed = False
            return {"ok": True, "version": self.version, "changed": True}
        if name == "inspect_diff":
            return {"version": self.version, "diff": "".join(difflib.unified_diff(
                self.original.splitlines(keepends=True), self.buffer.splitlines(keepends=True),
                fromfile="before", tofile="after"))[:12000]}
        if name in ("text_diagnostics", "validate_program"):
            parser = Workspace()
            did = parser.open_document_from_string(self.buffer)["document_id"]
            diagnostics = parser.get_diagnostics(did)
            errors = [x for x in diagnostics if x["severity"] == "error"]
            return {"valid": not errors, "diagnostics": diagnostics[:100],
                    "diagnostics_truncated": len(diagnostics) > 100,
                    "buffer_version": self.version}
        if name == "execute_program":
            parser = Workspace()
            did = parser.open_document_from_string(self.buffer)["document_id"]
            structure = parser.get_document_structure(did)
            matches = [f for f in structure["functions"]
                       if f["name"].casefold() == str(a["function"]).casefold()]
            if len(matches) != 1:
                raise ValueError(f"EXPECTED_ONE_FUNCTION: found {len(matches)}")
            engine = a.get("engine", "interp")
            if engine not in ("interp", "jit"):
                raise ValueError("UNSUPPORTED_ENGINE")
            executed = MirExecutionService().execute_function(
                parser, did, parser.get_revision(did), matches[0]["symbol_id"],
                a["arguments"], engine)
            return {"buffer_version": self.version, "function": a["function"],
                    "engine": engine, "result": executed["result"]}
        raise ValueError(f"UNKNOWN_TEXT_TOOL: {name}")


def dispatch_tools(runner: ToolRunner, tool_calls: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    outputs, messages = [], []
    for call in tool_calls:
        fn = call.get("function", {})
        name = fn.get("name", "")
        try:
            raw_args = fn.get("arguments") or "{}"
            args = raw_args if isinstance(raw_args, dict) else json.loads(raw_args)
            if not isinstance(args, dict):
                raise ValueError("tool arguments must be an object")
            result = runner.call(name, args)
        except (json.JSONDecodeError, ValueError) as exc:
            runner.failed_calls += 1
            result = {"ok": False, "code": "INVALID_TOOL_ARGUMENTS", "message": str(exc)}
        content = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
        outputs.append({"tool_call_id": call.get("id"), "name": name,
                        "arguments": fn.get("arguments"), "result": result,
                        "response_bytes": len(content.encode())})
        messages.append({"role": "tool", "tool_call_id": call.get("id"),
                         "name": name, "content": content})
    return outputs, messages


def descriptions(task: dict[str, Any]) -> str:
    ident = task["id"]
    if task.get("construction"):
        return task["instruction"]
    if task.get("unsupported"):
        return ("Inspect this BASIC program. It contains an incomplete or ambiguous construct. "
                "Determine whether the requested operation can be supported safely. If the "
                "relationship is ambiguous or the program is incomplete, do not edit it; report why.")
    if task.get("reject"):
        kind, name = task["target"]
        return f"Rename the {kind} named {name} to {task['new_name']}. If that collides with an existing symbol, refuse without committing and explain the collision."
    if task.get("move"):
        return f"Move the BASIC function {task['target'][1]} before function {task['before'][1]}. Preserve the function body and identity."
    if task.get("conflict"):
        return "Rename parameter X to VALUE. This is a regular single-agent task in this arm."
    pieces = []
    if "target" in task:
        pieces.append(f"Rename the {task['target'][0]} named {task['target'][1]} to {task['new_name']}.")
    if "line" in task:
        pieces.append(f"Renumber BASIC line {task['line'][0]} to {task['line'][1]} and update its supported branch references.")
    pieces.append("Preserve unrelated identifiers, literals, comments, and formatting. Use only the provided editing tools.")
    return " ".join(pieces)


def source_text_payload_bytes(tool_calls: list[dict[str, Any]]) -> int:
    """Count source-bearing text fields returned by tools, including repeated reads."""
    total = 0
    for call in tool_calls:
        name, result = call.get("name"), call.get("result") or {}
        strings: list[str] = []
        if name == "read_source":
            strings.append(result.get("text", ""))
        elif name == "search_text":
            strings.extend(x.get("text", "") for x in result.get("matches", []))
        elif name == "inspect_diff":
            strings.append(result.get("diff", ""))
        elif name == "workspace_preview":
            strings.append(result.get("diff", ""))
        elif name == "workspace_references":
            strings.extend(x.get("text", "") for x in result.get("items", []))
        elif name == "workspace_symbols":
            strings.extend(x.get("name", "") for x in result.get("items", []))
            symbol = result.get("unique_symbol")
            if symbol:
                strings.append(symbol.get("name", ""))
        elif name == "workspace_structure":
            strings.extend(x.get("name", "") for x in result.get("functions", []))
            strings.extend(str(x.get("line", "")) for x in result.get("line_labels", []))
        elif name == "workspace_render":
            strings.append(result.get("text", ""))
        total += sum(len(s.encode("utf-8")) for s in strings)
    return total


SYSTEM_SEMANTIC = """Use only the exact structured tools listed. The document is loaded in a private in-memory workspace. There is no workspace_rename_symbol or text-replacement tool. For edits call workspace_preview/workspace_commit with operations such as {\"operation\":\"rename_symbol\",\"symbol_id\":\"...\",\"new_name\":\"...\"}; renumber_line uses old_line/new_line; move_function uses symbol_id/before_symbol_id. Discover symbols or labels before using IDs. For a unique match, workspace_symbols with exact_name and unique=true returns opaque ID, scope, type, reference count, revision and diagnostic counts together. Call workspace_references only when details are useful. Preview is optional but useful for multi-operation changes; commit revalidates revision. For collisions, ambiguity, incomplete source or stale revisions, refuse or inspect current state; never guess. Do not return a full source listing unless needed. Finish with whether you committed or refused."""
SYSTEM_TEXT = """You edit BASIC source through conventional in-memory text tools. Read/search source as needed, then use exact-context patches with the current buffer version. A patch must match exactly once; inspect the diff and diagnostics after editing. If a patch is stale or ambiguous, read/search again and repair carefully. For collisions, ambiguity, incomplete source, or stale revisions, refuse or inspect the current state; never guess. Do not use shell or filesystem access. Finish with a short result and whether you edited or refused."""

SYSTEM_CONSTRUCTION_SEMANTIC = """You author numeric BASIC programs using only the structured semantic tools. The host has already opened an empty workspace at revision 1. Create a complete function in one workspace_create_function call, including its typed result expression. Use local_ref(name) to refer to parameters and optional locals created by that same request; locals are declared in order and may refer only to parameters or earlier locals. Calls to already existing functions require their discovered IDs. Use only returned persistent symbol and statement IDs for later edits; never invent IDs or submit BASIC source strings. Other expression nodes are number, discovered symbol_ref, unary, binary, and call. Each mutation commits one revision and requires its current expected_revision. Execute the current revision with workspace_execute_function when requested. If a request refers to an unavailable identity or a stale revision, inspect the workspace and recover safely; refuse when the requested relationship cannot be established. Do not render source during construction."""
SYSTEM_CONSTRUCTION_TEXT = """You author a numeric BASIC program in an in-memory text buffer. Use supported FUNCTION declarations with numeric parameters and assignments to the function result. Use write_source for its initial source, then exact-context patches for changes. Run diagnostics and execute the named function with execute_program when requested; it compiles this buffer through the same numeric BASIC/MIR subset as the semantic arm. A stale or ambiguous patch must not be forced; refresh the current buffer/version and retry carefully. Do not use shell or filesystem access."""


def run_session(endpoint: ChatEndpoint, arm: str, task: dict[str, Any],
                runner: ToolRunner, max_calls: int, max_iterations: int,
                prompt_override: str | None = None,
                initial_messages: list[dict[str, Any]] | None = None,
                include_private: bool = False,
                max_context_bytes: int = 64000,
                construction: bool = False) -> dict[str, Any]:
    tools = (CONSTRUCTION_SEMANTIC_TOOLS if arm == "semantic" else CONSTRUCTION_TEXT_TOOLS) if construction else (SEMANTIC_TOOLS if arm == "semantic" else TEXT_TOOLS)
    visible_task = descriptions(task)
    if construction and arm == "semantic":
        visible_task = ("The host has opened an empty virtual document at revision 1. "
                        "Use it directly; it is already ready for construction.\n" + visible_task)
    messages: list[dict[str, Any]] = copy.deepcopy(initial_messages) if initial_messages else [
        {"role": "system", "content": (SYSTEM_CONSTRUCTION_SEMANTIC if arm == "semantic" else SYSTEM_CONSTRUCTION_TEXT) if construction else (SYSTEM_SEMANTIC if arm == "semantic" else SYSTEM_TEXT)},
        {"role": "user", "content": f"Task {task['id']}: {visible_task}"},
    ]
    if initial_messages is not None:
        messages.append({"role": "user", "content": prompt_override or "Continue the task."})
    elif prompt_override:
        messages[-1]["content"] = prompt_override
    trace: list[dict[str, Any]] = []
    model_wait_ms = 0.0
    provider_usage: dict[str, int] = {}
    provider_usage_turns = 0
    model_turns = 0
    model_request_attempts = 0
    schema_bytes = len(json.dumps(tools, separators=(",", ":")).encode())
    max_request_context_bytes = 0
    final_text = ""
    terminal = "iteration_limit"
    while model_turns < max_iterations and runner.tool_calls < max_calls:
        request_context_bytes = len(json.dumps({"messages": messages, "tools": tools},
                                                ensure_ascii=False, separators=(",", ":")).encode())
        max_request_context_bytes = max(max_request_context_bytes, request_context_bytes)
        if request_context_bytes > max_context_bytes:
            terminal = "context_byte_limit"
            break
        model_request_attempts += 1
        try:
            response, elapsed = endpoint.complete(messages, tools)
        except Exception as exc:
            elapsed = getattr(endpoint, "last_elapsed_ms", 0.0)
            model_wait_ms += elapsed
            trace.append({"turn": model_turns + 1,
                "request_bytes": getattr(endpoint, "last_request_bytes", 0),
                "response_wire_bytes": getattr(endpoint, "last_response_bytes", 0),
                "elapsed_ms": round(elapsed, 3), "finish_reason": None,
                "usage": None, "tool_calls": [],
                "endpoint_error": f"{type(exc).__name__}: {str(exc)[:500]}"})
            terminal = "endpoint_error"
            break
        model_wait_ms += elapsed
        model_turns += 1
        choice = response.get("choices", [{}])[0]
        message = choice.get("message", {})
        final_text = message.get("content") or ""
        usage = response.get("usage")
        if isinstance(usage, dict):
            provider_usage_turns += 1
            for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                if isinstance(usage.get(key), int):
                    provider_usage[key] = provider_usage.get(key, 0) + usage[key]
        # Reasoning-only fields are neither part of OpenAI tool-call history nor
        # needed by the agent; do not feed them back or persist them in traces.
        assistant_message = {k: v for k, v in message.items()
                             if v is not None and k not in ("reasoning", "reasoning_content")}
        messages.append(assistant_message)
        calls = message.get("tool_calls") or []
        trace_row: dict[str, Any] = {"turn": model_turns, "elapsed_ms": round(elapsed, 3),
            "request_bytes": endpoint.last_request_bytes,
            "response_wire_bytes": endpoint.last_response_bytes,
            "response_id": response.get("id"), "response_created": response.get("created"),
            "model": response.get("model"), "system_fingerprint": response.get("system_fingerprint"),
            "finish_reason": choice.get("finish_reason"), "usage": usage,
            "assistant_content": final_text, "tool_calls": []}
        if not calls:
            trace.append(trace_row)
            terminal = "finished"
            break
        remaining = max_calls - runner.tool_calls
        calls = calls[:remaining]
        outputs, tool_messages = dispatch_tools(runner, calls)
        trace_row["tool_calls"] = outputs
        trace.append(trace_row)
        messages.extend(tool_messages)
    else:
        if runner.tool_calls >= max_calls:
            terminal = "tool_call_limit"
    refusal_words = ("refus", "ambigu", "collid", "cannot", "unsupported", "incomplete",
                     "not safe", "must not", "should not", "won't", "will not")
    explicit_refusal = any(word in final_text.casefold() for word in refusal_words)
    construction_execution = None
    current = runner.buffer if arm == "text" else None
    if construction:
        construction_execution = {"engine_results": {}, "valid": False}
        if task.get("must_refuse"):
            if arm == "semantic":
                if runner.client.document_id is None:
                    unchanged = True
                else:
                    structure = runner.client.workspace_structure()
                    unchanged = not structure["functions"] and not structure["line_labels"]
                construction_execution.update({"valid": unchanged, "workspace_empty": unchanged})
            else:
                unchanged = runner.buffer == ""
                construction_execution.update({"valid": unchanged, "workspace_empty": unchanged})
            safe_outcome = unchanged and explicit_refusal
            correct = safe_outcome
            correct_text = None
        else:
            try:
                if arm == "semantic":
                    structure = runner.client.workspace_structure()
                    matching = [f for f in structure["functions"]
                                if f["name"].casefold() == task["function"].casefold()]
                    if len(matching) != 1:
                        raise RuntimeError(f"expected one {task['function']} definition, found {len(matching)}")
                    for engine_name in ("interp", "jit"):
                        executed = runner.client.workspace_execute_function(
                            runner.client.revision, matching[0]["symbol_id"],
                            task["arguments"], engine_name)
                        construction_execution["engine_results"][engine_name] = executed["result"]
                    current = runner.client.workspace_render()["text"]
                else:
                    oracle = Workspace()
                    opened = oracle.open_document_from_string(runner.buffer)
                    docid = opened["document_id"]
                    structure = oracle.get_document_structure(docid)
                    matching = [f for f in structure["functions"]
                                if f["name"].casefold() == task["function"].casefold()]
                    if len(matching) != 1:
                        raise RuntimeError(f"expected one {task['function']} definition, found {len(matching)}")
                    executor = MirExecutionService()
                    for engine_name in ("interp", "jit"):
                        executed = executor.execute_function(oracle, docid,
                            oracle.get_revision(docid), matching[0]["symbol_id"],
                            task["arguments"], engine_name)
                        construction_execution["engine_results"][engine_name] = executed["result"]
                target = float(task["expected_result"])
                correct = all(abs(float(value) - target) <= 1e-12
                              for value in construction_execution["engine_results"].values())
                correct = correct and set(construction_execution["engine_results"]) == {"interp", "jit"}
                construction_execution.update({"valid": bool(correct), "expected_result": target})
                correct_text = None
                safe_outcome = False
            except Exception as exc:
                construction_execution.update({"valid": False, "error": str(exc)[:1000]})
                correct, correct_text, safe_outcome = False, None, False
    else:
        if arm == "semantic":
            try:
                rendered = runner.client._rpc("render_document", {"document_id": runner.client.document_id})
                current = rendered[:20000]
            except Exception as exc:
                current = None
                trace.append({"evaluation_render_error": str(exc)})
        expect_unchanged = bool(task.get("reject") or task.get("unsupported"))
        correct_text = current == task["expected"]
        safe_outcome = (expect_unchanged and current == task["source"] and explicit_refusal)
        correct = safe_outcome if expect_unchanged else correct_text
    system_prompt = ((SYSTEM_CONSTRUCTION_SEMANTIC if arm == "semantic" else SYSTEM_CONSTRUCTION_TEXT)
                     if construction else (SYSTEM_SEMANTIC if arm == "semantic" else SYSTEM_TEXT))
    result = {"arm": arm, "task_id": task["id"], "status": terminal,
        "system_prompt": system_prompt,
        "user_prompt": prompt_override or f"Task {task['id']}: {visible_task}",
        "correct": bool(correct), "safe_refusal": bool(safe_outcome),
        "final_source_matches_oracle": None if correct_text is None else bool(correct_text),
        "construction_execution": construction_execution, "final_text": final_text,
        "final_revision": runner.client.revision if arm == "semantic" and runner.client else runner.version,
        "model_turns": model_turns, "model_tool_calls": runner.tool_calls,
        "model_request_attempts": model_request_attempts,
        "transaction_previews": sum(1 for turn in trace for c in turn.get("tool_calls", []) if c["name"] == "workspace_preview"),
        "transaction_commit_attempts": sum(1 for turn in trace for c in turn.get("tool_calls", []) if c["name"] == "workspace_commit"),
        "patch_attempts": runner.patch_attempts,
        "max_request_context_bytes": max_request_context_bytes,
        "failed_tool_calls": runner.failed_calls,
        "repair_cycles": runner.repair_cycles, "provider_usage": provider_usage or None,
        "provider_usage_records": provider_usage_turns,
        "provider_usage_complete": provider_usage_turns == model_turns and terminal != "endpoint_error",
        "schema_bytes": schema_bytes, "tool_response_bytes": sum(
            c.get("response_bytes", 0) for t in trace for c in t.get("tool_calls", [])),
        "tool_execution_ms": round(runner.tool_time_ms, 3),
        "source_text_payload_bytes": source_text_payload_bytes(
            [c for t in trace for c in t.get("tool_calls", [])]),
        "inference_wait_ms": round(model_wait_ms, 3), "wall_ms": round(model_wait_ms + runner.tool_time_ms, 3),
        "trace": trace}
    if include_private:
        result["_messages"] = messages
    return result


def load_tasks() -> list[dict[str, Any]]:
    return json.loads(CORPUS.read_text(encoding="utf-8"))


def run_actual(args: argparse.Namespace) -> dict[str, Any]:
    key = os.environ.get(args.api_key_env) if args.api_key_env else None
    endpoint = ChatEndpoint(args.endpoint_url, args.model, key, args.temperature,
                            args.max_output_tokens, args.request_timeout, args.seed, args.think)
    RESULTS.mkdir(parents=True, exist_ok=True)
    config = {"model_requested": args.model, "endpoint_metadata": endpoint_metadata(args.endpoint_url),
        "authentication_configured": bool(key), "api_key_env_name": args.api_key_env if key else None,
        "temperature": args.temperature, "max_output_tokens": args.max_output_tokens,
        "max_tool_calls_per_session": args.max_tool_calls,
        "max_iterations_per_session": args.max_iterations,
        "max_serialized_context_bytes_per_request": args.max_context_bytes,
        "request_timeout_seconds": args.request_timeout, "seed": args.seed,
        "think_mode": "on" if args.think is True else "off" if args.think is False else "endpoint-default",
        "arms": ["semantic", "text"], "source": "operator-configured endpoint"}
    (RESULTS / "tool-definitions.json").write_text(json.dumps(
        {"semantic": SEMANTIC_TOOLS, "text": TEXT_TOOLS}, indent=2, ensure_ascii=False) + "\n")
    tasks = load_tasks()
    if args.limit:
        tasks = tasks[:args.limit]
    all_trials: list[dict[str, Any]] = []
    started_batch = time.perf_counter()
    # One persistent workspace subprocess serves every semantic task; each gets a new document.
    with WorkspaceClient(timeout=args.tool_timeout, max_render_chars=20000) as client:
        for task in tasks:
            if task.get("conflict"):
                # It has a dedicated scheduled two-agent experiment below.
                continue
            for arm in ("semantic", "text"):
                if arm == "semantic":
                    # Fixture loading is setup, not a model tool call. Source is deliberately
                    # absent from agent-visible messages; the equivalent text buffer is seeded.
                    adapter = AgentToolAdapter(client)
                    opened = adapter.call("workspace_open", {"text": task["source"],
                        "uri": f"memory://llm/{task['id']}"})
                    runner = ToolRunner(arm, client=client, adapter=adapter, source=task["source"])
                    setup = {"opened_revision": opened["revision"], "source_bytes": len(task["source"].encode())}
                else:
                    runner = ToolRunner(arm, source=task["source"])
                    setup = {"buffer_version": 1, "source_bytes": len(task["source"].encode())}
                trial = run_session(endpoint, arm, task, runner, args.max_tool_calls,
                                    args.max_iterations, max_context_bytes=args.max_context_bytes)
                trial["setup"] = setup
                trial["source_chars"] = len(task["source"])
                trial["source_bytes"] = len(task["source"].encode())
                trial["task_category"] = ("conflict" if task.get("conflict") else
                    "ambiguous" if task.get("unsupported") == "AMBIGUOUS_CALL_OR_ARRAY" else
                    "incomplete_or_unsupported" if task.get("unsupported") else
                    "must_reject" if task.get("reject") else "valid")
                all_trials.append(trial)
                checkpoint = {"configuration": config, "summary": summarize(all_trials),
                              "trials": all_trials,
                              "status": "in_progress", "multi_agent": "pending"}
                (RESULTS / "run.json").write_text(json.dumps(checkpoint, indent=2, ensure_ascii=False) + "\n")
    summary = summarize(all_trials)
    result = {"status": "completed", "configuration": config, "summary": summary,
              "batch_wall_ms": round((time.perf_counter() - started_batch) * 1000, 3),
              "trials": all_trials,
              "multi_agent": "run with --multi-agent separately after task trials"}
    (RESULTS / "run.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    (RESULTS / "config.json").write_text(json.dumps(config, indent=2) + "\n")
    (RESULTS / "SUMMARY.md").write_text(markdown(result))
    return result


def run_multi_agent(endpoint: ChatEndpoint, args: argparse.Namespace) -> dict[str, Any]:
    """Two genuine model sessions share one server/document and race one revision."""
    source = "FUNCTION F(X)\nF=X\nEND FUNCTION\n"
    task_a = {"id": "multi_agent_A", "source": source,
              "expected": "FUNCTION F(POINTS)\nF=POINTS\nEND FUNCTION\n", "target": ["parameter", "X"],
              "new_name": "POINTS"}
    task_b = {"id": "multi_agent_B", "source": source,
              "expected": "FUNCTION F(VALUE)\nF=VALUE\nEND FUNCTION\n", "target": ["parameter", "X"],
              "new_name": "VALUE"}
    with WorkspaceClient(timeout=args.tool_timeout, max_render_chars=20000) as client:
        adapter_a = AgentToolAdapter(client)
        opened = adapter_a.call("workspace_open", {"text": source, "uri": "memory://llm/multi-agent"})
        adapter_b = adapter_a.fork()
        runner_a = ToolRunner("semantic", client=client, adapter=adapter_a, source=source)
        runner_b = ToolRunner("semantic", client=client, adapter=adapter_b, source=source)
        runner_a.block_commit = runner_b.block_commit = True
        phase_a = run_session(endpoint, "semantic", task_a, runner_a, args.max_tool_calls,
            args.max_iterations,
            prompt_override="Agent A: discover parameter X and prepare a rename to POINTS. Inspect references and preview the operation if useful. Do not commit yet; report that you are waiting for the scheduler.",
            include_private=True, max_context_bytes=args.max_context_bytes)
        phase_b = run_session(endpoint, "semantic", task_b, runner_b, args.max_tool_calls,
            args.max_iterations,
            prompt_override="Agent B: independently discover parameter X in the already loaded shared document and prepare a rename to VALUE. Inspect references and preview if useful. Do not commit yet; report that you are waiting for the scheduler.",
            include_private=True, max_context_bytes=args.max_context_bytes)
        runner_a.block_commit = False
        commit_a = run_session(endpoint, "semantic", task_a, runner_a, args.max_tool_calls,
            args.max_iterations, prompt_override="The scheduler releases Agent A now. Commit the already previewed POINTS transaction at the revision you observed. Do not change the proposal.",
            initial_messages=phase_a["_messages"], max_context_bytes=args.max_context_bytes)
        runner_b.block_commit = False
        runner_b.require_stale_commit_revision = opened["revision"]
        commit_b = run_session(endpoint, "semantic", task_b, runner_b, args.max_tool_calls,
            args.max_iterations, prompt_override=f"The scheduler now delivers Agent B's previously prepared VALUE transaction based on revision {opened['revision']}. First attempt workspace_commit using that exact observed revision, before any structure or symbol refresh. If the server rejects it as stale, inspect the new revision and symbols; explicitly decide whether to refuse or revise. Do not silently resubmit against a new revision.",
            initial_messages=phase_b["_messages"], max_context_bytes=args.max_context_bytes)
        final_source = client._rpc("render_document", {"document_id": client.document_id})
        stale_seen = any(e.get("code") == "STALE_REVISION" for e in runner_b.tool_errors)
        a_committed = any(call["name"] == "workspace_commit" and
                          isinstance(call["result"], dict) and call["result"].get("committed")
                          for turn in commit_a.get("trace", []) for call in turn.get("tool_calls", []))
        b_decision = "revised" if stale_seen and "VALUE" in final_source else "refused_or_left_stale"
        details = {"document_id": client.document_id, "initial_revision": opened["revision"],
            "final_revision": client.revision, "agent_a_committed_first": a_committed,
            "agent_b_received_stale_rejection": stale_seen, "agent_b_decision": b_decision,
            "final_source": final_source, "agent_a": {k: v for k, v in phase_a.items() if k != "_messages"},
            "agent_b": {k: v for k, v in phase_b.items() if k != "_messages"},
            "agent_a_commit_phase": commit_a, "agent_b_commit_phase": commit_b,
            "shared_process": True, "workspace_process_requests": client.metrics}
    return details


def summarize(trials: list[dict[str, Any]]) -> dict[str, Any]:
    result = {}
    for arm in ("semantic", "text"):
        rows = [x for x in trials if x["arm"] == arm]
        result[arm] = {"attempted": len(rows), "correct": sum(x["correct"] for x in rows),
            "safe_refusals": sum(x["safe_refusal"] for x in rows),
            "model_turns": sum(x["model_turns"] for x in rows),
            "model_request_bytes": sum(sum(t.get("request_bytes", 0) for t in x.get("trace", [])) for x in rows),
            "model_response_wire_bytes": sum(sum(t.get("response_wire_bytes", 0) for t in x.get("trace", [])) for x in rows),
            "tool_calls": sum(x["model_tool_calls"] for x in rows),
            "failed_tool_calls": sum(x["failed_tool_calls"] for x in rows),
            "patch_attempts": sum(x["patch_attempts"] for x in rows),
            "transaction_previews": sum(x.get("transaction_previews", 0) for x in rows),
            "transaction_commit_attempts": sum(x.get("transaction_commit_attempts", 0) for x in rows),
            "repair_cycles": sum(x["repair_cycles"] for x in rows),
            "schema_bytes": sum(x["schema_bytes"] for x in rows),
            "schema_bytes_sent_estimate": sum(x["schema_bytes"] * x["model_turns"] for x in rows),
            "tool_response_bytes": sum(x["tool_response_bytes"] for x in rows),
            "source_text_payload_bytes": sum(x.get("source_text_payload_bytes", 0) for x in rows),
            "inference_wait_ms": round(sum(x["inference_wait_ms"] for x in rows), 3),
            "tool_execution_ms": round(sum(x["tool_execution_ms"] for x in rows), 3),
            "mean_wall_ms": round(statistics.mean(x["wall_ms"] for x in rows), 3) if rows else None,
            "median_wall_ms": round(statistics.median(x["wall_ms"] for x in rows), 3) if rows else None,
            "provider_prompt_tokens": sum((x.get("provider_usage") or {}).get("prompt_tokens", 0) for x in rows),
            "provider_completion_tokens": sum((x.get("provider_usage") or {}).get("completion_tokens", 0) for x in rows),
            "provider_token_records": sum(bool(x.get("provider_usage")) for x in rows)}
    return result


def markdown(result: dict[str, Any]) -> str:
    cfg, summary = result["configuration"], result["summary"]
    out = ["# Actual LLM BASIC editing trials\n\n",
        f"Model requested: `{cfg['model_requested']}`. Endpoint class: `{cfg['endpoint_metadata']}`.\n\n",
        "These are actual endpoint trials; usage fields are provider-reported only.\n\n",
        "| Arm | Correct / attempted | Turns | Tool calls | Failed calls | Prompt tokens | Completion tokens | Source-text bytes | Tool output bytes | Request bytes | Response bytes | Inference ms | Tool ms |\n",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|\n"]
    for arm in ("semantic", "text"):
        s = summary[arm]
        tok_in = str(s["provider_prompt_tokens"]) if s["provider_token_records"] else "unknown"
        tok_out = str(s["provider_completion_tokens"]) if s["provider_token_records"] else "unknown"
        out.append(f"| {arm} | {s['correct']} / {s['attempted']} | {s['model_turns']} | {s['tool_calls']} | {s['failed_tool_calls']} | {tok_in} | {tok_out} | {s['source_text_payload_bytes']} | {s['tool_response_bytes']} | {s['model_request_bytes']} | {s['model_response_wire_bytes']} | {s['inference_wait_ms']} | {s['tool_execution_ms']} |\n")
    out.append("\nSee `run.json` for each task, exact settings, usage metadata and raw model/tool trace.\n")
    return "".join(out)


def fixture_test() -> dict[str, Any]:
    """Offline protocol check with a fake OpenAI response; not a model result."""
    class FixtureEndpoint:
        model = "fixture-model"
        def __init__(self):
            self.n = 0
            self.last_request_bytes = 128
            self.last_response_bytes = 128
        def complete(self, messages, tools):
            self.n += 1
            if self.n == 1:
                msg = {"role": "assistant", "content": None, "tool_calls": [{"id": "call1",
                    "type": "function", "function": {"name": "read_source", "arguments": "{}"}}]}
                return {"model": "fixture-model", "choices": [{"message": msg, "finish_reason": "tool_calls"}],
                        "usage": {"prompt_tokens": 23, "completion_tokens": 5}}, 0.01
            msg = {"role": "assistant", "content": "I inspected the source and will leave it unchanged."}
            return {"model": "fixture-model", "choices": [{"message": msg, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 31, "completion_tokens": 10}}, 0.01
    task = {"id": "fixture", "source": "10 END\n", "expected": "10 END\n", "unsupported": "fixture"}
    runner = ToolRunner("text", source=task["source"])
    result = run_session(FixtureEndpoint(), "text", task, runner, 4, 4)
    return {"protocol_pass": result["model_turns"] == 2 and result["model_tool_calls"] == 1,
            "not_an_llm_trial": True, "provider_usage": result["provider_usage"],
            "failed_calls": result["failed_tool_calls"]}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--endpoint-url", default=os.environ.get("BASIC_WS_CHAT_COMPLETIONS_URL"),
                   help="Complete OpenAI-compatible /chat/completions URL")
    p.add_argument("--model", default=os.environ.get("BASIC_WS_MODEL"), help="Explicit model ID")
    p.add_argument("--api-key-env", default="OPENAI_API_KEY",
                   help="Name of environment variable containing the API key (value is never logged)")
    p.add_argument("--no-api-key", action="store_true", help="Do not attach an API key")
    p.add_argument("--temperature", type=float, default=0.0)
    p.add_argument("--max-output-tokens", type=int, default=1024)
    p.add_argument("--max-tool-calls", type=int, default=16)
    p.add_argument("--max-iterations", type=int, default=12)
    p.add_argument("--max-context-bytes", type=int, default=64000,
                   help="Hard cap on serialized messages plus tool schemas per request")
    p.add_argument("--request-timeout", type=float, default=180)
    p.add_argument("--tool-timeout", type=float, default=10)
    p.add_argument("--seed", type=int, default=None,
                   help="Optional seed; omit when the configured endpoint does not support it")
    p.add_argument("--think", choices=("on", "off", "endpoint-default"), default="endpoint-default",
                   help="Optional endpoint-specific think flag; omitted unless explicitly selected")
    p.add_argument("--fixture-test", action="store_true", help="Run offline protocol fixture; never calls a model")
    p.add_argument("--multi-agent-only", action="store_true", help="Run the scheduled shared-revision multi-agent trial")
    p.add_argument("--limit", type=int, default=None, help="Limit tasks for a pilot run")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if args.fixture_test:
        print(json.dumps(fixture_test(), indent=2))
        return 0
    if not args.endpoint_url or not args.model:
        print(json.dumps({"real_trials": "not_run", "reason": "endpoint URL and model must be configured explicitly"}, indent=2))
        return 2
    args.endpoint_url = args.endpoint_url.rstrip("/")
    if not args.endpoint_url.endswith("/chat/completions"):
        args.endpoint_url += "/chat/completions"
    args.api_key_env = None if args.no_api_key else args.api_key_env
    args.think = True if args.think == "on" else False if args.think == "off" else None
    args._task_limit = args.limit
    if args.multi_agent_only:
        key = os.environ.get(args.api_key_env) if args.api_key_env else None
        endpoint = ChatEndpoint(args.endpoint_url, args.model, key, args.temperature,
                                args.max_output_tokens, args.request_timeout, args.seed, args.think)
        result = run_multi_agent(endpoint, args)
        RESULTS.mkdir(parents=True, exist_ok=True)
        result = {"configuration": {"model_requested": args.model,
            "endpoint_metadata": endpoint_metadata(args.endpoint_url),
            "authentication_configured": bool(key), "temperature": args.temperature,
            "max_output_tokens": args.max_output_tokens, "max_tool_calls_per_agent": args.max_tool_calls,
            "max_iterations_per_phase": args.max_iterations, "request_timeout_seconds": args.request_timeout,
            "seed": args.seed, "think_mode": "on" if args.think is True else "off" if args.think is False else "endpoint-default"}, "result": result}
        (RESULTS / "multi-agent.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
        print(json.dumps({k: v for k, v in result.items() if k not in ("agent_a", "agent_b", "agent_a_commit_phase", "agent_b_commit_phase")}, indent=2))
        return 0
    # A cheap live capability check using the configured model and schema is deliberately
    # not counted as a task trial. Actual requests begin in run_actual.
    result = run_actual(args)
    print(json.dumps(result["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
