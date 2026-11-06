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

    def docid(self, uri: str) -> str:
        if uri not in self.by_uri:
            raise WorkspaceError("DOCUMENT_NOT_FOUND", f"Document is not open: {uri}")
        return self.by_uri[uri]

    def token_at(self, uri: str, position: dict[str, int]):
        d = self.workspace._doc(self.docid(uri))
        line = int(position["line"]) + 1
        char = int(position["character"])
        for t in d.tokens:
            if t.kind in ("IDENT", "NUMBER") and t.line == line and t.column <= char < t.column + len(t.text):
                sid = d.token_symbol.get(t.uid)
                if sid:
                    return d, d.symbols[sid], t
        return d, None, None

    @staticmethod
    def loc(uri: str, line: int, column: int, end: int) -> dict[str, Any]:
        return {"uri": uri, "range": {"start": {"line": line - 1, "character": column},
                                        "end": {"line": line - 1, "character": end}}}

    def request(self, method: str, p: dict[str, Any]) -> Any:
        if method == "initialize":
            return {"capabilities": {"textDocumentSync": 1,
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
                return None
            changes = p.get("contentChanges", [])
            if not changes or "range" in changes[-1]:
                raise WorkspaceError("LSP_CHANGE_UNSUPPORTED", "Only full-document didChange updates are supported")
            did = self.docid(uri)
            self.workspace.replace_document_from_string(did, changes[-1]["text"], self.workspace.get_revision(did))
            self.versions[uri] = version
            return None
        if method == "textDocument/didClose":
            uri = p["textDocument"]["uri"]
            did = self.by_uri.pop(uri, None)
            self.versions.pop(uri, None)
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
                result.append({"name": f["name"], "kind": 12 if f["kind"] == "function" else 12,
                               "range": {"start": {"line": start, "character": 0},
                                         "end": {"line": end, "character": 0}},
                               "selectionRange": {"start": {"line": name_token.line - 1 if name_token else start, "character": name_start},
                                                  "end": {"line": name_token.line - 1 if name_token else start, "character": name_start + len(f["name"])}}})
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
                               "range": {"start": {"line": token.line - 1, "character": token.column},
                                         "end": {"line": token.line - 1, "character": token.column + len(token.text)}},
                               "selectionRange": {"start": {"line": token.line - 1, "character": token.column},
                                                  "end": {"line": token.line - 1, "character": token.column + len(token.text)}}})
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
                return {"range": {"start": {"line": selected_token.line - 1, "character": selected_token.column},
                                   "end": {"line": selected_token.line - 1, "character": selected_token.column + len(selected_token.text)}},
                        "placeholder": sym.name}
            if method == "textDocument/references":
                include = p.get("context", {}).get("includeDeclaration", True)
                return [self.loc(uri, r["line"], r["column"], r["end_column"])
                        for r in refs if include or not r["is_definition"]]
            new_name = p["newName"]
            edits = [{"range": {"start": {"line": r["line"] - 1, "character": r["column"]},
                                "end": {"line": r["line"] - 1, "character": r["end_column"]}},
                      "newText": new_name} for r in refs]
            if sym.kind == "line_label":
                if not new_name.isdigit():
                    raise WorkspaceError("INVALID_LINE", "A BASIC line label can only be renamed to an integer")
                self.workspace.renumber_line(d.id, int(sym.name), int(new_name), self.workspace.get_revision(d.id))
            else:
                self.workspace.rename_symbol(d.id, sym.id, new_name, self.workspace.get_revision(d.id))
            return {"changes": {uri: edits}}
        raise WorkspaceError("METHOD_NOT_FOUND", f"Unsupported LSP method {method}")


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
        except Exception as exc:
            if "id" in request:
                write_message({"jsonrpc": "2.0", "id": request["id"],
                               "error": {"code": -32602, "message": str(exc)}})


if __name__ == "__main__":
    serve()
