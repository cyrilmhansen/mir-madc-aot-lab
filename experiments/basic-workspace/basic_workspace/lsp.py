"""Optional, thin LSP facade over the canonical in-memory Workspace model."""
from __future__ import annotations

import json
import sys
from typing import Any

from .model import Workspace, WorkspaceError


class Facade:
    def __init__(self) -> None:
        self.workspace = Workspace()
        self.by_uri: dict[str, str] = {}
        self.versions: dict[str, int] = {}
        self.pending_edits: dict[str, dict[str, Any]] = {}

    def docid(self, uri: str) -> str:
        if uri not in self.by_uri:
            raise WorkspaceError("DOCUMENT_NOT_FOUND", f"Document is not open: {uri}")
        return self.by_uri[uri]

    def _line_text(self, uri: str, line: int) -> str:
        d = self.workspace._doc(self.docid(uri))
        lines = d.render().splitlines(keepends=True)
        if line < 0 or line >= len(lines):
            raise WorkspaceError("INVALID_POSITION", "LSP line is outside the document")
        return lines[line].rstrip("\r\n")

    @staticmethod
    def _utf16_to_codepoint(text: str, units: int) -> int:
        if units < 0:
            raise WorkspaceError("INVALID_POSITION", "LSP character offset cannot be negative")
        used = 0
        for index, char in enumerate(text):
            width = len(char.encode("utf-16-le")) // 2
            if units == used:
                return index
            if used < units < used + width:
                raise WorkspaceError("INVALID_POSITION", "LSP position splits a UTF-16 surrogate pair")
            used += width
        if units == used:
            return len(text)
        raise WorkspaceError("INVALID_POSITION", "LSP character is outside the line")

    @staticmethod
    def _codepoint_to_utf16(text: str, column: int) -> int:
        if column < 0 or column > len(text):
            raise WorkspaceError("INVALID_POSITION", "Workspace column is outside the line")
        return len(text[:column].encode("utf-16-le")) // 2

    def _lsp_character(self, uri: str, line: int, codepoint_column: int) -> int:
        return self._codepoint_to_utf16(self._line_text(uri, line - 1), codepoint_column)

    def token_at(self, uri: str, position: dict[str, int]):
        d = self.workspace._doc(self.docid(uri))
        line = int(position["line"]) + 1
        char = self._utf16_to_codepoint(self._line_text(uri, int(position["line"])), int(position["character"]))
        for t in d.tokens:
            if t.kind in ("IDENT", "NUMBER") and t.line == line and t.column <= char < t.column + len(t.text):
                sid = d.token_symbol.get(t.uid)
                if sid:
                    return d, d.symbols[sid], t
        return d, None, None

    def loc(self, uri: str, line: int, column: int, end: int) -> dict[str, Any]:
        return {"uri": uri, "range": {"start": {"line": line - 1, "character": self._lsp_character(uri, line, column)},
                                        "end": {"line": line - 1, "character": self._lsp_character(uri, line, end)}}}

    def request(self, method: str, p: dict[str, Any]) -> Any:
        if method == "initialize":
            return {"capabilities": {"positionEncoding": "utf-16", "textDocumentSync": 1,
                    "documentSymbolProvider": True, "definitionProvider": True,
                    "referencesProvider": True, "renameProvider": {"prepareProvider": True}},
                    "serverInfo": {"name": "basic-workspace", "version": "0.1"}}
        if method == "initialized" or method == "exit":
            return None
        if method == "textDocument/didOpen":
            td = p["textDocument"]
            uri = td["uri"]
            text = td["text"]
            if uri in self.by_uri:
                did = self.by_uri[uri]
                rev = self.workspace.get_revision(did)
                self.workspace.replace_document_from_string(did, text, rev)
            else:
                opened = self.workspace.open_document_from_string(text, uri)
                did = opened["document_id"]
                self.by_uri[uri] = did
            self.versions[uri] = int(td.get("version", 0))
            return None
        if method == "textDocument/didChange":
            td = p["textDocument"]
            uri = td["uri"]
            version = int(td["version"])
            if version <= self.versions.get(uri, -1):
                raise WorkspaceError("STALE_DOCUMENT_VERSION", "didChange version must increase monotonically")
            changes = p.get("contentChanges", [])
            if not changes or "range" in changes[-1]:
                raise WorkspaceError("LSP_CHANGE_UNSUPPORTED", "Only full-document didChange updates are supported")
            did = self.docid(uri)
            pending = self.pending_edits.get(uri)
            current_revision = self.workspace.get_revision(did)
            if pending and current_revision != pending["revision"]:
                raise WorkspaceError("STALE_PREVIEW", "Workspace changed after LSP rename proposal; rediscover and retry")
            incoming_text = changes[-1]["text"]
            if pending and incoming_text != pending["expected_text"]:
                raise WorkspaceError("LSP_EDIT_MISMATCH", "Synchronized document does not match the proposed WorkspaceEdit")
            self.workspace.replace_document_from_string(did, incoming_text,
                                                        pending["revision"] if pending else current_revision)
            self.versions[uri] = version
            self.pending_edits.pop(uri, None)
            return None
        if method == "textDocument/didClose":
            uri = p["textDocument"]["uri"]
            did = self.by_uri.pop(uri, None)
            self.versions.pop(uri, None)
            self.pending_edits.pop(uri, None)
            if did:
                self.workspace.documents.pop(did, None)
            return None
        td = p.get("textDocument", {})
        uri = td.get("uri")
        if method == "textDocument/documentSymbol":
            did = self.docid(uri)
            d = self.workspace._doc(did)
            result = []
            for f in d.functions:
                start = f["start_line"] - 1
                end = (f["end_line"] or f["start_line"]) - 1
                symbol = d.symbols.get(f["symbol_id"])
                name_token = next((t for t in d.tokens if symbol and t.uid == symbol.declaration_token), None)
                name_start = name_token.column if name_token else 0
                end_tokens = [t for t in d.tokens if t.line == (f["end_line"] or f["start_line"])]
                end_column = max((t.column + len(t.text) for t in end_tokens), default=0)
                end_column = min(end_column, len(self._line_text(uri, end)))
                result.append({"name": f["name"], "kind": 12 if f["kind"] == "function" else 12,
                               "range": {"start": {"line": start, "character": 0},
                                         "end": {"line": end, "character": self._lsp_character(uri, end + 1, end_column)}},
                               "selectionRange": {"start": {"line": name_token.line - 1 if name_token else start, "character": self._lsp_character(uri, name_token.line if name_token else start + 1, name_start)},
                                                  "end": {"line": name_token.line - 1 if name_token else start, "character": self._lsp_character(uri, name_token.line if name_token else start + 1, name_start + len(f["name"]))}}})
            function_ids = {f["symbol_id"] for f in d.functions}
            kind_map = {"line_label": 13, "variable": 13, "parameter": 13}
            for symbol in d.symbols.values():
                if symbol.id in function_ids:
                    continue
                token = next((t for t in d.tokens if t.uid == symbol.declaration_token), None)
                if token is None:
                    continue
                result.append({"name": symbol.name, "kind": kind_map.get(symbol.kind, 13),
                               "detail": f"{symbol.kind} in {symbol.scope_id}",
                               "range": {"start": {"line": token.line - 1, "character": self._lsp_character(uri, token.line, token.column)},
                                         "end": {"line": token.line - 1, "character": self._lsp_character(uri, token.line, token.column + len(token.text))}},
                               "selectionRange": {"start": {"line": token.line - 1, "character": self._lsp_character(uri, token.line, token.column)},
                                                  "end": {"line": token.line - 1, "character": self._lsp_character(uri, token.line, token.column + len(token.text))}}})
            return result
        if method in ("textDocument/definition", "textDocument/references",
                      "textDocument/prepareRename", "textDocument/rename"):
            d, sym, selected_token = self.token_at(uri, p["position"])
            if not sym:
                return None if method in ("textDocument/definition", "textDocument/prepareRename") else []
            refs = self.workspace.find_references(d.id, sym.id)
            decl = next(x for x in refs if x["is_definition"])
            if method == "textDocument/definition":
                return self.loc(uri, decl["line"], decl["column"], decl["end_column"])
            if method == "textDocument/prepareRename":
                return {"range": {"start": {"line": selected_token.line - 1, "character": self._lsp_character(uri, selected_token.line, selected_token.column)},
                                   "end": {"line": selected_token.line - 1, "character": self._lsp_character(uri, selected_token.line, selected_token.column + len(selected_token.text))}},
                        "placeholder": sym.name}
            if method == "textDocument/references":
                include = p.get("context", {}).get("includeDeclaration", True)
                return [self.loc(uri, r["line"], r["column"], r["end_column"])
                        for r in refs if include or not r["is_definition"]]
            new_name = p["newName"]
            if uri in self.pending_edits:
                raise WorkspaceError("LSP_PENDING_EDIT", "Synchronize or abandon the previous proposed edit first")
            edits = [{"range": {"start": {"line": r["line"] - 1, "character": r["column"]},
                                "end": {"line": r["line"] - 1, "character": r["end_column"]}},
                      "newText": new_name} for r in refs]
            for edit, ref in zip(edits, refs):
                edit["range"]["start"]["character"] = self._lsp_character(uri, ref["line"], ref["column"])
                edit["range"]["end"]["character"] = self._lsp_character(uri, ref["line"], ref["end_column"])
            if sym.kind == "line_label":
                if not new_name.isdigit():
                    raise WorkspaceError("INVALID_LINE", "A BASIC line label can only be renamed to an integer")
                operation = {"operation": "renumber_line", "old_line": int(sym.name), "new_line": int(new_name)}
            else:
                operation = {"operation": "rename_symbol", "symbol_id": sym.id, "new_name": new_name}
            revision = self.workspace.get_revision(d.id)
            self.workspace.preview_transaction(d.id, revision, [operation])
            old_text = self.workspace.render_document(d.id)
            expected_text = self._apply_edits(old_text, uri, edits)
            self.pending_edits[uri] = {"revision": revision, "version": self.versions.get(uri, 0),
                                       "expected_text": expected_text}
            return {"documentChanges": [{"textDocument": {"uri": uri,
                                                               "version": self.versions.get(uri, 0)},
                                          "edits": edits}]}
        raise WorkspaceError("METHOD_NOT_FOUND", f"Unsupported LSP method {method}")

    def _apply_edits(self, text: str, uri: str, edits: list[dict[str, Any]]) -> str:
        lines = text.splitlines(keepends=True)
        starts, total = [], 0
        for line in lines:
            starts.append(total)
            total += len(line)
        def offset(position):
            line_no = position["line"]
            if line_no < 0 or line_no >= len(lines):
                raise WorkspaceError("INVALID_POSITION", "Edit line is outside the document")
            body = lines[line_no].rstrip("\r\n")
            cp = self._utf16_to_codepoint(body, position["character"])
            return starts[line_no] + cp
        changes = []
        for edit in edits:
            a, b = offset(edit["range"]["start"]), offset(edit["range"]["end"])
            changes.append((a, b, edit["newText"]))
        for a, b, value in sorted(changes, reverse=True):
            text = text[:a] + value + text[b:]
        return text


def read_message(stream) -> dict[str, Any] | None:
    headers: dict[str, str] = {}
    while True:
        line = stream.readline()
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            break
        key, _, value = line.decode("ascii").partition(":")
        headers[key.lower()] = value.strip()
    size = int(headers.get("content-length", "0"))
    if size <= 0:
        raise ValueError("Missing Content-Length")
    return json.loads(stream.read(size))


def write_message(value: dict[str, Any]) -> None:
    body = json.dumps(value, separators=(",", ":")).encode()
    sys.stdout.buffer.write(f"Content-Length: {len(body)}\r\n\r\n".encode() + body)
    sys.stdout.buffer.flush()


def serve() -> None:
    facade = Facade()
    while True:
        request = read_message(sys.stdin.buffer)
        if request is None:
            return
        method = request.get("method")
        try:
            result = facade.request(method, request.get("params") or {})
            if "id" in request:
                write_message({"jsonrpc": "2.0", "id": request["id"], "result": result})
        except WorkspaceError as exc:
            if "id" in request:
                write_message({"jsonrpc": "2.0", "id": request["id"],
                               "error": {"code": -32000, "message": exc.message, "data": exc.json()}})
            else:
                write_message({"jsonrpc": "2.0", "method": "window/logMessage",
                               "params": {"type": 1, "message": f"{exc.code}: {exc.message}"}})
        except Exception as exc:
            if "id" in request:
                write_message({"jsonrpc": "2.0", "id": request["id"],
                               "error": {"code": -32602, "message": str(exc)}})
            else:
                write_message({"jsonrpc": "2.0", "method": "window/logMessage",
                               "params": {"type": 1, "message": f"LSP_ERROR: {exc}"}})


if __name__ == "__main__":
    serve()
