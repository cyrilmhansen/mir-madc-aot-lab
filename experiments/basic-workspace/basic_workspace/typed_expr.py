"""Typed numeric expression requests shared by construction and MIR projection."""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping

from .model import WorkspaceError


@dataclass(frozen=True)
class Expr:
    kind: str
    value: str | float | None = None
    children: tuple["Expr", ...] = ()


def parse_request(value: Any, symbols: Mapping[str, Any], current_scope: str,
                  current_function_id: str, function_parameters: Mapping[str, int],
                  depth: int = 0, max_depth: int = 64) -> tuple[Expr, tuple[str, ...]]:
    """Validate a JSON expression without accepting or parsing source text.

    Returns a projection Expr plus the semantic IDs referenced by the request,
    in token emission order. This binding list is checked again after reindex.
    """
    if depth > max_depth:
        raise WorkspaceError("EXPRESSION_TOO_DEEP", f"Expression depth exceeds {max_depth}")
    if not isinstance(value, dict) or not isinstance(value.get("kind"), str):
        raise WorkspaceError("INVALID_EXPRESSION", "Expression must be a typed object with a kind")
    kind = value["kind"]
    if kind == "string":
        if set(value) != {"kind", "value"} or not isinstance(value["value"], str):
            raise WorkspaceError("INVALID_STRING", "string expression requires a string value")
        try:
            encoded = value["value"].encode("utf-8", "strict")
        except UnicodeError as exc:
            raise WorkspaceError("INVALID_UTF8", "String values must be valid UTF-8") from exc
        if b"\0" in encoded or b"\n" in encoded or b"\r" in encoded:
            raise WorkspaceError("INVALID_STRING", "String literals cannot contain NUL or line breaks")
        if len(encoded) > 4096:
            raise WorkspaceError("STRING_LIMIT", "String literals are limited to 4096 UTF-8 bytes")
        return Expr("string", value["value"]), ()
    if kind == "number":
        if set(value) != {"kind", "value"}:
            raise WorkspaceError("INVALID_EXPRESSION", "number expression requires only kind and value")
        number = value["value"]
        if isinstance(number, bool) or not isinstance(number, (int, float)):
            raise WorkspaceError("INVALID_EXPRESSION", "Numeric constants must be JSON numbers")
        number = float(number)
        if not math.isfinite(number):
            raise WorkspaceError("NON_FINITE_CONSTANT", "Numeric constants must be finite")
        return Expr("number", number), ()
    if kind == "symbol_ref":
        if set(value) != {"kind", "symbol_id"} or not isinstance(value["symbol_id"], str):
            raise WorkspaceError("INVALID_EXPRESSION", "symbol_ref requires only a symbol_id")
        sid = value["symbol_id"]
        symbol = symbols.get(sid)
        if symbol is None:
            raise WorkspaceError("SYMBOL_NOT_FOUND", "Expression refers to an unknown symbol identity")
        if symbol.kind == "array":
            raise WorkspaceError("UNSUPPORTED_TYPE", f"{symbol.name} requires an indexed expression")
        if symbol.name.endswith("$"):
            if sid == current_function_id and symbol.kind == "function":
                return Expr("result_string", sid), (sid,)
            if symbol.kind not in ("parameter", "variable") or symbol.scope_id != current_scope:
                raise WorkspaceError("CROSS_SCOPE_REFERENCE", f"{symbol.name} is outside the edited function scope")
            return Expr("variable_string", sid), (sid,)
        if symbol.kind == "function" and sid != current_function_id:
            raise WorkspaceError("UNSUPPORTED_TYPE", f"{symbol.name} is not a numeric local value")
        if sid == current_function_id:
            if symbol.kind != "function":
                raise WorkspaceError("UNSUPPORTED_TYPE", "Invalid function result reference")
            return Expr("result", sid), (sid,)
        if symbol.kind not in ("parameter", "variable"):
            raise WorkspaceError("UNSUPPORTED_TYPE", f"{symbol.name} cannot be used as a numeric value")
        if symbol.scope_id != current_scope:
            raise WorkspaceError("CROSS_SCOPE_REFERENCE", f"{symbol.name} is outside the edited function scope")
        return Expr("variable", sid), (sid,)
    if kind == "unary":
        if set(value) != {"kind", "operator", "operand"} or value["operator"] not in ("+", "-"):
            raise WorkspaceError("INVALID_OPERATOR", "unary supports only + or - and requires operand")
        child, refs = parse_request(value["operand"], symbols, current_scope,
                                    current_function_id, function_parameters, depth + 1, max_depth)
        result = child if value["operator"] == "+" else Expr("unary_minus", children=(child,))
        return result, refs
    if kind == "binary":
        if set(value) != {"kind", "operator", "left", "right"} or value["operator"] not in (
                "+", "-", "*", "/", "=", "<>", "<", "<=", ">", ">="):
            raise WorkspaceError("INVALID_OPERATOR", "binary requires an arithmetic or numeric comparison operator and left/right expressions")
        left, left_refs = parse_request(value["left"], symbols, current_scope,
                                        current_function_id, function_parameters, depth + 1, max_depth)
        right, right_refs = parse_request(value["right"], symbols, current_scope,
                                          current_function_id, function_parameters, depth + 1, max_depth)
        result_kind = "compare" if value["operator"] in ("=", "<>", "<", "<=", ">", ">=") else "binary"
        return Expr(result_kind, value["operator"], (left, right)), left_refs + right_refs
    if kind == "call":
        if set(value) != {"kind", "function_id", "arguments"}:
            raise WorkspaceError("INVALID_EXPRESSION", "call requires only function_id and arguments")
        callee_id, args = value["function_id"], value["arguments"]
        callee = symbols.get(callee_id) if isinstance(callee_id, str) else None
        if callee is None:
            raise WorkspaceError("SYMBOL_NOT_FOUND", "Call refers to an unknown function identity")
        if callee.kind != "function" or callee.name.endswith("$") or callee.document_id != symbols[current_function_id].document_id:
            raise WorkspaceError("UNSUPPORTED_TYPE", "Call target must be a numeric FUNCTION in this document")
        if not isinstance(args, list) or len(args) != function_parameters.get(callee_id):
            raise WorkspaceError("ARGUMENT_COUNT", f"Function {callee.name} expects {function_parameters.get(callee_id)} arguments")
        if len(args) > 6:
            raise WorkspaceError("UNSUPPORTED_ARITY", "Numeric calls support at most six arguments")
        children: list[Expr] = []
        refs: list[str] = [callee_id]
        for arg in args:
            child, child_refs = parse_request(arg, symbols, current_scope,
                                              current_function_id, function_parameters, depth + 1, max_depth)
            children.append(child)
            refs.extend(child_refs)
        return Expr("call", callee_id, tuple(children)), tuple(refs)
    if kind == "array_element":
        if set(value) != {"kind", "array_ref", "index"}:
            raise WorkspaceError("INVALID_EXPRESSION", "array_element requires kind, array_ref, and index")
        array_ref = value["array_ref"]
        if (not isinstance(array_ref, dict) or set(array_ref) != {"kind", "symbol_id"}
                or array_ref.get("kind") != "symbol_ref" or not isinstance(array_ref["symbol_id"], str)):
            raise WorkspaceError("INVALID_ARRAY_REFERENCE", "array_ref must contain a discovered array symbol identity")
        array_id = array_ref["symbol_id"]
        array = symbols.get(array_id)
        if array is None or array.kind != "array":
            raise WorkspaceError("UNSUPPORTED_TYPE", "array_element must reference a declared array")
        if array.scope_id not in (current_scope, "module"):
            raise WorkspaceError("CROSS_SCOPE_REFERENCE", f"Array {array.name} is outside the current function scope")
        index, index_refs = parse_request(value["index"], symbols, current_scope,
                                          current_function_id, function_parameters,
                                          depth + 1, max_depth)
        if index.kind not in ("number", "variable", "result", "unary_minus", "binary", "call", "array_element"):
            raise WorkspaceError("UNSUPPORTED_TYPE", "Array indexes must be numeric")
        return Expr("array_element_string" if array.name.endswith("$") else "array_element",
                    array_id, (index,)), (array_id,) + index_refs
    raise WorkspaceError("UNSUPPORTED_EXPRESSION", f"Unsupported expression kind {kind!r}")


def expression_tokens(expr: Expr, symbols: Mapping[str, Any]) -> tuple[list[tuple[str, str]], tuple[str, ...]]:
    """Serialize a validated expression to canonical token kind/text pairs."""
    if expr.kind == "number":
        number = float(expr.value)
        negative = number < 0 or number == 0 and math.copysign(1.0, number) < 0
        magnitude = abs(number)
        text = str(int(magnitude)) if magnitude.is_integer() and magnitude < 1e16 else repr(magnitude)
        parts = ([ ("OP", "-") ] if negative else []) + [("NUMBER", text)]
        return parts, ()
    if expr.kind == "string":
        return [("STRING", '"' + str(expr.value).replace('"', '""') + '"')], ()
    if expr.kind == "variable":
        sid = str(expr.value)
        return [("IDENT", symbols[sid].name)], (sid,)
    if expr.kind == "result":
        sid = str(expr.value)
        return [("IDENT", symbols[sid].name)], (sid,)
    if expr.kind in ("result_string", "variable_string"):
        sid = str(expr.value)
        return [("IDENT", symbols[sid].name)], (sid,)
    if expr.kind == "unary_minus":
        child, refs = expression_tokens(expr.children[0], symbols)
        return [("OP", "-"), ("PUNCT", "(")] + child + [("PUNCT", ")")], refs
    if expr.kind == "binary":
        left, left_refs = expression_tokens(expr.children[0], symbols)
        right, right_refs = expression_tokens(expr.children[1], symbols)
        return ([ ("PUNCT", "(") ] + left + [("WS", " "), ("OP", str(expr.value)), ("WS", " ")]
                + right + [("PUNCT", ")")]), left_refs + right_refs
    if expr.kind == "compare":
        left, left_refs = expression_tokens(expr.children[0], symbols)
        right, right_refs = expression_tokens(expr.children[1], symbols)
        return ([ ("PUNCT", "(") ] + left + [("WS", " "), ("OP", str(expr.value)), ("WS", " ")]
                + right + [("PUNCT", ")")]), left_refs + right_refs
    if expr.kind == "call":
        sid = str(expr.value)
        output: list[tuple[str, str]] = [("IDENT", symbols[sid].name), ("PUNCT", "(")]
        refs: list[str] = [sid]
        for index, child in enumerate(expr.children):
            if index:
                output.extend([("PUNCT", ","), ("WS", " ")])
            child_tokens, child_refs = expression_tokens(child, symbols)
            output.extend(child_tokens)
            refs.extend(child_refs)
        output.append(("PUNCT", ")"))
        return output, tuple(refs)
    if expr.kind in ("array_element", "array_element_string"):
        sid = str(expr.value)
        child, child_refs = expression_tokens(expr.children[0], symbols)
        return ([ ("IDENT", symbols[sid].name), ("PUNCT", "(") ] + child + [("PUNCT", ")")],
                (sid,) + child_refs)
    raise WorkspaceError("UNSUPPORTED_EXPRESSION", f"Unsupported projection node {expr.kind!r}")
