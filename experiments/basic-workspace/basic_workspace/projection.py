"""Immutable numeric compilation view derived directly from canonical tokens."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .model import Document, Token, Workspace, WorkspaceError
from .typed_expr import Expr


@dataclass(frozen=True)
class Assignment:
    target_symbol_id: str
    target_is_result: bool
    expression: Expr
    line: int
    target_index: Expr | None = None
    target_is_array: bool = False


@dataclass(frozen=True)
class ArrayProjection:
    symbol_id: str
    name: str
    lower_bound: int
    upper_bound: int


@dataclass(frozen=True)
class FunctionProjection:
    symbol_id: str
    name: str
    scope_id: str
    parameter_ids: tuple[str, ...]
    local_ids: tuple[str, ...]
    arrays: tuple[ArrayProjection, ...]
    statements: tuple[Assignment, ...]


@dataclass(frozen=True)
class CompilableProjection:
    document_id: str
    revision: int
    functions: tuple[FunctionProjection, ...]


def _fail(code: str, message: str, token: Token | None = None) -> WorkspaceError:
    details = None if token is None else {"line": token.line, "column": token.column}
    return WorkspaceError(code, message, details)


def _statements(doc: Document) -> list[tuple[Token, ...]]:
    """Group existing tokens into statements without lexing or rendering text."""
    by_line: dict[int, list[Token]] = {}
    for token in doc.tokens:
        if token.kind != "NEWLINE":
            by_line.setdefault(token.line, []).append(token)
    statements: list[tuple[Token, ...]] = []
    for line in sorted(by_line):
        current: list[Token] = []
        chunks: list[list[Token]] = []
        for token in by_line[line]:
            if token.kind in ("WS",):
                continue
            if token.kind == "COMMENT":
                if current:
                    chunks.append(current)
                    current = []
                break
            if token.kind == "PUNCT" and token.text == ":":
                if current:
                    chunks.append(current)
                    current = []
                continue
            current.append(token)
        if current:
            chunks.append(current)
        if chunks and chunks[0] and chunks[0][0].kind == "NUMBER" and chunks[0][0].text.isdigit():
            chunks[0] = chunks[0][1:]
        statements.extend(tuple(chunk) for chunk in chunks if chunk)
    return statements


class _ExpressionParser:
    def __init__(self, doc: Document, tokens: tuple[Token, ...], current: FunctionProjection | None = None):
        self.doc = doc
        self.tokens = tokens
        self.current = current
        self.pos = 0

    def peek(self) -> Token | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def take(self) -> Token:
        token = self.peek()
        if token is None:
            raise _fail("INVALID_EXPRESSION", "Expected an expression before end of statement")
        self.pos += 1
        return token

    @staticmethod
    def _precedence(token: Token | None) -> int:
        if token is None or token.kind != "OP":
            return -1
        if token.text in ("+", "-"):
            return 1
        if token.text in ("*", "/"):
            return 2
        return -1

    def parse(self, min_precedence: int = 0) -> Expr:
        token = self.take()
        if token.kind == "NUMBER":
            left = Expr("number", float(token.text))
        elif token.kind == "OP" and token.text in ("+", "-"):
            operand = self.parse(3)
            left = operand if token.text == "+" else Expr("unary_minus", children=(operand,))
        elif token.kind == "PUNCT" and token.text == "(":
            left = self.parse()
            close = self.take()
            if close.kind != "PUNCT" or close.text != ")":
                raise _fail("INVALID_EXPRESSION", "Expected closing parenthesis", close)
        elif token.kind == "IDENT":
            sid = self.doc.token_symbol.get(token.uid)
            symbol = self.doc.symbols.get(sid) if sid else None
            if symbol is None:
                raise _fail("UNRESOLVED_SYMBOL", f"Identifier {token.text} has no semantic binding", token)
            if self.peek() is not None and self.peek().text == "(":
                self.take()  # opening parenthesis
                if symbol.kind == "array":
                    index = self.parse()
                    close = self.take()
                    if close.text != ")":
                        raise _fail("UNSUPPORTED_ARRAY", "Only one-dimensional array reads are supported", close)
                    left = Expr("array_element", symbol.id, (index,))
                else:
                    if symbol.kind != "function" or symbol.name.endswith("$"):
                        raise _fail("UNSUPPORTED_CALL", f"{token.text} is not a resolved numeric FUNCTION", token)
                    args: list[Expr] = []
                    if self.peek() is not None and self.peek().text != ")":
                        while True:
                            args.append(self.parse())
                            next_token = self.peek()
                            if next_token is None or next_token.text != ",":
                                break
                            self.take()
                    close = self.take()
                    if close.text != ")":
                        raise _fail("INVALID_EXPRESSION", "Expected closing parenthesis in function call", close)
                    left = Expr("call", symbol.id, tuple(args))
            elif self.current is not None and symbol.id == self.current.symbol_id:
                left = Expr("result")
            elif symbol.kind in ("parameter", "variable") and self.current is not None and symbol.scope_id == self.current.scope_id:
                if symbol.name.endswith("$"):
                    raise _fail("UNSUPPORTED_TYPE", f"String value {token.text} is outside the numeric subset", token)
                left = Expr("variable", symbol.id)
            else:
                raise _fail("UNSUPPORTED_REFERENCE", f"Reference to {token.text} is not a local numeric value", token)
        else:
            raise _fail("INVALID_EXPRESSION", f"Unsupported expression token {token.text!r}", token)

        while self._precedence(self.peek()) >= min_precedence:
            op_token = self.take()
            precedence = self._precedence(op_token)
            right = self.parse(precedence + 1)
            left = Expr("binary", op_token.text, (left, right))
        return left

    def parse_all(self) -> Expr:
        value = self.parse()
        if self.peek() is not None:
            token = self.peek()
            raise _fail("UNSUPPORTED_EXPRESSION", f"Unexpected token {token.text!r} after expression", token)
        return value


def build_projection(workspace: Workspace, document_id: str,
                     expected_revision: int | None = None) -> CompilableProjection:
    return build_projection_from_document(workspace, workspace._doc(document_id), expected_revision)


def build_projection_from_document(workspace: Workspace, doc: Document,
                                   expected_revision: int | None = None) -> CompilableProjection:
    if expected_revision is not None and expected_revision != doc.revision:
        raise WorkspaceError("STALE_REVISION", f"Expected revision {expected_revision}, current revision is {doc.revision}",
                             {"current_revision": doc.revision})

    fatal = [d for d in doc.diagnostics if d.severity == "error" or d.code in (
        "DUPLICATE_LINE", "UNRESOLVED_LINE", "AMBIGUOUS_CALL_OR_ARRAY")]
    if fatal:
        d = fatal[0]
        raise WorkspaceError("NOT_COMPILABLE", d.message, [workspace._diag_json(x) for x in fatal])

    all_statements = _statements(doc)
    by_symbol = {f["symbol_id"]: f for f in doc.functions}
    function_rows: list[tuple[str, tuple[str, ...], list[tuple[Token, ...]]]] = []
    active_id: str | None = None
    active_body: list[tuple[Token, ...]] = []
    seen: set[str] = set()

    for statement in all_statements:
        first = statement[0]
        word = first.text.upper() if first.kind == "IDENT" else ""
        if active_id is None:
            if word in ("FUNCTION", "SUB", "DEF", "EXTERN", "EXTERNAL"):
                if word != "FUNCTION":
                    raise _fail("UNSUPPORTED_DECLARATION", f"{word} is outside the numeric FUNCTION subset", first)
                if len(statement) < 4 or statement[1].kind != "IDENT" or statement[2].text != "(":
                    raise _fail("INVALID_FUNCTION", "Expected FUNCTION name(parameter, ...)", first)
                name_token = statement[1]
                sid = doc.token_symbol.get(name_token.uid)
                symbol = doc.symbols.get(sid) if sid else None
                row = by_symbol.get(sid or "")
                if symbol is None or row is None or symbol.kind != "function":
                    raise _fail("UNRESOLVED_FUNCTION", f"Function {name_token.text} lacks a semantic definition", name_token)
                if symbol.name.endswith("$"):
                    raise _fail("UNSUPPORTED_TYPE", f"String function {symbol.name} is outside the numeric subset", name_token)
                if sid in seen:
                    raise _fail("DUPLICATE_FUNCTION", f"Duplicate function {symbol.name}", name_token)
                seen.add(sid)
                try:
                    close_index = next(i for i, t in enumerate(statement[3:], 3) if t.text == ")")
                except StopIteration:
                    raise _fail("INVALID_FUNCTION", "Missing closing parenthesis in function header", name_token)
                if close_index != len(statement) - 1:
                    raise _fail("UNSUPPORTED_FUNCTION_FORM", "Single-line FUNCTION bodies are not supported", statement[close_index + 1])
                params = tuple(doc.token_symbol[t.uid] for t in statement[3:close_index]
                               if t.kind == "IDENT" and t.uid in doc.token_symbol)
                if len(params) != len(row["parameters"]):
                    raise _fail("INVALID_FUNCTION", f"Parameter bindings for {symbol.name} are incomplete", name_token)
                if any(doc.symbols[p].name.endswith("$") for p in params):
                    raise _fail("UNSUPPORTED_TYPE", f"String parameter in {symbol.name} is outside the numeric subset", name_token)
                active_id, active_body = sid, []
            elif word == "END" and len(statement) > 1 and statement[1].text.upper() in ("FUNCTION", "SUB"):
                raise _fail("UNMATCHED_END", "END FUNCTION has no open function", first)
            else:
                raise _fail("UNSUPPORTED_TOP_LEVEL", "Only numeric FUNCTION declarations are executable in this projection", first)
        elif word == "END" and len(statement) > 1 and statement[1].text.upper() == "FUNCTION":
            function_rows.append((active_id, tuple(doc.functions[next(i for i, f in enumerate(doc.functions) if f["symbol_id"] == active_id)]["parameters"]), active_body))
            active_id, active_body = None, []
        else:
            active_body.append(statement)

    if active_id is not None:
        function = doc.symbols[active_id]
        raise WorkspaceError("NOT_COMPILABLE", f"Function {function.name} is incomplete")
    if not function_rows:
        raise WorkspaceError("NOT_COMPILABLE", "No numeric FUNCTION definitions were found")

    compiled: list[FunctionProjection] = []
    for sid, parameter_ids, body in function_rows:
        symbol = doc.symbols[sid]
        scope_id = by_symbol[sid]["scope_id"]
        array_rows = tuple(ArrayProjection(row.id, row.name, row.array_lower or 0,
                                           row.array_upper if row.array_upper is not None else -1)
                           for row in doc.symbols.values()
                           if row.kind == "array" and row.scope_id == scope_id)
        array_ids = {row.symbol_id for row in array_rows}
        shell = FunctionProjection(sid, symbol.name, scope_id, parameter_ids, (), array_rows, ())
        statements: list[Assignment] = []
        local_ids: set[str] = set()
        declared_arrays: set[str] = set()
        for row in doc.symbols.values():
            if row.kind == "variable" and row.scope_id == scope_id:
                local_ids.add(row.id)
        for tokens in body:
            if tokens[0].text.upper() == "DIM":
                if (len(tokens) != 5 or tokens[1].kind != "IDENT" or tokens[2].text != "("
                        or tokens[3].kind != "NUMBER" or not tokens[3].text.isdigit()
                        or tokens[4].text != ")"):
                    raise _fail("UNSUPPORTED_DIM", "Only one-dimensional DIM NAME(nonnegative-integer) is supported", tokens[0])
                sid_dim = doc.token_symbol.get(tokens[1].uid)
                if sid_dim not in array_ids:
                    raise _fail("UNRESOLVED_ARRAY", f"Array {tokens[1].text} is not declared in this function", tokens[1])
                if sid_dim in declared_arrays:
                    raise _fail("DUPLICATE_DIM", f"Array {tokens[1].text} is dimensioned more than once", tokens[1])
                declared_arrays.add(sid_dim)
                continue
            for token in tokens:
                sid_at_token = doc.token_symbol.get(token.uid)
                if sid_at_token in array_ids and sid_at_token not in declared_arrays:
                    raise _fail("ARRAY_USED_BEFORE_DIM", f"Array {token.text} is used before its DIM statement", token)
            if tokens[0].text.upper() == "LET":
                tokens = tokens[1:]
            if len(tokens) < 3 or tokens[0].kind != "IDENT":
                raise _fail("UNSUPPORTED_STATEMENT", "Expected a numeric assignment", tokens[0])
            target_token = tokens[0]
            target_sid = doc.token_symbol.get(target_token.uid)
            target = doc.symbols.get(target_sid) if target_sid else None
            if target is None:
                raise _fail("UNRESOLVED_ASSIGNMENT", f"Assignment target {target_token.text} has no binding", target_token)
            target_index: Expr | None = None
            equals_index = 1
            target_is_array = False
            if len(tokens) > 3 and tokens[1].text == "(":
                close_index = next((j for j in range(2, len(tokens)) if tokens[j].text == ")"), None)
                if close_index is not None and close_index + 1 < len(tokens) and tokens[close_index + 1].text == "=":
                    if target.kind != "array":
                        raise _fail("UNSUPPORTED_ARRAY", f"{target.name} is not a declared array", target_token)
                    target_index = _ExpressionParser(doc, tokens[2:close_index], shell).parse_all()
                    equals_index = close_index + 1
                    target_is_array = True
                else:
                    raise _fail("UNSUPPORTED_ARRAY", "Malformed or multidimensional array assignment", target_token)
            elif tokens[1].text != "=":
                raise _fail("UNSUPPORTED_STATEMENT", "Expected '=' after numeric assignment target", tokens[1])
            if target.kind == "array" and not target_is_array:
                raise _fail("UNSUPPORTED_ARRAY", "Array assignment requires an index", target_token)
            is_result = target.id == sid
            if target_is_array:
                if target.id not in array_ids or target.scope_id != scope_id:
                    raise _fail("CROSS_SCOPE_REFERENCE", "Array target is outside the current function", target_token)
            elif not is_result and (target.kind not in ("parameter", "variable") or target.scope_id != scope_id):
                raise _fail("UNSUPPORTED_ASSIGNMENT", f"Assignment to {target.name} is outside the current function scope", target_token)
            if target.name.endswith("$"):
                raise _fail("UNSUPPORTED_TYPE", f"String assignment {target.name} is outside the numeric subset", target_token)
            expression = _ExpressionParser(doc, tokens[equals_index + 1:], shell).parse_all()
            statements.append(Assignment(target.id, is_result, expression, target_token.line,
                                         target_index, target_is_array))
            if not is_result and target.kind == "variable":
                local_ids.add(target.id)

        # Keep slot order tied to declaration token order, not dictionary order.
        token_index = {t.uid: i for i, t in enumerate(doc.tokens)}
        locals_ordered = tuple(sorted(local_ids, key=lambda ident: token_index[doc.symbols[ident].declaration_token]))
        compiled.append(FunctionProjection(sid, symbol.name, scope_id, parameter_ids,
                                           locals_ordered, array_rows, tuple(statements)))

    function_ids = {f.symbol_id for f in compiled}
    call_graph: dict[str, set[str]] = {f.symbol_id: set() for f in compiled}
    for function in compiled:
        for statement in function.statements:
            _validate_calls(statement.expression, function_ids, len(compiled), doc)
            call_graph[function.symbol_id].update(_called_functions(statement.expression))
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(function_id: str) -> None:
        if function_id in visiting:
            raise WorkspaceError("RECURSIVE_CALL_UNSUPPORTED", "Recursive numeric FUNCTION call graphs are not supported")
        if function_id in visited:
            return
        visiting.add(function_id)
        for callee_id in call_graph[function_id]:
            visit(callee_id)
        visiting.remove(function_id)
        visited.add(function_id)

    for function_id in call_graph:
        visit(function_id)
    return CompilableProjection(doc.id, doc.revision, tuple(compiled))


def _validate_calls(expr: Expr, functions: set[str], _count: int, doc: Document) -> None:
    if expr.kind == "call":
        if expr.value not in functions:
            symbol = doc.symbols.get(str(expr.value))
            raise WorkspaceError("UNSUPPORTED_CALL", f"Call target {symbol.name if symbol else expr.value} is not a compiled numeric FUNCTION")
        row = next(f for f in doc.functions if f["symbol_id"] == expr.value)
        if len(expr.children) != len(row["parameters"]):
            raise WorkspaceError("ARGUMENT_COUNT", f"Function {row['name']} expects {len(row['parameters'])} arguments, got {len(expr.children)}")
    for child in expr.children:
        _validate_calls(child, functions, _count, doc)


def _called_functions(expr: Expr) -> set[str]:
    result = {str(expr.value)} if expr.kind == "call" else set()
    for child in expr.children:
        result.update(_called_functions(child))
    return result
