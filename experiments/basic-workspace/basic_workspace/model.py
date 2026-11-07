"""Lossless BASIC token model and semantic editing API.

The token stream (including whitespace, comments and line endings) is canonical.
Statement, scope and symbol indexes are rebuilt views over that stream. Semantic
edits mutate token identities, then validate and rebuild indexes atomically.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import copy
import difflib
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
    lines: list[dict[str, Any]] = field(default_factory=list)
    functions: list[dict[str, Any]] = field(default_factory=list)
    _symbol_ids: dict[str, str] = field(default_factory=dict, repr=False)
    _scope_ids: dict[str, str] = field(default_factory=dict, repr=False)

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

    def create_workspace(self) -> dict[str, Any]:
        return {"workspace_id": "workspace-1", "documents": 0}

    def open_document_from_string(self, text: str, uri: str | None = None) -> dict[str, Any]:
        did = opaque("doc")
        doc = Document(did, uri or f"memory://{did}/program.bas", 1, lex(text))
        self.documents[did] = doc
        self._index(doc)
        return {"document_id": did, "uri": doc.uri, "revision": doc.revision,
                "diagnostics": [self._diag_json(d) for d in doc.diagnostics]}

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
        doc.symbols = {}
        doc.token_symbol = {}
        doc.labels = {}
        doc.label_tokens = {}
        doc.line_refs = {}
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

        # Resolve implicit variables per function/module scope. The declaration
        # identity is the first occurrence token; the dialect has no explicit
        # variable declaration requirement for this subset.
        var_symbols: dict[tuple[str, str], Symbol] = {}
        array_names: set[str] = set()
        for st in statements:
            sig = st["tokens"]
            if sig and sig[0].text.upper() == "DIM":
                for t in sig[1:]:
                    if t.kind == "IDENT" and t.text.upper() not in KEYWORDS:
                        array_names.add(t.text.casefold())
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
                    if (t.text.casefold() in array_names or any(x.text == "=" for x in sig[:i + 1])
                            or (i > 0 and sig[i - 1].text.upper() == "DIM")
                            or word in ("DIM", "FOR", "NEXT", "READ", "INPUT")):
                        pass
                    else:
                        doc.diagnostics.append(Diagnostic("AMBIGUOUS_CALL_OR_ARRAY", f"Cannot tell whether {t.text} is an implicit array or function call", "information", t.line, t.column))
                        continue
                key = (scope_id, t.text.casefold())
                sym = var_symbols.get(key)
                if sym is None:
                    skey = f"implicit:{scope_id}:{t.uid}"
                    sid = previous_ids.get(skey) or opaque("sym")
                    sym = Symbol(sid, "variable", t.text, t.text.casefold(), scope_id, doc.id, t.uid, t.line, True)
                    var_symbols[key] = sym
                    doc.symbols[sid] = sym
                sym.references.append(t.uid)
                doc.token_symbol[t.uid] = sym.id

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
            elif sym.kind == "line_label":
                doc._symbol_ids[f"line_label:{sym.declaration_token}"] = sym.id

    @staticmethod
    def _diag_json(d: Diagnostic) -> dict[str, Any]:
        return {"code": d.code, "message": d.message, "severity": d.severity,
                "line": d.line, "column": d.column}

    def get_document_structure(self, document_id: str) -> dict[str, Any]:
        d = self._doc(document_id)
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
        return [self._symbol_json(s) for s in d.symbols.values()]

    def list_symbols_page(self, document_id: str, offset: int = 0, limit: int = 50,
                          kind: str | None = None, name_query: str | None = None,
                          scope_id: str | None = None) -> dict[str, Any]:
        if offset < 0 or limit < 1 or limit > 200:
            raise WorkspaceError("INVALID_PAGE", "Use offset >= 0 and limit from 1 to 200")
        rows = [self._symbol_json(s) for s in self._doc(document_id).symbols.values()
                if (kind is None or s.kind == kind)
                and (name_query is None or name_query.casefold() in s.name.casefold())
                and (scope_id is None or s.scope_id == scope_id)]
        return {"items": rows[offset:offset + limit], "total": len(rows),
                "offset": offset, "limit": limit, "truncated": offset + limit < len(rows)}

    @staticmethod
    def _symbol_json(s: Symbol) -> dict[str, Any]:
        return {"symbol_id": s.id, "kind": s.kind, "name": s.name,
                "scope_id": s.scope_id, "document_id": s.document_id,
                "declaration_token_id": s.declaration_token, "line": s.line,
                "implicit": s.implicit, "reference_count": len(s.references)}

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

    def _prepare_transaction(self, document_id: str, expected_revision: int,
                             operations: list[dict[str, Any]], include_diff: bool = False) -> tuple[Document, dict[str, Any]]:
        current = self._doc(document_id)
        if current.revision != expected_revision:
            raise WorkspaceError("STALE_REVISION", f"Expected revision {expected_revision}, current revision is {current.revision}", {"current_revision": current.revision})
        if not operations:
            raise WorkspaceError("EMPTY_TRANSACTION", "A semantic transaction needs at least one operation")
        candidate = copy.deepcopy(current)
        touched: dict[str, str] = {}
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
            else:
                raise WorkspaceError("UNSUPPORTED_OPERATION", f"Unsupported semantic operation: {kind}")
            self._index(candidate)
        errors = [x for x in candidate.diagnostics if x.severity == "error" or x.code in ("DUPLICATE_LINE", "UNRESOLVED_LINE")]
        if errors:
            raise WorkspaceError("VALIDATION_FAILED", "Transaction would introduce invalid semantics", [self._diag_json(x) for x in errors])
        candidate.revision = current.revision + 1
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
                                   "new": new_diags}}
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
        return preview

    def apply_transaction(self, document_id: str, expected_revision: int,
                          operations: list[dict[str, Any]]) -> dict[str, Any]:
        candidate, preview = self._prepare_transaction(document_id, expected_revision, operations)
        self.documents[document_id] = candidate
        return {"committed": True, "revision": candidate.revision,
                "affected_entities": preview["affected_entities"],
                "diagnostics": preview["diagnostics"]}

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
            "open_document_from_string": lambda: self.open_document_from_string(params["text"], params.get("uri")),
            "replace_document_from_string": lambda: self.replace_document_from_string(params["document_id"], params["text"], params["expected_revision"]),
            "list_documents": self.list_documents,
            "get_document_structure": lambda: self.get_document_structure(params["document_id"]),
            "get_document_structure_page": lambda: self.get_document_structure_page(params["document_id"], params.get("offset", 0), params.get("limit", 50)),
            "list_symbols": lambda: self.list_symbols(params["document_id"]),
            "list_symbols_page": lambda: self.list_symbols_page(params["document_id"], params.get("offset", 0), params.get("limit", 50), params.get("kind"), params.get("name_query"), params.get("scope_id")),
            "find_definition": lambda: self.find_definition(params["document_id"], params["symbol_id"]),
            "find_references": lambda: self.find_references(params["document_id"], params["symbol_id"]),
            "find_references_page": lambda: self.find_references_page(params["document_id"], params["symbol_id"], params.get("offset", 0), params.get("limit", 100)),
            "rename_symbol": lambda: self.rename_symbol(params["document_id"], params["symbol_id"], params["new_name"], params["expected_revision"]),
            "apply_transaction": lambda: self.apply_transaction(params["document_id"], params["expected_revision"], params["operations"]),
            "preview_transaction": lambda: self.preview_transaction(params["document_id"], params["expected_revision"], params["operations"], params.get("include_diff", False)),
            "renumber_line": lambda: self.renumber_line(params["document_id"], params["old_line"], params["new_line"], params["expected_revision"]),
            "move_function": lambda: self.move_function(params["document_id"], params["symbol_id"], params.get("before_symbol_id"), params["expected_revision"]),
            "render_document": lambda: self.render_document(params["document_id"]),
            "get_diagnostics": lambda: self.get_diagnostics(params["document_id"]),
            "get_revision": lambda: self.get_revision(params["document_id"]),
        }
        if method not in methods:
            raise WorkspaceError("METHOD_NOT_FOUND", f"Unknown method {method}")
        return methods[method]()
