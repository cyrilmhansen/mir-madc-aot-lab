"""Lossless BASIC token model and semantic editing API.

The token stream (including whitespace, comments and line endings) is canonical.
Statement, scope and symbol indexes are rebuilt views over that stream. Semantic
edits mutate token identities, then validate and rebuild indexes atomically.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import copy
import difflib
import math
import re
import uuid
from typing import Any


def opaque(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


@dataclass
class Token:
    uid: str
    kind: str
    text: str
    line: int
    column: int


@dataclass
class Symbol:
    id: str
    kind: str
    name: str
    normalized: str
    scope_id: str
    document_id: str
    declaration_token: str
    line: int
    implicit: bool = False
    array_lower: int | None = None
    array_upper: int | None = None
    references: list[str] = field(default_factory=list)


@dataclass
class Diagnostic:
    code: str
    message: str
    severity: str
    line: int
    column: int


@dataclass
class Document:
    id: str
    uri: str
    revision: int
    tokens: list[Token]
    diagnostics: list[Diagnostic] = field(default_factory=list)
    symbols: dict[str, Symbol] = field(default_factory=dict)
    token_symbol: dict[str, str] = field(default_factory=dict)
    labels: dict[int, str] = field(default_factory=dict)
    label_tokens: dict[str, str] = field(default_factory=dict)
    line_refs: dict[str, int] = field(default_factory=dict)
    # Derived from DIM statements on every index rebuild: symbol ID -> (lower, upper).
    array_bounds: dict[str, tuple[int, int]] = field(default_factory=dict)
    lines: list[dict[str, Any]] = field(default_factory=list)
    functions: list[dict[str, Any]] = field(default_factory=list)
    statements: dict[str, dict[str, Any]] = field(default_factory=dict)
    _symbol_ids: dict[str, str] = field(default_factory=dict, repr=False)
    _scope_ids: dict[str, str] = field(default_factory=dict, repr=False)
    _statement_ids: dict[str, str] = field(default_factory=dict, repr=False)

    def render(self) -> str:
        return "".join(t.text for t in self.tokens)


KEYWORDS = set("""AND AS CALL CASE CLEAR CLOSE DATA DEF DIM DO ELSE ELSEIF END EXTERN
EXTERNAL FN FOR FUNCTION GET GOSUB GOTO IF INPUT LET LOOP MAT NEXT NOT OFF ON OPEN
OPTION PRINT RANDOMIZE READ REM RESTORE RETURN RESUME SCREEN STEP STOP SUB THEN TO
UNTIL WEND WHILE WRITE XOR OR MOD""".split())
BUILTINS = set("""ABS ASC ATN CHR$ COS EXP INT LEFT$ LEN LOG MID$ RIGHT$ RND SGN SIN
SQR STR$ TAN UCASE$ UPPER$ VAL FRE PEEK POS TAB SPC EOF EOFN""".split())
IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z_0-9]*(?:[$%!#])?")
NUMBER_RE = re.compile(r"(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?")


def lex(text: str) -> list[Token]:
    tokens: list[Token] = []
    lines = text.splitlines(keepends=True)
    if not lines and text == "":
        return tokens
    if text and (not lines or not lines[-1].endswith(("\n", "\r"))):
        pass
    for line_no, raw in enumerate(lines or [""], 1):
        body = raw.rstrip("\r\n")
        ending = raw[len(body):]
        col, i = 0, 0
        previous_non_ws: Token | None = None
        while i < len(body):
            start = i
            ch = body[i]
            if ch.isspace():
                i += 1
                while i < len(body) and body[i].isspace():
                    i += 1
                kind = "WS"
            elif ch == "'":
                i = len(body)
                kind = "COMMENT"
            elif ch == '"':
                i += 1
                closed = False
                while i < len(body):
                    if body[i] == '"':
                        if i + 1 < len(body) and body[i + 1] == '"':
                            i += 2
                            continue
                        i += 1
                        closed = True
                        break
                    i += 1
                kind = "STRING" if closed else "UNTERMINATED_STRING"
            else:
                m = IDENT_RE.match(body, i)
                if m:
                    i = m.end()
                    # REM starts a comment only at a statement boundary.
                    at_record_start = (previous_non_ws is not None
                                       and previous_non_ws.kind == "NUMBER"
                                       and previous_non_ws.text.isdigit()
                                       and not any(t.line == line_no and t.kind not in ("WS",) for t in tokens))
                    if m.group().upper() == "REM" and (previous_non_ws is None or previous_non_ws.text == ":" or at_record_start):
                        i = len(body)
                        kind = "COMMENT"
                    else:
                        kind = "IDENT"
                else:
                    m = NUMBER_RE.match(body, i)
                    if m:
                        i = m.end()
                        kind = "NUMBER"
                    elif i + 1 < len(body) and body[i:i + 2] in ("<=", ">=", "<>", "=="):
                        i += 2
                        kind = "OP"
                    else:
                        i += 1
                        kind = "PUNCT" if ch in ":,();" else "OP"
            token = Token(opaque("t"), kind, body[start:i], line_no, col)
            tokens.append(token)
            if kind != "WS":
                previous_non_ws = token
            col += i - start
        if ending:
            tokens.append(Token(opaque("t"), "NEWLINE", ending, line_no, len(body)))
    return tokens


def sigil_type(name: str) -> str:
    return "string" if name.endswith("$") else "numeric"


class WorkspaceError(Exception):
    def __init__(self, code: str, message: str, details: Any = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details

    def json(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details}


class Workspace:
    def __init__(self) -> None:
        self.documents: dict[str, Document] = {}
        self._discovered_symbols: dict[str, set[str]] = {}
        self._discovered_statements: dict[str, set[str]] = {}

    def create_workspace(self) -> dict[str, Any]:
        return {"workspace_id": "workspace-1", "documents": 0}

    def open_document_from_string(self, text: str, uri: str | None = None) -> dict[str, Any]:
        did = opaque("doc")
        doc = Document(did, uri or f"memory://{did}/program.bas", 1, lex(text))
        self.documents[did] = doc
        self._discovered_symbols[did] = set()
        self._discovered_statements[did] = set()
        self._index(doc)
        return {"document_id": did, "uri": doc.uri, "revision": doc.revision,
                "diagnostics": [self._diag_json(d) for d in doc.diagnostics]}

    def create_empty_document(self, uri: str | None = None) -> dict[str, Any]:
        """Create an empty canonical token model without accepting BASIC text."""
        did = opaque("doc")
        doc = Document(did, uri or f"memory://{did}/program.bas", 1, [])
        self.documents[did] = doc
        self._discovered_symbols[did] = set()
        self._discovered_statements[did] = set()
        self._index(doc)
        return {"document_id": did, "uri": doc.uri, "revision": doc.revision,
                "diagnostics": []}

    def replace_document_from_string(self, document_id: str, text: str,
                                     expected_revision: int) -> dict[str, Any]:
        """Import an external full-text sync as one explicit model transaction.

        This is a compatibility bridge for editors. It invalidates token and
        symbol identities because the request replaces the complete text.
        Semantic API edits preserve identities instead.
        """
        old = self._doc(document_id)
        if old.revision != expected_revision:
            raise WorkspaceError("STALE_REVISION", f"Expected revision {expected_revision}, current revision is {old.revision}", {"current_revision": old.revision})
        new = Document(old.id, old.uri, old.revision + 1, lex(text))
        self._index(new)
        self.documents[document_id] = new
        self._discovered_symbols[document_id] = set()
        self._discovered_statements[document_id] = set()
        return {"document_id": new.id, "revision": new.revision,
                "diagnostics": [self._diag_json(d) for d in new.diagnostics]}

    def list_documents(self) -> list[dict[str, Any]]:
        return [{"document_id": d.id, "uri": d.uri, "revision": d.revision}
                for d in self.documents.values()]

    def _doc(self, document_id: str) -> Document:
        try:
            return self.documents[document_id]
        except KeyError as exc:
            raise WorkspaceError("DOCUMENT_NOT_FOUND", "Unknown document identity") from exc

    @staticmethod
    def _significant(tokens: list[Token]) -> list[Token]:
        return [t for t in tokens if t.kind not in ("WS", "NEWLINE", "COMMENT")]

    def _index(self, doc: Document) -> None:
        previous_ids = doc._symbol_ids
        previous_scopes = doc._scope_ids
        previous_statement_ids = doc._statement_ids
        doc.symbols = {}
        doc.token_symbol = {}
        doc.labels = {}
        doc.label_tokens = {}
        doc.line_refs = {}
        doc.array_bounds = {}
        doc.diagnostics = []
        doc.lines = []
        doc.functions = []

        by_line: dict[int, list[Token]] = {}
        for token in doc.tokens:
            by_line.setdefault(token.line, []).append(token)
        statements: list[dict[str, Any]] = []
        physical_line_tokens: dict[int, list[Token]] = {}
        for number, toks in by_line.items():
            physical_line_tokens[number] = toks
            for bad in (t for t in toks if t.kind == "UNTERMINATED_STRING"):
                doc.diagnostics.append(Diagnostic("UNTERMINATED_STRING", "String literal is missing its closing quote", "error", bad.line, bad.column))
            content = self._significant(toks)
            if content and content[0].kind == "NUMBER" and content[0].text.isdigit():
                label = int(content[0].text)
                if label in doc.labels:
                    doc.diagnostics.append(Diagnostic("DUPLICATE_LINE", f"Duplicate BASIC line label {label}", "error", content[0].line, content[0].column))
                else:
                    doc.labels[label] = content[0].uid
                    doc.label_tokens[content[0].uid] = label
                    sid = previous_ids.get(f"line_label:{content[0].uid}") or opaque("sym")
                    symbol = Symbol(sid, "line_label", content[0].text, content[0].text,
                                    "module", doc.id, content[0].uid, content[0].line)
                    doc.symbols[sid] = symbol
                    doc.token_symbol[content[0].uid] = sid
            # Split statements at colon tokens; strings/comments are atomic.
            current: list[Token] = []
            chunks: list[list[Token]] = []
            for t in toks:
                if t.kind == "COMMENT":
                    if current:
                        chunks.append(current)
                        current = []
                    chunks.append([t])
                    break
                if t.text == ":" and t.kind == "PUNCT":
                    chunks.append(current + [t])
                    current = []
                else:
                    current.append(t)
            if current:
                chunks.append(current)
            first = True
            for chunk in chunks:
                sig = self._significant(chunk)
                if first and sig and sig[0].kind == "NUMBER" and sig[0].text.isdigit():
                    sig = sig[1:]
                first = False
                if not sig:
                    continue
                statements.append({"tokens": sig, "line": number, "physical_line": number,
                                   "kind": sig[0].text.upper() if sig[0].kind == "IDENT" else "UNKNOWN"})
            raw = "".join(t.text for t in toks)
            doc.lines.append({"physical_line": number, "line_label": int(content[0].text) if content and content[0].kind == "NUMBER" and content[0].text.isdigit() else None,
                              "text": raw, "statement_count": len([s for s in statements if s["physical_line"] == number])})

        # Discover function declarations and parameter scopes first.
        func_by_name: dict[str, Symbol] = {}
        scope_for_token: dict[str, str] = {}
        def_fn_scopes: dict[int, tuple[str, str]] = {}
        scope_name: dict[str, str] = {}
        function_ranges: list[dict[str, Any]] = []
        active: dict[str, Any] | None = None
        for i, st in enumerate(statements):
            sig = st["tokens"]
            word = sig[0].text.upper() if sig[0].kind == "IDENT" else ""
            if word == "DEF" and len(sig) > 2 and sig[1].kind == "IDENT" and sig[1].text.upper().startswith("FN"):
                name_t = sig[1]
                sid = previous_ids.get(f"function:{name_t.uid}") or opaque("sym")
                scope_id = previous_scopes.get(f"scope:{name_t.uid}") or opaque("scope")
                sym = Symbol(sid, "function", name_t.text, name_t.text.casefold(), "module", doc.id, name_t.uid, name_t.line)
                doc.symbols[sid] = sym
                doc.token_symbol[name_t.uid] = sid
                func_by_name[sym.normalized] = sym
                func = {"symbol_id": sid, "name": name_t.text, "kind": "def_fn", "scope_id": scope_id,
                        "start_statement": i, "end_statement": i, "start_line": st["line"],
                        "end_line": st["line"], "parameters": []}
                function_ranges.append(func)
                def_fn_scopes[i] = (scope_id, name_t.text.casefold())
                try:
                    lp = next(j for j, t in enumerate(sig) if t.text == "(")
                    rp = next(j for j in range(lp + 1, len(sig)) if sig[j].text == ")")
                    for p in sig[lp + 1:rp]:
                        if p.kind == "IDENT":
                            psid = previous_ids.get(f"parameter:{p.uid}") or opaque("sym")
                            psym = Symbol(psid, "parameter", p.text, p.text.casefold(), scope_id, doc.id, p.uid, p.line)
                            doc.symbols[psid] = psym
                            doc.token_symbol[p.uid] = psid
                            func["parameters"].append(psid)
                except StopIteration:
                    doc.diagnostics.append(Diagnostic("INCOMPLETE_HEADER", f"Could not parse DEF FN parameters for {name_t.text}", "warning", name_t.line, name_t.column))
                continue
            decl_offset = 0
            external = False
            decl_word = word
            if word in ("EXTERN", "EXTERNAL") and len(sig) > 2 and sig[1].text.upper() in ("FUNCTION", "SUB"):
                decl_offset = 1
                decl_word = sig[1].text.upper()
                external = True
            if decl_word in ("FUNCTION", "SUB") and len(sig) > decl_offset + 1 and sig[decl_offset + 1].kind == "IDENT":
                name_t = sig[decl_offset + 1]
                key = f"function:{name_t.uid}"
                sid = previous_ids.get(key) or opaque("sym")
                scope_key = f"scope:{name_t.uid}"
                scope_id = previous_scopes.get(scope_key) or opaque("scope")
                kind = ("external_function" if external and decl_word == "FUNCTION" else
                        "external_procedure" if external else
                        "function" if decl_word == "FUNCTION" else "procedure")
                sym = Symbol(sid, kind, name_t.text, name_t.text.casefold(), "module", doc.id, name_t.uid, name_t.line)
                doc.symbols[sid] = sym
                doc.token_symbol[name_t.uid] = sid
                if sym.normalized in func_by_name:
                    doc.diagnostics.append(Diagnostic("DUPLICATE_FUNCTION", f"Duplicate function/procedure {sym.name}", "error", name_t.line, name_t.column))
                func_by_name[sym.normalized] = sym
                func = {"symbol_id": sid, "name": name_t.text, "kind": kind, "scope_id": scope_id,
                        "start_statement": i, "end_statement": i if external else None, "start_line": st["line"],
                        "end_line": st["line"] if external else None, "parameters": []}
                function_ranges.append(func)
                active = None if external else func
                scope_name[scope_id] = name_t.text
                # Parameter identifiers are the identifiers inside the first header parens.
                try:
                    lp = next(j for j, t in enumerate(sig) if t.text == "(")
                    rp = next(j for j in range(lp + 1, len(sig)) if sig[j].text == ")")
                    for p in sig[lp + 1:rp]:
                        if p.kind == "IDENT" and p.text.upper() not in KEYWORDS:
                            pkey = f"parameter:{p.uid}"
                            psid = previous_ids.get(pkey) or opaque("sym")
                            psym = Symbol(psid, "parameter", p.text, p.text.casefold(), scope_id, doc.id, p.uid, p.line)
                            doc.symbols[psid] = psym
                            doc.token_symbol[p.uid] = psid
                            func["parameters"].append(psid)
                except (StopIteration, ValueError):
                    doc.diagnostics.append(Diagnostic("INCOMPLETE_HEADER", f"Could not parse parameter list for {name_t.text}", "warning", name_t.line, name_t.column))
                continue
            if word == "END" and len(sig) > 1 and sig[1].text.upper() in ("FUNCTION", "SUB"):
                if active:
                    active["end_statement"] = i
                    active["end_line"] = st["line"]
                    active = None
                else:
                    doc.diagnostics.append(Diagnostic("UNMATCHED_END", "END FUNCTION/SUB without an open definition", "warning", st["line"], sig[0].column))
                continue
            if active:
                for t in sig:
                    scope_for_token[t.uid] = active["scope_id"]
        if active:
            doc.diagnostics.append(Diagnostic("UNCLOSED_FUNCTION", f"Missing END for {active['name']}", "error", active["start_line"], 0))
        doc.functions = function_ranges

        # Line branch targets are numeric labels, not ordinary numeric literals.
        label_symbols = {s.declaration_token: s for s in doc.symbols.values() if s.kind == "line_label"}
        for statement_index, st in enumerate(statements):
            sig = st["tokens"]
            words = [i for i, t in enumerate(sig) if t.kind == "IDENT" and t.text.upper() in ("GOTO", "GOSUB")]
            for wi in words:
                if wi + 1 < len(sig) and sig[wi + 1].kind == "NUMBER" and sig[wi + 1].text.isdigit():
                    target = int(sig[wi + 1].text)
                    doc.line_refs[sig[wi + 1].uid] = target
                    if target not in doc.labels:
                        doc.diagnostics.append(Diagnostic("UNRESOLVED_LINE", f"Branch references missing BASIC line {target}", "warning", sig[wi + 1].line, sig[wi + 1].column))
                    else:
                        label_token = doc.labels[target]
                        label_symbol = label_symbols.get(label_token)
                        if label_symbol:
                            label_symbol.references.append(sig[wi + 1].uid)
                            doc.token_symbol[sig[wi + 1].uid] = label_symbol.id
                    # ON ... GOTO/GOSUB supports comma-separated computed targets.
                    if any(t.text.upper() == "ON" for t in sig[:wi]):
                        j = wi + 2
                        while j + 1 < len(sig) and sig[j].text == "," and sig[j + 1].kind == "NUMBER" and sig[j + 1].text.isdigit():
                            target = int(sig[j + 1].text)
                            doc.line_refs[sig[j + 1].uid] = target
                            if target not in doc.labels:
                                doc.diagnostics.append(Diagnostic("UNRESOLVED_LINE", f"Branch references missing BASIC line {target}", "warning", sig[j + 1].line, sig[j + 1].column))
                            else:
                                label_token = doc.labels[target]
                                label_symbol = label_symbols.get(label_token)
                                if label_symbol:
                                    label_symbol.references.append(sig[j + 1].uid)
                                    doc.token_symbol[sig[j + 1].uid] = label_symbol.id
                            j += 2

        # Index the fixed, one-dimensional numeric DIM subset. Bounds and array
        # symbols are derived from canonical tokens; only DIM A(nonnegative-int)
        # is admitted here. The executable projection further checks scope/use.
        array_symbols: dict[tuple[str, str], Symbol] = {}
        for statement_index, st in enumerate(statements):
            sig = st["tokens"]
            if not sig or sig[0].text.upper() != "DIM":
                continue
            enclosing = next((f for f in function_ranges
                              if f["start_statement"] < statement_index
                              and f["end_statement"] is not None
                              and statement_index < f["end_statement"]), None)
            scope_id = enclosing["scope_id"] if enclosing else "module"
            if (len(sig) != 5 or sig[1].kind != "IDENT" or sig[2].text != "("
                    or sig[3].kind != "NUMBER" or not sig[3].text.isdigit()
                    or sig[4].text != ")"):
                doc.diagnostics.append(Diagnostic(
                    "UNSUPPORTED_DIM", "Only DIM NAME(nonnegative-integer) is indexed by this Workspace subset",
                    "warning", sig[0].line, sig[0].column))
                continue
            name_token = sig[1]
            key = (scope_id, name_token.text.casefold())
            try:
                upper = int(sig[3].text)
            except ValueError:
                upper = 0
            if upper > 255:
                doc.diagnostics.append(Diagnostic("ARRAY_CAPACITY_LIMIT",
                    "Numeric arrays are limited to 256 elements (upper bound 255)",
                    "error", sig[3].line, sig[3].column))
                continue
            if key in array_symbols:
                doc.diagnostics.append(Diagnostic("DUPLICATE_DIM",
                    f"Array {name_token.text} is dimensioned more than once in the same scope",
                    "error", name_token.line, name_token.column))
                continue
            existing = next((s for s in doc.symbols.values()
                             if s.normalized == key[1]
                             and ((s.scope_id == scope_id and s.kind == "parameter")
                                  or (s.scope_id == "module" and s.kind in (
                                      "function", "procedure", "external_function",
                                      "external_procedure")))), None)
            if existing is not None:
                doc.diagnostics.append(Diagnostic("ARRAY_NAME_COLLISION",
                    f"Array {name_token.text} collides with {existing.kind} {existing.name}",
                    "error", name_token.line, name_token.column))
                continue
            sid = previous_ids.get(f"array:{name_token.uid}") or opaque("sym")
            symbol = Symbol(sid, "array", name_token.text, name_token.text.casefold(),
                            scope_id, doc.id, name_token.uid, name_token.line,
                            array_lower=0, array_upper=upper)
            doc.symbols[sid] = symbol
            doc.token_symbol[name_token.uid] = sid
            doc.array_bounds[sid] = (0, upper)
            array_symbols[key] = symbol

        # Resolve implicit variables per function/module scope. The declaration
        # identity is the first occurrence token; the dialect has no explicit
        # variable declaration requirement for this subset.
        var_symbols: dict[tuple[str, str], Symbol] = {}
        for sym in doc.symbols.values():
            if sym.kind == "parameter":
                var_symbols[(sym.scope_id, sym.normalized)] = sym
        for statement_index, st in enumerate(statements):
            sig = st["tokens"]
            # The statement's lexical scope is its enclosing function (if any).
            enclosing = None
            for f in function_ranges:
                if f["start_statement"] < statement_index and (f["end_statement"] is None or statement_index < f["end_statement"]):
                    enclosing = f
            scope_id = enclosing["scope_id"] if enclosing else "module"
            active_name = enclosing["name"].casefold() if enclosing else None
            if statement_index in def_fn_scopes:
                scope_id, active_name = def_fn_scopes[statement_index]
            for i, t in enumerate(sig):
                if t.kind != "IDENT" or t.uid in doc.token_symbol or t.uid in doc.label_tokens:
                    continue
                word = t.text.upper()
                if word in KEYWORDS:
                    continue
                if t.uid in doc.line_refs:
                    continue
                array = array_symbols.get((scope_id, t.text.casefold()))
                if array is None and scope_id != "module":
                    array = array_symbols.get(("module", t.text.casefold()))
                if array is not None:
                    if i + 1 >= len(sig) or sig[i + 1].text != "(":
                        doc.diagnostics.append(Diagnostic("ARRAY_SCALAR_COLLISION",
                            f"{t.text} is an array and must be used with an index", "error",
                            t.line, t.column))
                    array.references.append(t.uid)
                    doc.token_symbol[t.uid] = array.id
                    continue
                # Calls bind normally; a function's own bare name inside its body
                # is the return-value assignment/reference in this BASIC dialect.
                if t.text.casefold() in func_by_name:
                    if i + 1 < len(sig) and sig[i + 1].text == "(":
                        fs = func_by_name[t.text.casefold()]
                        fs.references.append(t.uid)
                        doc.token_symbol[t.uid] = fs.id
                    elif active_name and t.text.casefold() == active_name and enclosing:
                        result_func = func_by_name.get(active_name)
                        if result_func and result_func.id == enclosing["symbol_id"] and enclosing["kind"] == "function":
                            result_func.references.append(t.uid)
                            doc.token_symbol[t.uid] = result_func.id
                    continue
                # DEF FN names and builtins are callable entities, not variables.
                if word in BUILTINS or word.startswith("FN"):
                    continue
                # Unknown call-like names remain explicit ambiguity diagnostics.
                if i + 1 < len(sig) and sig[i + 1].text == "(":
                    # Array variables are common; known statement context and assignment
                    # indicate arrays. Otherwise retain an ambiguity rather than guessing.
                    if (any(x.text == "=" for x in sig[:i + 1])
                            or (i > 0 and sig[i - 1].text.upper() == "DIM")
                            or word in ("DIM", "FOR", "NEXT", "READ", "INPUT")):
                        pass
                    else:
                        doc.diagnostics.append(Diagnostic("AMBIGUOUS_CALL_OR_ARRAY", f"Cannot tell whether {t.text} is an implicit array or function call", "information", t.line, t.column))
                        continue
                key = (scope_id, t.text.casefold())
                sym = var_symbols.get(key)
                if key in array_symbols:
                    doc.diagnostics.append(Diagnostic("ARRAY_SCALAR_COLLISION",
                        f"{t.text} is a numeric array and cannot also be used as a scalar", "error",
                        t.line, t.column))
                    continue
                if sym is None:
                    skey = f"implicit:{scope_id}:{t.uid}"
                    sid = previous_ids.get(skey) or opaque("sym")
                    sym = Symbol(sid, "variable", t.text, t.text.casefold(), scope_id, doc.id, t.uid, t.line, True)
                    var_symbols[key] = sym
                    doc.symbols[sid] = sym
                sym.references.append(t.uid)
                doc.token_symbol[t.uid] = sym.id

        # Stable IDs for supported assignment statements are anchored to the
        # canonical target token, not to line/column positions.
        doc.statements = {}
        doc._statement_ids = {}
        for statement_index, st in enumerate(statements):
            sig = st["tokens"]
            offset = 1 if sig and sig[0].text.upper() == "LET" else 0
            target_end = offset + 1
            is_array_target = False
            if (len(sig) > offset + 4 and sig[offset].kind == "IDENT"
                    and sig[offset + 1].text == "("):
                close = next((j for j in range(offset + 2, len(sig)) if sig[j].text == ")"), None)
                if close is not None and close + 1 < len(sig) and sig[close + 1].text == "=":
                    target_end = close + 1
                    is_array_target = True
            if len(sig) < target_end + 2 or sig[offset].kind != "IDENT" or sig[target_end].text != "=":
                continue
            owner = next((f for f in function_ranges
                          if f["start_statement"] < statement_index
                          and f["end_statement"] is not None
                          and statement_index < f["end_statement"]), None)
            if owner is None or owner["kind"] != "function":
                continue
            target = sig[offset]
            target_id = doc.token_symbol.get(target.uid)
            target_symbol = doc.symbols.get(target_id) if target_id else None
            if target_symbol is None:
                continue
            if is_array_target and target_symbol.kind != "array":
                continue
            if not is_array_target and target_symbol.kind == "array":
                continue
            statement_id = previous_statement_ids.get(target.uid) or opaque("stmt")
            referenced: list[str] = []
            if is_array_target:
                for token in sig[offset + 2:target_end - 1]:
                    sid = doc.token_symbol.get(token.uid)
                    if sid and sid not in referenced:
                        referenced.append(sid)
            expression_start = target_end + 1
            for token in sig[expression_start:]:
                sid = doc.token_symbol.get(token.uid)
                if sid and token.uid != target.uid and sid not in referenced:
                    referenced.append(sid)
            expression_summary = "".join(token.text for token in sig[expression_start:])[:120]
            doc.statements[statement_id] = {
                "statement_id": statement_id,
                "anchor_token_id": target.uid,
                "kind": "array_assignment" if is_array_target else "assignment",
                "containing_function_id": owner["symbol_id"],
                "target_symbol_id": target_id,
                "target_name": target_symbol.name,
                "referenced_symbol_ids": referenced,
                "expression_summary": expression_summary,
                "line": st["line"],
                "physical_statement_index": statement_index,
            }
            if is_array_target:
                doc.statements[statement_id]["index_token_ids"] = [t.uid for t in sig[offset + 2:target_end - 1]]
            doc._statement_ids[target.uid] = statement_id

        # Preserve IDs through the next reindex, keyed by declaration token.
        doc._symbol_ids = {}
        doc._scope_ids = {}
        for sym in doc.symbols.values():
            if sym.kind in ("function", "procedure", "external_function", "external_procedure"):
                doc._symbol_ids[f"function:{sym.declaration_token}"] = sym.id
                f = next((x for x in function_ranges if x["symbol_id"] == sym.id), None)
                if f:
                    doc._scope_ids[f"scope:{sym.declaration_token}"] = f["scope_id"]
            elif sym.kind == "parameter":
                doc._symbol_ids[f"parameter:{sym.declaration_token}"] = sym.id
            elif sym.implicit:
                doc._symbol_ids[f"implicit:{sym.scope_id}:{sym.declaration_token}"] = sym.id
            elif sym.kind == "array":
                doc._symbol_ids[f"array:{sym.declaration_token}"] = sym.id
            elif sym.kind == "line_label":
                doc._symbol_ids[f"line_label:{sym.declaration_token}"] = sym.id

    @staticmethod
    def _diag_json(d: Diagnostic) -> dict[str, Any]:
        return {"code": d.code, "message": d.message, "severity": d.severity,
                "line": d.line, "column": d.column}

    def get_document_structure(self, document_id: str) -> dict[str, Any]:
        d = self._doc(document_id)
        self._discovered_symbols.setdefault(document_id, set()).update(
            f["symbol_id"] for f in d.functions if f.get("symbol_id"))
        self._discovered_symbols[document_id].update(
            d.token_symbol[uid] for uid in d.labels.values() if uid in d.token_symbol)
        return {"document_id": d.id, "revision": d.revision, "physical_lines": d.lines,
                "functions": [{k: v for k, v in f.items()} for f in d.functions],
                "line_labels": [{"line": n, "token_id": uid,
                                 "symbol_id": d.token_symbol.get(uid)} for n, uid in d.labels.items()],
                "diagnostics": [self._diag_json(x) for x in d.diagnostics]}

    def get_document_structure_page(self, document_id: str, offset: int = 0, limit: int = 50) -> dict[str, Any]:
        d = self._doc(document_id)
        if offset < 0 or limit < 1 or limit > 200:
            raise WorkspaceError("INVALID_PAGE", "Use offset >= 0 and limit from 1 to 200")
        rows = self.get_document_structure(document_id)
        rows["physical_lines"] = [{k: line[k] for k in ("physical_line", "line_label", "statement_count")}
                                   for line in rows["physical_lines"][offset:offset + limit]]
        rows["functions"] = rows["functions"][offset:offset + limit]
        rows["line_labels"] = rows["line_labels"][offset:offset + limit]
        rows["diagnostics_total"] = len(rows["diagnostics"])
        rows["diagnostics"] = rows["diagnostics"][:50]
        rows["page"] = {"offset": offset, "limit": limit,
                         "physical_line_total": len(d.lines), "function_total": len(d.functions),
                         "line_label_total": len(d.labels)}
        return rows

    def list_symbols(self, document_id: str) -> list[dict[str, Any]]:
        d = self._doc(document_id)
        rows = [self._symbol_json(s) for s in d.symbols.values()]
        self._discovered_symbols.setdefault(document_id, set()).update(x["symbol_id"] for x in rows)
        return rows

    def list_symbols_page(self, document_id: str, offset: int = 0, limit: int = 50,
                          kind: str | None = None, name_query: str | None = None,
                          scope_id: str | None = None, exact_name: str | None = None,
                          unique: bool = False) -> dict[str, Any]:
        if offset < 0 or limit < 1 or limit > 200:
            raise WorkspaceError("INVALID_PAGE", "Use offset >= 0 and limit from 1 to 200")
        rows = [self._symbol_json(s) for s in self._doc(document_id).symbols.values()
                if (kind is None or s.kind == kind)
                and (name_query is None or name_query.casefold() in s.name.casefold())
                and (exact_name is None or exact_name.casefold() == s.name.casefold())
                and (scope_id is None or s.scope_id == scope_id)]
        discovered = self._discovered_symbols.setdefault(document_id, set())
        if unique and len(rows) == 1:
            discovered.add(rows[0]["symbol_id"])
        else:
            discovered.update(x["symbol_id"] for x in rows[offset:offset + limit])
        result = {"items": rows[offset:offset + limit], "total": len(rows),
                  "offset": offset, "limit": limit, "truncated": offset + limit < len(rows)}
        if unique:
            d = self._doc(document_id)
            result.update({"revision": d.revision, "unique": len(rows) == 1,
                           "ambiguous": len(rows) > 1,
                           "unique_symbol": rows[0] if len(rows) == 1 else None,
                           "diagnostic_summary": {"count": len(d.diagnostics),
                             "errors": sum(x.severity == "error" for x in d.diagnostics),
                             "warnings": sum(x.severity == "warning" for x in d.diagnostics)}})
            if len(rows) == 1:
                result["items"] = []
            else:
                result["items"] = rows[:min(limit, 5)]
        return result

    def symbol_was_discovered(self, document_id: str, symbol_id: str) -> bool:
        return symbol_id in self._discovered_symbols.get(document_id, set())

    def list_function_statements(self, document_id: str, function_id: str,
                                 offset: int = 0, limit: int = 50) -> dict[str, Any]:
        doc = self._doc(document_id)
        if offset < 0 or limit < 1 or limit > 200:
            raise WorkspaceError("INVALID_PAGE", "Use offset >= 0 and limit from 1 to 200")
        function = doc.symbols.get(function_id)
        if function is None or function.kind != "function":
            raise WorkspaceError("FUNCTION_NOT_FOUND", "Unknown numeric FUNCTION identity")
        rows = [row for row in doc.statements.values()
                if row["containing_function_id"] == function_id]
        rows.sort(key=lambda row: (row["line"], row["physical_statement_index"]))
        page = [self._statement_json(row) for row in rows[offset:offset + limit]]
        self._discovered_statements.setdefault(document_id, set()).update(x["statement_id"] for x in page)
        self._discovered_symbols.setdefault(document_id, set()).update(
            sid for row in page for sid in ([row["target_symbol_id"]] + row["referenced_symbol_ids"]))
        return {"document_id": document_id, "revision": doc.revision,
                "function_id": function_id, "items": page, "total": len(rows),
                "offset": offset, "limit": limit, "truncated": offset + limit < len(rows)}

    def statement_was_discovered(self, document_id: str, statement_id: str) -> bool:
        return statement_id in self._discovered_statements.get(document_id, set())

    @staticmethod
    def _statement_json(row: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in row.items() if key != "physical_statement_index"}

    @staticmethod
    def _symbol_json(s: Symbol) -> dict[str, Any]:
        row = {"symbol_id": s.id, "kind": s.kind, "name": s.name,
                "scope_id": s.scope_id, "document_id": s.document_id,
                "declaration_token_id": s.declaration_token, "line": s.line,
                "implicit": s.implicit, "reference_count": len(s.references)}
        if s.kind == "array":
            row.update({"element_type": "string" if s.name.endswith("$") else "numeric", "lower_bound": s.array_lower,
                        "upper_bound": s.array_upper,
                        "capacity": s.array_upper - s.array_lower + 1})
        return row

    def find_definition(self, document_id: str, symbol_id: str) -> dict[str, Any]:
        d = self._doc(document_id)
        s = d.symbols.get(symbol_id)
        if not s:
            raise WorkspaceError("SYMBOL_NOT_FOUND", "Unknown symbol identity")
        return self._symbol_json(s)

    def find_references(self, document_id: str, symbol_id: str) -> list[dict[str, Any]]:
        d = self._doc(document_id)
        s = d.symbols.get(symbol_id)
        if not s:
            raise WorkspaceError("SYMBOL_NOT_FOUND", "Unknown symbol identity")
        uids = [s.declaration_token] + s.references
        target_ids = set(uids)
        return [{"token_id": t.uid, "line": t.line, "column": t.column,
                 "end_column": t.column + len(t.text), "text": t.text,
                 "is_definition": t.uid == s.declaration_token}
                for t in d.tokens if t.uid in target_ids]

    def find_references_page(self, document_id: str, symbol_id: str,
                             offset: int = 0, limit: int = 100) -> dict[str, Any]:
        if offset < 0 or limit < 1 or limit > 500:
            raise WorkspaceError("INVALID_PAGE", "Use offset >= 0 and limit from 1 to 500")
        rows = self.find_references(document_id, symbol_id)
        return {"items": rows[offset:offset + limit], "total": len(rows),
                "offset": offset, "limit": limit, "truncated": offset + limit < len(rows)}

    def get_revision(self, document_id: str) -> int:
        return self._doc(document_id).revision

    def get_diagnostics(self, document_id: str) -> list[dict[str, Any]]:
        return [self._diag_json(d) for d in self._doc(document_id).diagnostics]

    def render_document(self, document_id: str) -> str:
        return self._doc(document_id).render()

    def _transaction(self, document_id: str, expected_revision: int,
                     operation: dict[str, Any]) -> dict[str, Any]:
        return self.apply_transaction(document_id, expected_revision, [operation])

    @staticmethod
    def _numeric_identifier(name: Any, role: str) -> str:
        if (not isinstance(name, str) or not IDENT_RE.fullmatch(name)
                or name.upper() in KEYWORDS
                or name[-1:] in ("$", "%", "!", "#")):
            raise WorkspaceError("INVALID_NAME", f"{role} must be an unsuffixed numeric BASIC identifier")
        return name

    @staticmethod
    def _function_identifier(name: Any) -> str:
        if (not isinstance(name, str) or not IDENT_RE.fullmatch(name)
                or name.endswith(("%", "!", "#"))
                or name.upper() in KEYWORDS or name.upper() in BUILTINS):
            raise WorkspaceError("INVALID_NAME", "Function name must be a BASIC identifier")
        return name

    @staticmethod
    def _local_identifier(name: Any) -> str:
        if (not isinstance(name, str) or not IDENT_RE.fullmatch(name)
                or name.endswith(("%", "!", "#")) or name.upper() in KEYWORDS):
            raise WorkspaceError("INVALID_NAME", "Local name must be a numeric or $ string identifier")
        return name

    @staticmethod
    def _new_tokens(parts: list[tuple[str, str]]) -> list[Token]:
        return [Token(opaque("t"), kind, text, 1, 0) for kind, text in parts]

    def _create_function_tokens(self, doc: Document, name: str, parameters: list[str]) -> None:
        name = self._function_identifier(name)
        if name.upper() in BUILTINS:
            raise WorkspaceError("NAME_COLLISION", f"{name} is a BASIC built-in name")
        if not isinstance(parameters, list) or len(parameters) > 6:
            raise WorkspaceError("UNSUPPORTED_ARITY", "Numeric functions support zero through six parameters")
        params = [self._numeric_identifier(p, "Parameter name") for p in parameters]
        folded = [p.casefold() for p in params]
        if len(set(folded)) != len(folded):
            raise WorkspaceError("NAME_COLLISION", "Function parameter names must be unique")
        if name.casefold() in folded:
            raise WorkspaceError("NAME_COLLISION", "A parameter cannot have the function's name")
        if any(s.normalized == name.casefold() and s.scope_id == "module" for s in doc.symbols.values()):
            raise WorkspaceError("NAME_COLLISION", f"{name} collides with an existing module symbol")
        parts: list[tuple[str, str]] = [("IDENT", "FUNCTION"), ("WS", " "),
                                        ("IDENT", name), ("PUNCT", "(")]
        for index, param in enumerate(params):
            if index:
                parts.append(("PUNCT", ","))
            parts.append(("IDENT", param))
        parts.extend([("PUNCT", ")"), ("NEWLINE", "\n"),
                      ("WS", "  "), ("IDENT", name), ("WS", " "),
                      ("OP", "="), ("WS", " "),
                      (("STRING", '""') if name.endswith("$") else ("NUMBER", "0")), ("NEWLINE", "\n"),
                      ("IDENT", "END"), ("WS", " "), ("IDENT", "FUNCTION"),
                      ("NEWLINE", "\n")])
        if doc.tokens and doc.tokens[-1].kind != "NEWLINE":
            doc.tokens.append(Token(opaque("t"), "NEWLINE", "\n", 1, 0))
        doc.tokens.extend(self._new_tokens(parts))
        self._recolumn(doc)

    @staticmethod
    def _function_row(doc: Document, function_id: str) -> dict[str, Any]:
        row = next((f for f in doc.functions if f["symbol_id"] == function_id), None)
        if row is None or row["kind"] != "function" or row["end_statement"] is None:
            raise WorkspaceError("FUNCTION_NOT_FOUND", "Expected a complete numeric FUNCTION identity")
        return row

    @staticmethod
    def _resolve_constructor_handles(expression: Any, handles: dict[str, str]) -> Any:
        """Replace transaction-local name handles with candidate symbol IDs."""
        if not isinstance(expression, dict):
            raise WorkspaceError("INVALID_EXPRESSION", "Expression must be a typed object")
        kind = expression.get("kind")
        if kind == "local_ref":
            if set(expression) != {"kind", "name"} or not isinstance(expression["name"], str):
                raise WorkspaceError("INVALID_TRANSACTION_HANDLE", "local_ref requires only a string name")
            key = expression["name"].casefold()
            if key not in handles:
                raise WorkspaceError("UNKNOWN_TRANSACTION_HANDLE",
                                     f"{expression['name']} is not a parameter or earlier local in this constructor")
            return {"kind": "symbol_ref", "symbol_id": handles[key]}
        if kind == "unary":
            return {**expression, "operand": Workspace._resolve_constructor_handles(
                expression.get("operand"), handles)}
        if kind == "binary" or kind == "compare":
            return {**expression,
                    "left": Workspace._resolve_constructor_handles(expression.get("left"), handles),
                    "right": Workspace._resolve_constructor_handles(expression.get("right"), handles)}
        if kind == "call":
            args = expression.get("arguments")
            if not isinstance(args, list):
                raise WorkspaceError("INVALID_EXPRESSION", "call arguments must be an array")
            return {**expression, "arguments": [Workspace._resolve_constructor_handles(x, handles)
                                                   for x in args]}
        if kind == "array_element":
            array_ref = expression.get("array_ref")
            if not isinstance(array_ref, dict):
                raise WorkspaceError("INVALID_ARRAY_REFERENCE", "array_ref must be a typed reference")
            if array_ref.get("kind") == "local_ref":
                name = array_ref.get("name")
                if not isinstance(name, str) or name.casefold() not in handles:
                    raise WorkspaceError("UNKNOWN_TRANSACTION_HANDLE", "array_ref name is not declared by this constructor")
                array_ref = {"kind": "symbol_ref", "symbol_id": handles[name.casefold()]}
            return {**expression, "array_ref": array_ref,
                    "index": Workspace._resolve_constructor_handles(expression.get("index"), handles)}
        # number and symbol_ref are validated by the shared expression parser.
        return expression

    def _insert_numeric_array_tokens(self, doc: Document, function_id: str,
                                     name: Any, upper_bound: Any,
                                     before_statement_id: str) -> str:
        if (not isinstance(name, str) or not IDENT_RE.fullmatch(name)
                or name.endswith(("%", "!", "#"))):
            raise WorkspaceError("INVALID_NAME", "Array name must be a BASIC identifier")
        if isinstance(upper_bound, bool) or not isinstance(upper_bound, int) or not 0 <= upper_bound <= 255:
            raise WorkspaceError("INVALID_ARRAY_BOUND", "Numeric array upper_bound must be an integer from 0 through 255")
        function = self._function_row(doc, function_id)
        result = doc.statements.get(before_statement_id)
        if result is None or result["containing_function_id"] != function_id:
            raise WorkspaceError("CROSS_SCOPE_STATEMENT", "Array declaration must be inserted inside its function")
        parts = [("WS", "  "), ("IDENT", "DIM"), ("WS", " "), ("IDENT", name),
                 ("PUNCT", "("), ("NUMBER", str(upper_bound)), ("PUNCT", ")"), ("NEWLINE", "\n")]
        generated = self._new_tokens(parts)
        line = result["line"]
        index = next((i for i, token in enumerate(doc.tokens) if token.line == line), None)
        if index is None:
            raise WorkspaceError("INVALID_STATEMENT_POSITION", "Could not locate result statement for DIM insertion")
        doc.tokens[index:index] = generated
        self._recolumn(doc)
        self._index(doc)
        row = self._function_row(doc, function_id)
        symbol_id = doc.token_symbol.get(generated[3].uid)
        symbol = doc.symbols.get(symbol_id) if symbol_id else None
        if (symbol is None or symbol.kind != "array" or symbol.scope_id != row["scope_id"]
                or doc.array_bounds.get(symbol_id) != (0, upper_bound)):
            raise WorkspaceError("BINDING_MISMATCH", "DIM declaration did not produce the expected local array")
        return symbol_id

    def _declare_shared_array_tokens(self, doc: Document, name: Any, upper_bound: Any) -> str:
        if (not isinstance(name, str) or not IDENT_RE.fullmatch(name) or name.upper() in KEYWORDS
                or name.endswith(("$", "%", "!", "#"))):
            raise WorkspaceError("INVALID_NAME", "Shared numeric array name must be an unsuffixed BASIC identifier")
        if isinstance(upper_bound, bool) or not isinstance(upper_bound, int) or not 0 <= upper_bound <= 255:
            raise WorkspaceError("INVALID_ARRAY_BOUND", "Shared array upper_bound must be from 0 through 255")
        if any(s.scope_id == "module" and s.normalized == name.casefold() for s in doc.symbols.values()):
            raise WorkspaceError("NAME_COLLISION", f"{name} already exists at module scope")
        tokens = self._new_tokens([("IDENT", "DIM"), ("WS", " "), ("IDENT", name),
                                   ("PUNCT", "("), ("NUMBER", str(upper_bound)),
                                   ("PUNCT", ")"), ("NEWLINE", "\n")])
        first_function_line = min((f["start_line"] for f in doc.functions), default=None)
        position = next((i for i, t in enumerate(doc.tokens)
                         if first_function_line is not None and t.line == first_function_line), len(doc.tokens))
        doc.tokens[position:position] = tokens
        self._recolumn(doc)
        self._index(doc)
        sid = doc.token_symbol.get(tokens[2].uid)
        symbol = doc.symbols.get(sid) if sid else None
        if symbol is None or symbol.kind != "array" or symbol.scope_id != "module":
            raise WorkspaceError("BINDING_MISMATCH", "Shared DIM did not produce a module array")
        return sid

    def _insert_array_assignment_tokens(self, doc: Document, function_id: str,
                                        array_id: str, index_expression: Any,
                                        value_expression: Any,
                                        before_statement_id: str) -> Token:
        from .typed_expr import expression_tokens, parse_request

        function = self._function_row(doc, function_id)
        array = doc.symbols.get(array_id)
        if array is None or array.kind != "array" or array.scope_id not in (function["scope_id"], "module"):
            raise WorkspaceError("UNSUPPORTED_TYPE", "Array assignment requires a local or module array")
        before = doc.statements.get(before_statement_id)
        if before is None or before["containing_function_id"] != function_id:
            raise WorkspaceError("CROSS_SCOPE_STATEMENT", "Array assignment must be inserted inside its function")
        parameters, symbols = self._expression_context(doc)
        index_expr, index_refs = parse_request(index_expression, symbols, function["scope_id"],
                                                function_id, parameters)
        value_expr, value_refs = parse_request(value_expression, symbols, function["scope_id"],
                                                function_id, parameters)
        index_tokens, emitted_index_refs = expression_tokens(index_expr, symbols)
        value_tokens, emitted_value_refs = expression_tokens(value_expr, symbols)
        if index_refs != emitted_index_refs or value_refs != emitted_value_refs:
            raise WorkspaceError("INTERNAL_BINDING_ERROR", "Array assignment expression binding list changed during serialization")
        parts = [("WS", "  "), ("IDENT", array.name), ("PUNCT", "(")] + index_tokens + [
            ("PUNCT", ")"), ("WS", " "), ("OP", "="), ("WS", " ")] + value_tokens + [("NEWLINE", "\n")]
        generated = self._new_tokens(parts)
        line = before["line"]
        position = next((i for i, token in enumerate(doc.tokens) if token.line == line), None)
        if position is None:
            raise WorkspaceError("INVALID_STATEMENT_POSITION", "Could not locate function result for array assignment")
        doc.tokens[position:position] = generated
        self._recolumn(doc)
        self._index(doc)
        actual = tuple(doc.token_symbol.get(token.uid) for token in generated if token.kind == "IDENT")
        expected = (array_id,) + index_refs + value_refs
        if actual != expected:
            raise WorkspaceError("BINDING_MISMATCH", "Generated array assignment resolved to different semantic identities",
                                 {"expected": list(expected), "actual": list(actual)})
        statement_id = doc._statement_ids.get(generated[1].uid)
        statement = doc.statements.get(statement_id) if statement_id else None
        if statement is None or statement["kind"] != "array_assignment" or statement["target_symbol_id"] != array_id:
            raise WorkspaceError("STATEMENT_CREATION_FAILED", "Indexed array assignment did not receive a stable statement identity")
        return generated[1]

    def _insert_statement_lines_before(self, doc: Document, before_statement_id: str,
                                       rows: list[tuple[list[tuple[str, str]], int]]) -> list[Token]:
        """Shared canonical token insertion primitive for constructed bodies and edits."""
        before = doc.statements.get(before_statement_id)
        if before is None:
            raise WorkspaceError("INVALID_STATEMENT_POSITION", "Could not locate the semantic insertion anchor")
        # Insert at the start of the anchor's physical line.  Inserting at the
        # statement's semantic anchor token can leave the line's existing
        # indentation before the new text and move that indentation away from
        # the original statement.  The constructor used to insert at the first
        # token on the line; preserve that formatting and identity behavior.
        position = next((i for i, token in enumerate(doc.tokens)
                         if token.line == before["line"]), None)
        if position is None:
            raise WorkspaceError("INVALID_STATEMENT_POSITION", "Could not locate the insertion anchor token")
        generated: list[Token] = []
        for parts, indent in rows:
            generated.extend(self._new_tokens([("WS", "  " * indent)] + parts + [("NEWLINE", "\n")]))
        doc.tokens[position:position] = generated
        self._recolumn(doc)
        self._index(doc)
        return generated

    def _insert_typed_if_block_tokens(self, doc: Document, function_id: str,
                                      before_statement_id: str,
                                      statement: dict[str, Any]) -> list[str]:
        """Insert one bounded, typed IF block before a verified result epilogue.

        This uses the same typed expression parser and token serializer as
        function construction. IF/ELSE/END IF markers intentionally have no
        statement IDs in the current canonical model; result assignments do.
        """
        from .typed_expr import expression_tokens, parse_request

        if not isinstance(statement, dict) or statement.get("kind") != "if" or set(statement) - {"kind", "condition", "then", "else"}:
            raise WorkspaceError("INVALID_IF", "Structural insertion requires one typed IF statement")
        if "condition" not in statement or not isinstance(statement.get("then"), list):
            raise WorkspaceError("INVALID_IF", "IF insertion requires a condition and then list")
        if "else" in statement and not isinstance(statement["else"], list):
            raise WorkspaceError("INVALID_IF", "IF else branch must be a statement list")
        if len(statement["then"]) + len(statement.get("else", [])) < 1:
            raise WorkspaceError("INVALID_IF", "Inserted IF must contain at least one assignment")

        function = self._function_row(doc, function_id)
        fn_symbol = doc.symbols.get(function_id)
        if fn_symbol is None or fn_symbol.kind != "function" or fn_symbol.name.endswith("$"):
            raise WorkspaceError("UNSUPPORTED_TYPE", "Typed IF insertion requires a numeric function")
        anchor = doc.statements.get(before_statement_id)
        if anchor is None or anchor.get("containing_function_id") != function_id:
            raise WorkspaceError("INVALID_INSERTION_ANCHOR", "Insertion anchor must be a statement in the selected function")
        if anchor.get("kind") != "assignment" or anchor.get("target_symbol_id") != function_id:
            raise WorkspaceError("INVALID_INSERTION_ANCHOR", "Insertion anchor must be a function-result assignment")
        later = [row for row in doc.statements.values()
                 if row.get("containing_function_id") == function_id
                 and row.get("physical_statement_index", -1) > anchor.get("physical_statement_index", -1)]
        if later:
            raise WorkspaceError("INVALID_INSERTION_ANCHOR", "Result assignment is not at the verified function-body boundary")
        # The supported generated epilogue is exactly RESULT = RESULT. It is
        # retained, and new authored control flow is inserted immediately
        # before it. This check prevents arbitrary mid-body insertion.
        if anchor.get("expression_summary", "").replace(" ", "").casefold() != fn_symbol.name.casefold():
            raise WorkspaceError("INVALID_INSERTION_ANCHOR", "Boundary assignment is not the generated result epilogue")

        params, symbols = self._expression_context(doc)
        rows: list[tuple[list[tuple[str, str]], int]] = []
        def verify_parts(parts: list[tuple[str, str]], expected: tuple[str, ...]) -> None:
            generated_names = tuple(text for kind, text in parts if kind == "IDENT" and text.upper() not in KEYWORDS)
            expected_names = tuple(doc.symbols[sid].name for sid in expected)
            if generated_names != expected_names:
                raise WorkspaceError("BINDING_MISMATCH", "Typed IF token references do not match resolved semantic identities")

        cond_expr, cond_refs = parse_request(statement["condition"], symbols, function["scope_id"], function_id, params)
        cond_parts, emitted_cond_refs = expression_tokens(cond_expr, symbols)
        if cond_refs != emitted_cond_refs:
            raise WorkspaceError("INTERNAL_BINDING_ERROR", "IF condition references changed during token emission")
        cond_line = [("IDENT", "IF"), ("WS", " ")] + cond_parts + [("WS", " "), ("IDENT", "THEN")]
        verify_parts(cond_line, cond_refs)
        rows.append((cond_line, 1))

        def branch(items: list[Any], label: str) -> None:
            if len(items) > 64:
                raise WorkspaceError("INVALID_IF", f"IF {label} branch exceeds 64 statements")
            for item in items:
                if not isinstance(item, dict) or set(item) != {"kind", "target", "expression"} or item.get("kind") != "assign" or item.get("target") != {"kind": "result"}:
                    raise WorkspaceError("INVALID_BODY_STATEMENT", "Inserted IF branches may contain only typed function-result assignments")
                expr, refs = parse_request(item["expression"], symbols, function["scope_id"], function_id, params)
                expr_parts, emitted_refs = expression_tokens(expr, symbols)
                if refs != emitted_refs:
                    raise WorkspaceError("INTERNAL_BINDING_ERROR", "Assignment references changed during token emission")
                line = [("IDENT", fn_symbol.name), ("WS", " "), ("OP", "="), ("WS", " ")] + expr_parts
                verify_parts(line, (function_id,) + refs)
                rows.append((line, 2))

        branch(statement["then"], "then")
        if statement.get("else"):
            rows.append(([ ("IDENT", "ELSE") ], 1))
            branch(statement["else"], "else")
        rows.append(([("IDENT", "END"), ("WS", " "), ("IDENT", "IF")], 1))

        generated = self._insert_statement_lines_before(doc, before_statement_id, rows)
        created = [doc._statement_ids[token.uid] for token in generated
                   if token.kind == "IDENT" and token.text.casefold() == fn_symbol.name.casefold()
                   and token.uid in doc._statement_ids]
        if len(created) != len(statement["then"]) + len(statement.get("else", [])):
            raise WorkspaceError("STATEMENT_CREATION_FAILED", "Inserted result assignments did not receive stable statement identities")
        # Re-resolve every emitted identifier after canonical indexing. This
        # proves the serializer did not bind a call or result to another symbol.
        actual = tuple(doc.token_symbol.get(token.uid) for token in generated
                       if token.kind == "IDENT" and token.text.upper() not in KEYWORDS)
        expected = cond_refs
        for items in (statement["then"], statement.get("else", [])):
            for item in items:
                _, refs = parse_request(item["expression"], symbols, function["scope_id"], function_id, params)
                expected += (function_id,) + refs
        if actual != expected:
            raise WorkspaceError("BINDING_MISMATCH", "Inserted IF did not preserve the requested semantic bindings",
                                 {"expected": list(expected), "actual": list(actual)})
        return created

    def _populate_constructed_function(self, doc: Document, operation: dict[str, Any]) -> None:
        """Build locals and result within the private candidate transaction."""
        from .typed_expr import expression_tokens, parse_request

        name = self._function_identifier(operation.get("name"))
        function = next((f for f in doc.functions if f["kind"] == "function"
                         and f["name"].casefold() == name.casefold()
                         and doc.symbols.get(f["symbol_id"]) is not None
                         and doc.symbols[f["symbol_id"]].scope_id == "module"), None)
        if function is None:
            raise WorkspaceError("FUNCTION_CREATION_FAILED", "Created function was not indexed")
        function_id = function["symbol_id"]
        row = self._function_row(doc, function_id)
        handles = {doc.symbols[sid].name.casefold(): sid for sid in row["parameters"]}
        handles[name.casefold()] = function_id
        result_statement = next((s for s in doc.statements.values()
                                 if s["containing_function_id"] == function_id
                                 and s["target_symbol_id"] == function_id), None)
        if result_statement is None:
            raise WorkspaceError("STATEMENT_CREATION_FAILED", "Function result assignment was not indexed")
        result_statement_id = result_statement["statement_id"]

        arrays_spec = operation.get("arrays", [])
        if not isinstance(arrays_spec, list) or len(arrays_spec) > 32:
            raise WorkspaceError("INVALID_ARRAYS", "arrays must be an array of at most 32 declarations")
        for array_spec in arrays_spec:
            if not isinstance(array_spec, dict) or set(array_spec) - {"name", "upper_bound", "element_type"} or not {"name", "upper_bound"}.issubset(array_spec):
                raise WorkspaceError("INVALID_ARRAYS", "Each array declaration requires name and upper_bound, with optional element_type")
            element_type = array_spec.get("element_type", "string" if str(array_spec["name"]).endswith("$") else "numeric")
            if element_type not in ("numeric", "string") or (element_type == "string") != str(array_spec["name"]).endswith("$"):
                raise WorkspaceError("TYPE_MISMATCH", "String arrays require a $ name and numeric arrays must be unsuffixed")
            array_id = self._insert_numeric_array_tokens(doc, function_id,
                array_spec["name"], array_spec["upper_bound"], result_statement_id)
            array_name = doc.symbols[array_id].name.casefold()
            if array_name in handles:
                raise WorkspaceError("NAME_COLLISION", f"{array_name} already names a parameter or local")
            handles[array_name] = array_id
            result_statement = doc.statements.get(result_statement_id)

        locals_spec = operation.get("locals", [])
        if not isinstance(locals_spec, list) or len(locals_spec) > 16:
            raise WorkspaceError("INVALID_LOCALS", "locals must be an array of at most 16 declarations")
        for local in locals_spec:
            if not isinstance(local, dict) or set(local) != {"name", "expression"}:
                raise WorkspaceError("INVALID_LOCALS", "Each local requires exactly name and expression")
            local_name = self._local_identifier(local["name"])
            key = local_name.casefold()
            if key in handles:
                raise WorkspaceError("NAME_COLLISION", f"{local_name} already exists in this function")
            resolved = self._resolve_constructor_handles(local["expression"], handles)
            generated, expected_refs, target_token = self._insert_assignment_tokens(
                doc, function_id, {"kind": "local", "name": local_name},
                resolved, result_statement_id)
            self._index(doc)
            self._verify_expression_bindings(doc, generated, expected_refs)
            target_id = doc.token_symbol.get(target_token.uid)
            target_symbol = doc.symbols.get(target_id) if target_id else None
            if (target_symbol is None or target_symbol.kind != "variable"
                    or target_symbol.scope_id != row["scope_id"]):
                raise WorkspaceError("BINDING_MISMATCH", "Constructed local did not bind in the function scope")
            handles[key] = target_id
            result_statement = doc.statements.get(result_statement_id)
            if result_statement is None:
                raise WorkspaceError("STATEMENT_CREATION_FAILED", "Result statement identity changed during construction")

        array_assignments = operation.get("array_assignments", [])
        if not isinstance(array_assignments, list) or len(array_assignments) > 4096:
            raise WorkspaceError("INVALID_ARRAY_ASSIGNMENTS", "array_assignments must contain at most 4096 rows")
        for assignment in array_assignments:
            if (not isinstance(assignment, dict)
                    or set(assignment) != {"array_ref", "index", "expression"}):
                raise WorkspaceError("INVALID_ARRAY_ASSIGNMENT", "Each row requires array_ref, index, and expression")
            array_ref = assignment["array_ref"]
            if (not isinstance(array_ref, dict)
                    or array_ref.get("kind") not in ("local_ref", "symbol_ref")):
                raise WorkspaceError("INVALID_ARRAY_REFERENCE", "array_ref must be a local_ref name or symbol_ref ID")
            if array_ref["kind"] == "local_ref":
                handle_name = array_ref.get("name")
                if not isinstance(handle_name, str) or handle_name.casefold() not in handles:
                    raise WorkspaceError("UNKNOWN_TRANSACTION_HANDLE", "Array assignment names an undeclared array")
                array_id = handles[handle_name.casefold()]
            else:
                array_id = array_ref.get("symbol_id")
            resolved_index = self._resolve_constructor_handles(assignment["index"], handles)
            resolved_value = self._resolve_constructor_handles(assignment["expression"], handles)
            self._insert_array_assignment_tokens(doc, function_id, array_id, resolved_index,
                                                 resolved_value, result_statement_id)
            result_statement = doc.statements.get(result_statement_id)

        structured_body = operation.get("body", [])
        if not isinstance(structured_body, list) or len(structured_body) > 4096:
            raise WorkspaceError("INVALID_BODY", "body must contain at most 4096 typed statements")

        def append_line(parts: list[tuple[str, str]], indent: int) -> list[Token]:
            current_result = doc.statements.get(result_statement_id)
            if current_result is None:
                raise WorkspaceError("STATEMENT_CREATION_FAILED", "Function result anchor disappeared")
            return self._insert_statement_lines_before(doc, result_statement_id, [(parts, indent + 1)])

        def checked_expression(request: Any) -> tuple[list[tuple[str, str]], tuple[str, ...]]:
            resolved = self._resolve_constructor_handles(request, handles)
            params, symbols = self._expression_context(doc)
            parsed, references = parse_request(resolved, symbols, row["scope_id"],
                                               function_id, params)
            parts, emitted = expression_tokens(parsed, symbols)
            if references != emitted:
                raise WorkspaceError("INTERNAL_BINDING_ERROR", "Control expression binding list changed")
            return parts, references

        def verify_generated(generated: list[Token], expected: tuple[str, ...], *,
                             target_symbol: str | None = None) -> None:
            expr_ids = tuple(doc.token_symbol.get(token.uid) for token in generated
                             if token.kind == "IDENT" and token.text.upper() not in KEYWORDS)
            wanted = ((target_symbol,) if target_symbol is not None else ()) + expected
            if expr_ids != wanted:
                raise WorkspaceError("BINDING_MISMATCH", "Structured body tokens resolved to unexpected symbols",
                                     {"expected": list(wanted), "actual": list(expr_ids)})

        def append_block(items: list[dict[str, Any]], depth: int = 0) -> None:
            if depth > 16:
                raise WorkspaceError("CONTROL_DEPTH", "Nested IF/FOR blocks are limited to depth 16")
            for item in items:
                if not isinstance(item, dict) or not isinstance(item.get("kind"), str):
                    raise WorkspaceError("INVALID_BODY_STATEMENT", "Each body item requires a typed kind")
                kind = item["kind"]
                if kind == "assign":
                    if set(item) != {"kind", "target", "expression"} or not isinstance(item["target"], dict):
                        raise WorkspaceError("INVALID_BODY_STATEMENT", "assign requires target and expression")
                    target = item["target"]
                    if target == {"kind": "result"}:
                        target_id, target_name = function_id, doc.symbols[function_id].name
                    elif set(target) == {"kind", "name"} and target.get("kind") == "local":
                        local_name = target["name"]
                        target_id = handles.get(local_name.casefold()) if isinstance(local_name, str) else None
                        target_symbol = doc.symbols.get(target_id) if target_id else None
                        if target_symbol is None or target_symbol.kind != "variable" or target_symbol.scope_id != row["scope_id"]:
                            raise WorkspaceError("INVALID_ASSIGNMENT_TARGET", "Body assignment target must be a declared numeric local")
                        target_name = target_symbol.name
                    else:
                        raise WorkspaceError("INVALID_ASSIGNMENT_TARGET", "Body target must be result or a local_ref name")
                    expression_parts, refs = checked_expression(item["expression"])
                    generated = append_line([("IDENT", target_name), ("WS", " "), ("OP", "="),
                                             ("WS", " ")] + expression_parts, depth)
                    verify_generated(generated, refs, target_symbol=target_id)
                elif kind == "array_assign":
                    if set(item) != {"kind", "array_ref", "index", "expression"}:
                        raise WorkspaceError("INVALID_BODY_STATEMENT", "array_assign requires array_ref, index, and expression")
                    ref = item["array_ref"]
                    if (not isinstance(ref, dict) or ref.get("kind") not in ("local_ref", "symbol_ref")):
                        raise WorkspaceError("INVALID_ARRAY_REFERENCE", "Body array_ref must be a constructor handle or discovered symbol")
                    if ref["kind"] == "local_ref":
                        if not isinstance(ref.get("name"), str):
                            raise WorkspaceError("INVALID_ARRAY_REFERENCE", "Constructor array handle requires a name")
                        array_id = handles.get(ref["name"].casefold())
                    else:
                        array_id = ref.get("symbol_id")
                    array = doc.symbols.get(array_id) if array_id else None
                    if array is None or array.kind != "array" or array.scope_id not in (row["scope_id"], "module"):
                        raise WorkspaceError("INVALID_ARRAY_REFERENCE", "array_assign must target a local or module array")
                    index_parts, index_refs = checked_expression(item["index"])
                    value_parts, value_refs = checked_expression(item["expression"])
                    generated = append_line([("IDENT", array.name), ("PUNCT", "(")] + index_parts +
                        [("PUNCT", ")"), ("WS", " "), ("OP", "="), ("WS", " ")] + value_parts, depth)
                    verify_generated(generated, (array_id,) + index_refs + value_refs)
                elif kind == "if":
                    if set(item) - {"kind", "condition", "then", "else"} or "condition" not in item or not isinstance(item.get("then"), list) or not isinstance(item.get("else", []), list):
                        raise WorkspaceError("INVALID_IF", "if requires a typed condition, then list, and optional else list")
                    condition_parts, condition_refs = checked_expression(item["condition"])
                    generated = append_line([("IDENT", "IF"), ("WS", " ")] + condition_parts +
                                            [("WS", " "), ("IDENT", "THEN")], depth)
                    verify_generated(generated, condition_refs)
                    append_block(item["then"], depth + 1)
                    if item.get("else"):
                        append_line([("IDENT", "ELSE")], depth)
                        append_block(item["else"], depth + 1)
                    append_line([("IDENT", "END"), ("WS", " "), ("IDENT", "IF")], depth)
                elif kind == "for":
                    required = {"kind", "variable", "start", "end", "body"}
                    if not required.issubset(item) or set(item) - required - {"step"} or not isinstance(item["body"], list):
                        raise WorkspaceError("INVALID_FOR", "for requires variable, constant start/end, optional step, and body list")
                    loop_name = self._numeric_identifier(item["variable"], "Loop variable")
                    key = loop_name.casefold()
                    if key in handles:
                        raise WorkspaceError("NAME_COLLISION", f"Loop variable {loop_name} already names a parameter, local, or array")
                    start_parts, start_refs = checked_expression(item["start"])
                    end_parts, end_refs = checked_expression(item["end"])
                    step_parts, step_refs = checked_expression(item.get("step", {"kind": "number", "value": 1}))
                    if start_refs or end_refs or step_refs:
                        raise WorkspaceError("DYNAMIC_LOOP_BOUND", "FOR bounds and step must be numeric constants")
                    # The projection performs the exact static trip-count validation.
                    parts = [("IDENT", "FOR"), ("WS", " "), ("IDENT", loop_name), ("WS", " "),
                             ("OP", "="), ("WS", " ")] + start_parts + [("WS", " "), ("IDENT", "TO"),
                             ("WS", " ")] + end_parts
                    if "step" in item:
                        parts += [("WS", " "), ("IDENT", "STEP"), ("WS", " ")] + step_parts
                    generated = append_line(parts, depth)
                    self._index(doc)
                    loop_token = next((token for token in generated if token.kind == "IDENT" and token.text.casefold() == key), None)
                    loop_id = doc.token_symbol.get(loop_token.uid) if loop_token else None
                    loop_symbol = doc.symbols.get(loop_id) if loop_id else None
                    if loop_symbol is None or loop_symbol.kind != "variable" or loop_symbol.scope_id != row["scope_id"]:
                        raise WorkspaceError("BINDING_MISMATCH", "FOR variable did not bind as a function local")
                    handles[key] = loop_id
                    verify_generated(generated, start_refs + end_refs + step_refs, target_symbol=loop_id)
                    append_block(item["body"], depth + 1)
                    next_line = append_line([("IDENT", "NEXT"), ("WS", " "), ("IDENT", loop_name)], depth)
                    verify_generated(next_line, (), target_symbol=loop_id)
                else:
                    raise WorkspaceError("UNSUPPORTED_BODY_STATEMENT", f"Unsupported typed statement kind {kind!r}")

        append_block(structured_body)

        def assigns_result(items: list[dict[str, Any]]) -> bool:
            for item in items:
                if item.get("kind") == "assign" and item.get("target") == {"kind": "result"}:
                    return True
                if item.get("kind") == "if" and (assigns_result(item.get("then", [])) or
                                                   assigns_result(item.get("else", []))):
                    return True
                if item.get("kind") == "for" and assigns_result(item.get("body", [])):
                    return True
            return False

        # Keep the result anchor as a no-op after an explicitly constructed
        # result assignment. The MIR worker initializes the result register to
        # zero, and the typed body owns any intended initial value (for example
        # -1 before a search loop).
        if "expression" not in operation and assigns_result(structured_body):
            generated, expected_refs = self._edit_expression_tokens(
                doc, result_statement_id, {"kind": "symbol_ref", "symbol_id": function_id})
            self._index(doc)
            self._verify_expression_bindings(doc, generated, expected_refs)

        if "expression" in operation:
            resolved = self._resolve_constructor_handles(operation["expression"], handles)
            generated, expected_refs = self._edit_expression_tokens(doc, result_statement_id, resolved)
            self._index(doc)
            self._verify_expression_bindings(doc, generated, expected_refs)


    @staticmethod
    def _expression_context(doc: Document) -> tuple[dict[str, int], dict[str, Any]]:
        params = {row["symbol_id"]: len(row["parameters"])
                  for row in doc.functions if row["kind"] == "function"}
        return params, doc.symbols

    @staticmethod
    def _verify_expression_bindings(doc: Document, generated: list[Token], expected: tuple[str, ...]) -> None:
        identifier_tokens = [token for token in generated if token.kind == "IDENT"]
        actual = tuple(doc.token_symbol.get(token.uid) for token in identifier_tokens)
        if actual != expected:
            raise WorkspaceError("BINDING_MISMATCH", "Generated expression did not resolve to its requested symbol identities",
                                 {"expected": list(expected), "actual": list(actual)})

    def _insert_assignment_tokens(self, doc: Document, function_id: str, target: dict[str, Any],
                                  expression: Any, before_statement_id: str | None) -> tuple[list[Token], tuple[str, ...], Token]:
        from .typed_expr import expression_tokens, parse_request

        function = self._function_row(doc, function_id)
        if not isinstance(target, dict) or target.get("kind") not in ("result", "local"):
            raise WorkspaceError("INVALID_ASSIGNMENT_TARGET", "target must be {kind: result} or {kind: local, name}")
        owner = doc.symbols[function_id]
        if target["kind"] == "result":
            if set(target) != {"kind"}:
                raise WorkspaceError("INVALID_ASSIGNMENT_TARGET", "result target accepts only kind")
            target_name = owner.name
        else:
            if set(target) != {"kind", "name"}:
                raise WorkspaceError("INVALID_ASSIGNMENT_TARGET", "local target requires kind and name")
            target_name = self._local_identifier(target["name"])
            if target_name.casefold() == owner.name.casefold():
                raise WorkspaceError("NAME_COLLISION", "A local cannot have the containing function's name")
            if any(s.scope_id == function["scope_id"] and s.normalized == target_name.casefold()
                   for s in doc.symbols.values()):
                raise WorkspaceError("NAME_COLLISION", f"{target_name} already exists in this function")
        function_parameters, symbols = self._expression_context(doc)
        parsed, expected_refs = parse_request(expression, symbols, function["scope_id"],
                                               function_id, function_parameters)
        expression_parts, token_refs = expression_tokens(parsed, symbols)
        if token_refs != expected_refs:
            raise WorkspaceError("INTERNAL_BINDING_ERROR", "Typed expression serializer changed its binding list")
        generated = self._new_tokens([("WS", "  "), ("IDENT", target_name), ("WS", " "),
                                      ("OP", "="), ("WS", " ")] + expression_parts + [("NEWLINE", "\n")])
        if before_statement_id is not None:
            before = doc.statements.get(before_statement_id)
            if before is None:
                raise WorkspaceError("STATEMENT_NOT_FOUND", "Insertion position statement is unknown")
            if before["containing_function_id"] != function_id:
                raise WorkspaceError("CROSS_SCOPE_STATEMENT", "Insertion position must be inside the selected function")
            destination_line = before["line"]
        else:
            destination_line = function["end_line"]
        insertion_index = next((i for i, token in enumerate(doc.tokens) if token.line == destination_line), None)
        if insertion_index is None:
            raise WorkspaceError("INVALID_STATEMENT_POSITION", "Could not resolve the semantic insertion point")
        doc.tokens[insertion_index:insertion_index] = generated
        self._recolumn(doc)
        return [token for token in generated[5:-1] if token.kind == "IDENT"], expected_refs, generated[1]

    @staticmethod
    def _assignment_rhs_bounds(doc: Document, anchor_token_id: str) -> tuple[int, int, int]:
        anchor = next((i for i, token in enumerate(doc.tokens) if token.uid == anchor_token_id), None)
        if anchor is None:
            raise WorkspaceError("STATEMENT_NOT_FOUND", "Assignment anchor token no longer exists")
        start = anchor
        while start > 0 and doc.tokens[start - 1].line == doc.tokens[anchor].line \
                and not (doc.tokens[start - 1].kind == "PUNCT" and doc.tokens[start - 1].text == ":"):
            start -= 1
        end = anchor
        while end < len(doc.tokens) and doc.tokens[end].line == doc.tokens[anchor].line \
                and doc.tokens[end].kind not in ("COMMENT", "NEWLINE") \
                and not (doc.tokens[end].kind == "PUNCT" and doc.tokens[end].text == ":"):
            end += 1
        equals = next((i for i in range(anchor + 1, end)
                       if doc.tokens[i].kind == "OP" and doc.tokens[i].text == "="), None)
        if equals is None:
            raise WorkspaceError("UNSUPPORTED_STATEMENT", "Selected statement is no longer a simple assignment")
        rhs_start = equals + 1
        while rhs_start < end and doc.tokens[rhs_start].kind == "WS":
            rhs_start += 1
        rhs_end = end
        while rhs_end > rhs_start and doc.tokens[rhs_end - 1].kind == "WS":
            rhs_end -= 1
        if rhs_start == rhs_end:
            raise WorkspaceError("INVALID_EXPRESSION", "Selected assignment has no right-hand expression")
        return rhs_start, rhs_end, end

    def _edit_expression_tokens(self, doc: Document, statement_id: str, expression: Any) -> tuple[list[Token], tuple[str, ...]]:
        from .typed_expr import expression_tokens, parse_request

        statement = doc.statements.get(statement_id)
        if statement is None:
            raise WorkspaceError("STATEMENT_NOT_FOUND", "Unknown assignment statement identity")
        function = self._function_row(doc, statement["containing_function_id"])
        params, symbols = self._expression_context(doc)
        parsed, expected_refs = parse_request(expression, symbols, function["scope_id"],
                                               function["symbol_id"], params)
        parts, token_refs = expression_tokens(parsed, symbols)
        if token_refs != expected_refs:
            raise WorkspaceError("INTERNAL_BINDING_ERROR", "Typed expression serializer changed its binding list")
        generated = self._new_tokens(parts)
        rhs_start, rhs_end, _ = self._assignment_rhs_bounds(doc, statement["anchor_token_id"])
        doc.tokens[rhs_start:rhs_end] = generated
        self._recolumn(doc)
        return generated, expected_refs

    def _edit_numeric_literal_at_path(self, doc: Document, operation: dict[str, Any]) -> str | None:
        """Replace one numeric leaf selected through the typed projection.

        This deliberately small primitive supports an assignment RHS root or
        the right operand of a simple IF comparison. It preserves the selected
        literal token UID and all declaration/statement anchors.
        """
        from .projection import (Assignment, ForLoop, IfBlock, _ExpressionParser,
                                 _statements, build_projection_from_document)

        allowed = {"operation", "function_id", "target_kind", "statement_id", "control_path",
                   "expression_path", "expected_value", "replacement_value"}
        if set(operation) - allowed:
            raise WorkspaceError("INVALID_LITERAL_EDIT", "Numeric literal edit contains unsupported fields")
        function_id = operation.get("function_id")
        function_row = doc.symbols.get(function_id)
        if function_row is None or function_row.kind != "function" or function_row.name.endswith("$"):
            raise WorkspaceError("FUNCTION_NOT_FOUND", "Literal edit function identity is not a numeric function")
        expected = operation.get("expected_value")
        replacement = operation.get("replacement_value")
        for value, label in ((expected, "expected_value"), (replacement, "replacement_value")):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise WorkspaceError("INVALID_LITERAL_EDIT", f"{label} must be a finite number")
        expression_path = operation.get("expression_path")
        if not isinstance(expression_path, list) or any(isinstance(i, bool) or not isinstance(i, int) for i in expression_path):
            raise WorkspaceError("INVALID_LITERAL_PATH", "expression_path must be an array of child indexes")

        projection = build_projection_from_document(self, doc, doc.revision)
        function = next((row for row in projection.functions if row.symbol_id == function_id), None)
        if function is None:
            raise WorkspaceError("FUNCTION_NOT_FOUND", "Numeric function is missing from the typed projection")
        target_kind = operation.get("target_kind")
        target_node: Any = None
        expression = None
        statement_id: str | None = None
        if target_kind == "assignment_rhs":
            statement_id = operation.get("statement_id")
            if not isinstance(statement_id, str) or operation.get("control_path") is not None or expression_path:
                raise WorkspaceError("INVALID_LITERAL_PATH", "Assignment RHS edits require a statement_id and an empty expression_path")

            def find_assignment(items):
                for item in items:
                    if isinstance(item, Assignment) and item.statement_id == statement_id:
                        return item
                    if isinstance(item, (IfBlock, ForLoop)):
                        for children in ((item.then_body, item.else_body) if isinstance(item, IfBlock) else (item.body,)):
                            found = find_assignment(children)
                            if found is not None:
                                return found
                return None

            target_node = find_assignment(function.statements)
            if target_node is None or target_node.target_symbol_id != function_id:
                raise WorkspaceError("STATEMENT_NOT_FOUND", "Assignment identity is not a result assignment in the selected function")
            expression = target_node.expression
        elif target_kind == "if_condition_rhs":
            if operation.get("statement_id") is not None or expression_path != [1]:
                raise WorkspaceError("INVALID_LITERAL_PATH", "IF comparison edit requires control_path and expression_path [1]")
            path = operation.get("control_path")
            if not isinstance(path, list) or not path:
                raise WorkspaceError("INVALID_LITERAL_PATH", "IF condition edit requires a nonempty control_path")
            block = function.statements
            target_node = None
            for step_index, step in enumerate(path):
                if not isinstance(step, dict) or set(step) != {"block", "index"}:
                    raise WorkspaceError("INVALID_LITERAL_PATH", "Each control_path step requires block and index")
                block_name, index = step["block"], step["index"]
                if block_name not in ("body", "then", "else") or isinstance(index, bool) or not isinstance(index, int):
                    raise WorkspaceError("INVALID_LITERAL_PATH", "Unsupported control_path block or index")
                if not 0 <= index < len(block):
                    raise WorkspaceError("INVALID_LITERAL_PATH", "control_path index is outside the selected block")
                target_node = block[index]
                if step_index + 1 < len(path):
                    next_step = path[step_index + 1]
                    next_block = next_step.get("block") if isinstance(next_step, dict) else None
                    if isinstance(target_node, IfBlock):
                        if next_block == "then": block = target_node.then_body
                        elif next_block == "else": block = target_node.else_body
                        else: raise WorkspaceError("INVALID_LITERAL_PATH", "IF children use then or else blocks")
                    elif isinstance(target_node, ForLoop) and next_block == "body":
                        block = target_node.body
                    else:
                        raise WorkspaceError("INVALID_LITERAL_PATH", "Intermediate control_path item has no child block")
            if not isinstance(target_node, IfBlock):
                raise WorkspaceError("INVALID_LITERAL_PATH", "The selected control-flow node is not an IF")
            expression = target_node.condition
            if expression.kind != "compare" or len(expression.children) != 2:
                raise WorkspaceError("INVALID_LITERAL_PATH", "Only a two-operand comparison IF condition is editable")
        else:
            raise WorkspaceError("INVALID_LITERAL_EDIT", "target_kind must be assignment_rhs or if_condition_rhs")

        selected = expression
        for child_index in expression_path:
            if not 0 <= child_index < len(selected.children):
                raise WorkspaceError("INVALID_LITERAL_PATH", "expression_path does not resolve in the typed expression")
            selected = selected.children[child_index]
        if selected.kind != "number" or float(selected.value) != float(expected):
            raise WorkspaceError("EXPECTED_LITERAL_MISMATCH", "Selected typed expression is not the expected numeric literal",
                                 {"expected": float(expected), "actual_kind": selected.kind, "actual_value": selected.value})

        doc_token_index = {token.uid: i for i, token in enumerate(doc.tokens)}
        literal_token: Token | None = None
        if target_kind == "assignment_rhs":
            row = doc.statements.get(statement_id)
            if row is None or row["containing_function_id"] != function_id:
                raise WorkspaceError("STATEMENT_NOT_FOUND", "Assignment identity is not owned by the selected function")
            start, end, _ = self._assignment_rhs_bounds(doc, row["anchor_token_id"])
            rhs = [doc.tokens[i] for i in range(start, end) if doc.tokens[i].kind != "WS"]
            if len(rhs) != 1 or rhs[0].kind != "NUMBER" or float(rhs[0].text) != float(expected):
                raise WorkspaceError("EXPECTED_LITERAL_MISMATCH", "Assignment RHS token does not match the selected typed literal")
            literal_token = rhs[0]
        else:
            rows = [tokens for tokens in _statements(doc) if tokens and tokens[0].line == target_node.line]
            if len(rows) != 1 or rows[0][0].text.upper() != "IF" or rows[0][-1].text.upper() != "THEN":
                raise WorkspaceError("AMBIGUOUS_LITERAL_TARGET", "Could not uniquely resolve the selected IF condition tokens")
            condition_tokens = rows[0][1:-1]
            parsed = _ExpressionParser(doc, tuple(condition_tokens), function).parse_all()
            if parsed != expression:
                raise WorkspaceError("LITERAL_PATH_MISMATCH", "Canonical IF tokens do not match the selected projected expression")
            # This bounded operation edits only the right operand [1] of a
            # top-level numeric comparison. Strip harmless enclosing parens,
            # then require one numeric token on the right.
            rhs = list(condition_tokens)
            while len(rhs) >= 2 and rhs[0].text == "(" and rhs[-1].text == ")":
                depth = 0
                closes_at_end = False
                for i, token in enumerate(rhs):
                    if token.text == "(": depth += 1
                    elif token.text == ")":
                        depth -= 1
                        if depth == 0:
                            closes_at_end = i == len(rhs) - 1
                            break
                if not closes_at_end: break
                rhs = rhs[1:-1]
            depth = 0
            operators = []
            for i, token in enumerate(rhs):
                if token.text == "(": depth += 1
                elif token.text == ")": depth -= 1
                elif depth == 0 and token.kind == "OP" and token.text in ("=", "<>", "<", "<=", ">", ">="):
                    operators.append(i)
            if len(operators) != 1:
                raise WorkspaceError("AMBIGUOUS_LITERAL_TARGET", "IF comparison does not have one top-level comparison operator")
            rhs_operand = [token for token in rhs[operators[0] + 1:] if token.kind != "WS"]
            if len(rhs_operand) != 1 or rhs_operand[0].kind != "NUMBER" or float(rhs_operand[0].text) != float(expected):
                raise WorkspaceError("LITERAL_PATH_MISMATCH", "IF comparison right operand does not match the selected literal path")
            literal_token = rhs_operand[0]

        if literal_token is None or literal_token.uid not in doc_token_index:
            raise WorkspaceError("LITERAL_TOKEN_NOT_FOUND", "Resolved numeric literal token is missing")
        literal_token.text = format(float(replacement), ".15g")
        self._recolumn(doc)
        return statement_id

    def _prepare_transaction(self, document_id: str, expected_revision: int,
                             operations: list[dict[str, Any]], include_diff: bool = False) -> tuple[Document, dict[str, Any]]:
        current = self._doc(document_id)
        if current.revision != expected_revision:
            raise WorkspaceError("STALE_REVISION", f"Expected revision {expected_revision}, current revision is {current.revision}", {"current_revision": current.revision})
        if not operations:
            raise WorkspaceError("EMPTY_TRANSACTION", "A semantic transaction needs at least one operation")
        candidate = copy.deepcopy(current)
        touched: dict[str, str] = {}
        touched_statements: set[str] = set()
        for operation in operations:
            kind = operation.get("operation")
            if kind == "rename_symbol":
                sid = operation["symbol_id"]
                if sid not in candidate.symbols:
                    raise WorkspaceError("SYMBOL_NOT_FOUND", "Unknown symbol identity")
                touched.setdefault(sid, candidate.symbols[sid].name)
                self._rename(candidate, sid, operation["new_name"])
            elif kind == "renumber_line":
                old = int(operation["old_line"])
                if old in candidate.labels:
                    label_uid = candidate.labels[old]
                    label_symbol = next((s for s in candidate.symbols.values() if s.kind == "line_label" and s.declaration_token == label_uid), None)
                    if label_symbol:
                        touched.setdefault(label_symbol.id, label_symbol.name)
                self._renumber(candidate, old, int(operation["new_line"]))
            elif kind == "move_function":
                sid = operation["symbol_id"]
                if sid not in candidate.symbols:
                    raise WorkspaceError("SYMBOL_NOT_FOUND", "Unknown symbol identity")
                touched.setdefault(sid, candidate.symbols[sid].name)
                self._move_function(candidate, sid, operation.get("before_symbol_id"))
            elif kind == "declare_shared_numeric_array":
                shared_id = self._declare_shared_array_tokens(
                    candidate, operation.get("name"), operation.get("upper_bound"))
                touched[shared_id] = candidate.symbols[shared_id].name
            elif kind in ("create_numeric_function", "create_string_function"):
                self._create_function_tokens(candidate, operation.get("name"), operation.get("parameters", []))
                self._index(candidate)
                self._populate_constructed_function(candidate, operation)
            elif kind == "edit_assignment_expression":
                statement_id = operation.get("statement_id")
                if statement_id not in candidate.statements:
                    raise WorkspaceError("STATEMENT_NOT_FOUND", "Unknown assignment statement identity")
                generated, expected_refs = self._edit_expression_tokens(
                    candidate, statement_id, operation.get("expression"))
                touched_statements.add(statement_id)
                self._index(candidate)
                self._verify_expression_bindings(candidate, generated, expected_refs)
                continue
            elif kind == "edit_numeric_literal_at_path":
                statement_id = self._edit_numeric_literal_at_path(candidate, operation)
                if statement_id is not None:
                    touched_statements.add(statement_id)
            elif kind == "insert_numeric_assignment":
                expression_tokens, expected_refs, target_token = self._insert_assignment_tokens(
                    candidate, operation.get("function_id"), operation.get("target"),
                    operation.get("expression"), operation.get("before_statement_id"))
                self._index(candidate)
                self._verify_expression_bindings(candidate, expression_tokens, expected_refs)
                function_id = operation["function_id"]
                target_id = candidate.token_symbol.get(target_token.uid)
                target_symbol = candidate.symbols.get(target_id) if target_id else None
                target_spec = operation["target"]
                if target_spec["kind"] == "result":
                    if target_id != function_id:
                        raise WorkspaceError("BINDING_MISMATCH", "Function-result target resolved to a different symbol")
                elif (target_symbol is None or target_symbol.kind != "variable"
                      or target_symbol.scope_id != self._function_row(candidate, function_id)["scope_id"]):
                    raise WorkspaceError("BINDING_MISMATCH", "Local assignment target did not resolve in the requested function scope")
                if not any(row["anchor_token_id"] == target_token.uid for row in candidate.statements.values()):
                    raise WorkspaceError("STATEMENT_CREATION_FAILED", "Inserted assignment did not receive a statement identity")
                continue
            elif kind == "insert_typed_if_block":
                function_id = operation.get("function_id")
                if not isinstance(function_id, str) or function_id not in candidate.symbols:
                    raise WorkspaceError("FUNCTION_NOT_FOUND", "Typed IF insertion requires a known function identity")
                self._insert_typed_if_block_tokens(candidate, function_id,
                    operation.get("before_statement_id"), operation.get("statement"))
                self._index(candidate)
                continue
            else:
                raise WorkspaceError("UNSUPPORTED_OPERATION", f"Unsupported semantic operation: {kind}")
            self._index(candidate)
        errors = [x for x in candidate.diagnostics if x.severity == "error" or x.code in ("DUPLICATE_LINE", "UNRESOLVED_LINE")]
        if errors:
            raise WorkspaceError("VALIDATION_FAILED", "Transaction would introduce invalid semantics", [self._diag_json(x) for x in errors])
        candidate.revision = current.revision + 1
        if any(operation.get("operation") in ("create_numeric_function", "create_string_function",
                                                "edit_assignment_expression",
                                                "edit_numeric_literal_at_path",
                                                "insert_numeric_assignment", "insert_typed_if_block")
               for operation in operations):
            from .projection import build_projection_from_document
            build_projection_from_document(self, candidate, candidate.revision)
        elif any(operation.get("operation") == "declare_shared_numeric_array" for operation in operations) and candidate.functions:
            from .projection import build_projection_from_document
            build_projection_from_document(self, candidate, candidate.revision)
        created_entities = [self._symbol_json(symbol) for sid, symbol in candidate.symbols.items()
                            if sid not in current.symbols]
        created_statements = [self._statement_json(row) for sid, row in candidate.statements.items()
                              if sid not in current.statements]
        affected = []
        for sid, before in touched.items():
            after = candidate.symbols.get(sid)
            if after:
                affected.append({"symbol_id": sid, "kind": after.kind, "before": before,
                                 "after": after.name, "reference_count": len(after.references)})
        old_diags = {(x.code, x.message, x.severity) for x in current.diagnostics}
        new_diags = [self._diag_json(x) for x in candidate.diagnostics
                     if (x.code, x.message, x.severity) not in old_diags]
        preview = {"valid": True, "document_id": document_id,
                   "base_revision": current.revision,
                   "expected_result_revision": candidate.revision,
                   "affected_entities": affected,
                   "diagnostics": {"error_count": 0,
                                   "warning_count": sum(x.severity == "warning" for x in candidate.diagnostics),
                                   "new": new_diags},
                   "created_entity_summary": {"symbols": len(created_entities),
                                              "statements": len(created_statements)},
                   "affected_statement_ids": sorted(touched_statements),
                   "_created_entities": created_entities,
                   "_created_statements": created_statements}
        if include_diff:
            diff = "".join(difflib.unified_diff(
                current.render().splitlines(keepends=True), candidate.render().splitlines(keepends=True),
                fromfile="workspace-before", tofile="workspace-after"))
            preview["diff"] = diff[:4000]
            preview["diff_truncated"] = len(diff) > 4000
        return candidate, preview

    def preview_transaction(self, document_id: str, expected_revision: int,
                            operations: list[dict[str, Any]], include_diff: bool = False) -> dict[str, Any]:
        _, preview = self._prepare_transaction(document_id, expected_revision, operations, include_diff)
        preview.pop("_created_entities", None)
        preview.pop("_created_statements", None)
        return preview

    def preview_transaction_semantics(self, document_id: str, expected_revision: int,
                                      operations: list[dict[str, Any]]) -> dict[str, Any]:
        """Return a typed candidate projection without mutating the live document.

        This is intentionally a narrow inspection API for controlled policy
        gateways. It uses the same private candidate validation as ordinary
        preview/commit and does not expose or install the candidate Document.
        """
        candidate, preview = self._prepare_transaction(document_id, expected_revision, operations)
        from .projection import build_projection_from_document, projection_semantics
        projection = build_projection_from_document(self, candidate, candidate.revision)
        preview.pop("_created_entities", None)
        preview.pop("_created_statements", None)
        return {"preview": preview, "candidate_semantics": projection_semantics(projection)}

    def apply_transaction(self, document_id: str, expected_revision: int,
                          operations: list[dict[str, Any]]) -> dict[str, Any]:
        candidate, preview = self._prepare_transaction(document_id, expected_revision, operations)
        self.documents[document_id] = candidate
        created_entities = preview.pop("_created_entities", [])
        created_statements = preview.pop("_created_statements", [])
        self._discovered_symbols.setdefault(document_id, set()).update(
            entity["symbol_id"] for entity in created_entities)
        self._discovered_statements.setdefault(document_id, set()).update(
            row["statement_id"] for row in created_statements)
        return {"committed": True, "revision": candidate.revision,
                "affected_entities": preview["affected_entities"],
                "diagnostics": preview["diagnostics"],
                "created_entities": created_entities,
                "created_statements": created_statements,
                "affected_statement_ids": preview["affected_statement_ids"]}

    def rename_symbol(self, document_id: str, symbol_id: str, new_name: str,
                      expected_revision: int) -> dict[str, Any]:
        return self._transaction(document_id, expected_revision,
                                 {"operation": "rename_symbol", "symbol_id": symbol_id,
                                  "new_name": new_name})

    def renumber_line(self, document_id: str, old_line: int, new_line: int,
                      expected_revision: int) -> dict[str, Any]:
        return self._transaction(document_id, expected_revision,
                                 {"operation": "renumber_line", "old_line": old_line,
                                  "new_line": new_line})

    def move_function(self, document_id: str, symbol_id: str,
                      before_symbol_id: str | None, expected_revision: int) -> dict[str, Any]:
        return self._transaction(document_id, expected_revision,
                                 {"operation": "move_function", "symbol_id": symbol_id,
                                  "before_symbol_id": before_symbol_id})

    def create_numeric_function(self, document_id: str, name: str, parameters: list[str],
                                expected_revision: int, expression: Any = None,
                                locals: list[dict[str, Any]] | None = None,
                                arrays: list[dict[str, Any]] | None = None,
                                array_assignments: list[dict[str, Any]] | None = None,
                                body: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        operation = {"operation": "create_numeric_function", "name": name,
                     "parameters": parameters}
        if expression is not None:
            operation["expression"] = expression
        if locals is not None:
            operation["locals"] = locals
        if arrays is not None:
            operation["arrays"] = arrays
        if array_assignments is not None:
            operation["array_assignments"] = array_assignments
        if body is not None:
            operation["body"] = body
        return self._transaction(document_id, expected_revision,
                                 operation)

    def declare_shared_numeric_array(self, document_id: str, name: str,
                                     upper_bound: int, expected_revision: int) -> dict[str, Any]:
        return self._transaction(document_id, expected_revision,
                                 {"operation": "declare_shared_numeric_array",
                                  "name": name, "upper_bound": upper_bound})

    def create_string_function(self, document_id: str, name: str, parameters: list[str],
                               expected_revision: int, expression: Any = None,
                               locals: list[dict[str, Any]] | None = None,
                               arrays: list[dict[str, Any]] | None = None,
                               array_assignments: list[dict[str, Any]] | None = None,
                               body: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        if not isinstance(name, str) or not name.endswith("$"):
            raise WorkspaceError("INVALID_NAME", "String function names must end in '$'")
        operation = {"operation": "create_string_function", "name": name,
                     "parameters": parameters}
        if expression is not None: operation["expression"] = expression
        if locals is not None: operation["locals"] = locals
        if arrays is not None: operation["arrays"] = arrays
        if array_assignments is not None: operation["array_assignments"] = array_assignments
        if body is not None: operation["body"] = body
        return self._transaction(document_id, expected_revision, operation)

    def edit_assignment_expression(self, document_id: str, statement_id: str,
                                   expression: Any, expected_revision: int) -> dict[str, Any]:
        return self._transaction(document_id, expected_revision,
                                 {"operation": "edit_assignment_expression",
                                  "statement_id": statement_id, "expression": expression})

    def insert_numeric_assignment(self, document_id: str, function_id: str,
                                   target: dict[str, Any], expression: Any,
                                   expected_revision: int,
                                   before_statement_id: str | None = None) -> dict[str, Any]:
        operation = {"operation": "insert_numeric_assignment", "function_id": function_id,
                     "target": target, "expression": expression}
        if before_statement_id is not None:
            operation["before_statement_id"] = before_statement_id
        return self._transaction(document_id, expected_revision, operation)

    def insert_typed_if_block(self, document_id: str, function_id: str,
                              before_statement_id: str, statement: dict[str, Any],
                              expected_revision: int) -> dict[str, Any]:
        return self._transaction(document_id, expected_revision, {
            "operation": "insert_typed_if_block", "function_id": function_id,
            "before_statement_id": before_statement_id, "statement": statement})

    def _rename(self, d: Document, symbol_id: str, new_name: str) -> None:
        s = d.symbols.get(symbol_id)
        if not s:
            raise WorkspaceError("SYMBOL_NOT_FOUND", "Unknown symbol identity")
        if s.kind == "line_label":
            raise WorkspaceError("UNSUPPORTED_RENAME", "Use renumber_line for BASIC line labels")
        if not IDENT_RE.fullmatch(new_name) or new_name.upper() in KEYWORDS:
            raise WorkspaceError("INVALID_NAME", "New name must be a BASIC identifier and not a keyword")
        old_suffix = s.name[-1] if s.name.endswith(("$", "%", "!", "#")) else ""
        new_suffix = new_name[-1] if new_name.endswith(("$", "%", "!", "#")) else ""
        if old_suffix != new_suffix:
            raise WorkspaceError("TYPE_SUFFIX_MISMATCH", "Rename must preserve the BASIC type suffix")
        norm = new_name.casefold()
        if norm == s.normalized:
            return
        collision = next((x for x in d.symbols.values() if x.id != s.id and x.scope_id == s.scope_id and x.normalized == norm), None)
        if collision:
            raise WorkspaceError("NAME_COLLISION", f"{new_name} collides with {collision.name} in the same scope")
        target_uids = {s.declaration_token, *s.references}
        tokens = {t.uid: t for t in d.tokens}
        for uid in target_uids:
            tokens[uid].text = new_name
        # Recompute token columns after a length-changing semantic rename.
        self._recolumn(d)

    def _renumber(self, d: Document, old: int, new: int) -> None:
        if new < 0 or new > 65529:
            raise WorkspaceError("INVALID_LINE", "BASIC line labels must be from 0 through 65529")
        if old not in d.labels:
            raise WorkspaceError("LINE_NOT_FOUND", f"BASIC line {old} does not exist")
        if new != old and new in d.labels:
            raise WorkspaceError("DUPLICATE_LINE", f"BASIC line {new} already exists")
        label_uid = d.labels[old]
        for t in d.tokens:
            if t.uid == label_uid or d.line_refs.get(t.uid) == old:
                t.text = str(new)
        self._recolumn(d)

    def _move_function(self, d: Document, symbol_id: str, before_symbol_id: str | None) -> None:
        func = next((f for f in d.functions if f["symbol_id"] == symbol_id), None)
        if not func or func["end_statement"] is None:
            raise WorkspaceError("MOVE_UNSUPPORTED", "Only complete FUNCTION/SUB blocks can be moved")
        if before_symbol_id == symbol_id:
            return
        target = next((f for f in d.functions if f["symbol_id"] == before_symbol_id), None) if before_symbol_id else None
        if before_symbol_id and not target:
            raise WorkspaceError("SYMBOL_NOT_FOUND", "Move destination function is unknown")
        # Function blocks are moved as complete physical-line spans. Refuse a
        # header/end embedded in colon-separated statements because extracting
        # that safely would require a more complete grammar.
        start_line, end_line = func["start_line"], func["end_line"]
        for line_no in (start_line, end_line):
            toks = [t for t in d.tokens if t.line == line_no and t.kind not in ("WS", "NEWLINE", "COMMENT")]
            if len(toks) < 2 or (line_no == start_line and toks[0].text.upper() not in ("FUNCTION", "SUB") and not (len(toks) > 1 and toks[1].text.upper() in ("FUNCTION", "SUB"))):
                raise WorkspaceError("MOVE_UNSUPPORTED", "Function header/end must occupy a complete physical line")
        block = [t for t in d.tokens if start_line <= t.line <= end_line]
        if target:
            dest_line = target["start_line"]
            if start_line <= dest_line <= end_line:
                raise WorkspaceError("MOVE_UNSUPPORTED", "Destination lies inside the selected function")
        else:
            dest_line = None
        block_ids = {t.uid for t in block}
        rest = [t for t in d.tokens if t.uid not in block_ids]
        if dest_line is not None:
            first_uid = next((t.uid for t in d.tokens if t.line == dest_line), None)
            insert_at = next((i for i, t in enumerate(rest) if t.uid == first_uid), None)
            if insert_at is None:
                raise WorkspaceError("MOVE_UNSUPPORTED", "Could not locate destination")
        else:
            insert_at = len(rest)
        d.tokens = rest[:insert_at] + block + rest[insert_at:]
        self._recolumn(d)

    def _statement_token_ranges(self, d: Document) -> list[list[str]]:
        result: list[list[str]] = []
        by_line: dict[int, list[Token]] = {}
        for t in d.tokens:
            by_line.setdefault(t.line, []).append(t)
        for toks in by_line.values():
            cur: list[str] = []
            for t in toks:
                cur.append(t.uid)
                if t.text == ":" and t.kind == "PUNCT":
                    result.append(cur)
                    cur = []
            if cur:
                result.append(cur)
        return result

    @staticmethod
    def _recolumn(d: Document) -> None:
        line = col = 1
        for t in d.tokens:
            t.line, t.column = line, col - 1
            breaks = t.text.count("\n") + t.text.count("\r") - t.text.count("\r\n")
            if breaks:
                line += breaks
                last_break = max(t.text.rfind("\n"), t.text.rfind("\r"))
                col = len(t.text) - last_break
            else:
                col += len(t.text)


    def protocol_call(self, method: str, params: dict[str, Any]) -> Any:
        methods = {
            "create_workspace": lambda: self.create_workspace(),
            "create_empty_document": lambda: self.create_empty_document(params.get("uri")),
            "open_document_from_string": lambda: self.open_document_from_string(params["text"], params.get("uri")),
            "replace_document_from_string": lambda: self.replace_document_from_string(params["document_id"], params["text"], params["expected_revision"]),
            "list_documents": self.list_documents,
            "get_document_structure": lambda: self.get_document_structure(params["document_id"]),
            "get_document_structure_page": lambda: self.get_document_structure_page(params["document_id"], params.get("offset", 0), params.get("limit", 50)),
            "list_function_statements": lambda: self.list_function_statements(params["document_id"], params["function_id"], params.get("offset", 0), params.get("limit", 50)),
            "list_symbols": lambda: self.list_symbols(params["document_id"]),
            "list_symbols_page": lambda: self.list_symbols_page(params["document_id"], params.get("offset", 0), params.get("limit", 50), params.get("kind"), params.get("name_query"), params.get("scope_id"), params.get("exact_name"), params.get("unique", False)),
            "find_definition": lambda: self.find_definition(params["document_id"], params["symbol_id"]),
            "find_references": lambda: self.find_references(params["document_id"], params["symbol_id"]),
            "find_references_page": lambda: self.find_references_page(params["document_id"], params["symbol_id"], params.get("offset", 0), params.get("limit", 100)),
            "rename_symbol": lambda: self.rename_symbol(params["document_id"], params["symbol_id"], params["new_name"], params["expected_revision"]),
            "apply_transaction": lambda: self.apply_transaction(params["document_id"], params["expected_revision"], params["operations"]),
            "preview_transaction": lambda: self.preview_transaction(params["document_id"], params["expected_revision"], params["operations"], params.get("include_diff", False)),
            "preview_transaction_semantics": lambda: self.preview_transaction_semantics(params["document_id"], params["expected_revision"], params["operations"]),
            "renumber_line": lambda: self.renumber_line(params["document_id"], params["old_line"], params["new_line"], params["expected_revision"]),
            "move_function": lambda: self.move_function(params["document_id"], params["symbol_id"], params.get("before_symbol_id"), params["expected_revision"]),
            "create_numeric_function": lambda: self.create_numeric_function(
                params["document_id"], params["name"], params.get("parameters", []),
                params["expected_revision"], params.get("expression"), params.get("locals"),
                params.get("arrays"), params.get("array_assignments"), params.get("body")),
            "create_string_function": lambda: self.create_string_function(
                params["document_id"], params["name"], params.get("parameters", []),
                params["expected_revision"], params.get("expression"), params.get("locals"),
                params.get("arrays"), params.get("array_assignments"), params.get("body")),
            "declare_shared_numeric_array": lambda: self.declare_shared_numeric_array(
                params["document_id"], params["name"], params["upper_bound"], params["expected_revision"]),
            "edit_assignment_expression": lambda: self.edit_assignment_expression(params["document_id"], params["statement_id"], params["expression"], params["expected_revision"]),
            "insert_numeric_assignment": lambda: self.insert_numeric_assignment(params["document_id"], params["function_id"], params["target"], params["expression"], params["expected_revision"], params.get("before_statement_id")),
            "insert_typed_if_block": lambda: self.insert_typed_if_block(params["document_id"], params["function_id"], params["before_statement_id"], params["statement"], params["expected_revision"]),
            "render_document": lambda: self.render_document(params["document_id"]),
            "get_diagnostics": lambda: self.get_diagnostics(params["document_id"]),
            "get_revision": lambda: self.get_revision(params["document_id"]),
        }
        if method not in methods:
            raise WorkspaceError("METHOD_NOT_FOUND", f"Unknown method {method}")
        return methods[method]()
