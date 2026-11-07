import pathlib
import json
import subprocess
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from basic_workspace import Workspace, WorkspaceError
from basic_workspace.lsp import Facade
from basic_workspace.client import AgentToolAdapter, RpcError, WorkspaceClient


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.ws = Workspace()

    def open(self, source):
        return self.ws.open_document_from_string(source)["document_id"]

    def symbol(self, did, kind, name, scope=None):
        return next(s for s in self.ws.list_symbols(did)
                    if s["kind"] == kind and s["name"].casefold() == name.casefold()
                    and (scope is None or s["scope_id"] == scope))

    def test_lossless_roundtrip_and_in_memory_only(self):
        source = "10  PRINT  \"Hi: there\" : REM note\r\n20 END\r\n"
        did = self.open(source)
        self.assertEqual(source, self.ws.render_document(did))
        self.assertEqual([10, 20], [x["line_label"] for x in self.ws.get_document_structure(did)["physical_lines"]])

    def test_parameter_rename_preserves_comments_literals_and_case(self):
        did = self.open('''10 FUNCTION TOTAL(SCORE)\n20 TOTAL = SCORE + 1\n30 PRINT "SCORE" ' score note\n40 END FUNCTION\n''')
        p = self.symbol(did, "parameter", "score")
        before_id = p["symbol_id"]
        self.ws.rename_symbol(did, before_id, "POINTS", 1)
        text = self.ws.render_document(did)
        self.assertIn("TOTAL(POINTS)", text)
        self.assertIn("TOTAL = POINTS + 1", text)
        self.assertIn('"SCORE"', text)
        self.assertIn("' score note", text)
        p2 = self.symbol(did, "parameter", "points")
        self.assertEqual(before_id, p2["symbol_id"])
        self.assertEqual(2, self.ws.get_revision(did))

    def test_complete_in_memory_edit_matches_expected_source(self):
        source = '''FUNCTION TOTAL(SCORE)
  TOTAL = SCORE + 1
END FUNCTION
10 GOTO 100
20 PRINT "SCORE is just text": GOTO 200
30 END
100 PRINT TOTAL(9)
200 END
'''
        expected = '''FUNCTION TOTAL(POINTS)
  TOTAL = POINTS + 1
END FUNCTION
10 GOTO 150
20 PRINT "SCORE is just text": GOTO 200
30 END
150 PRINT TOTAL(9)
200 END
'''
        did = self.open(source)
        param = self.symbol(did, "parameter", "SCORE")
        result = self.ws.apply_transaction(did, 1, [
            {"operation": "rename_symbol", "symbol_id": param["symbol_id"], "new_name": "POINTS"},
            {"operation": "renumber_line", "old_line": 100, "new_line": 150},
        ])
        self.assertEqual(2, result["revision"])
        self.assertEqual(expected, self.ws.render_document(did))

    def test_scope_isolation(self):
        did = self.open("""FUNCTION F(A)\nX=A\nEND FUNCTION\nFUNCTION G(A)\nX=A+1\nEND FUNCTION\n""")
        params = [x for x in self.ws.list_symbols(did) if x["kind"] == "parameter"]
        self.assertEqual(2, len(params))
        self.assertNotEqual(params[0]["scope_id"], params[1]["scope_id"])
        locals_ = [x for x in self.ws.list_symbols(did) if x["kind"] == "variable" and x["name"] == "X"]
        self.assertEqual(2, len(locals_))
        self.assertNotEqual(locals_[0]["symbol_id"], locals_[1]["symbol_id"])

    def test_rename_collision_is_atomic(self):
        did = self.open("FUNCTION F(A,B)\nF=A+B\nEND FUNCTION\n")
        a = self.symbol(did, "parameter", "A")
        before = self.ws.render_document(did)
        with self.assertRaises(WorkspaceError) as caught:
            self.ws.rename_symbol(did, a["symbol_id"], "B", 1)
        self.assertEqual("NAME_COLLISION", caught.exception.code)
        self.assertEqual(before, self.ws.render_document(did))
        self.assertEqual(1, self.ws.get_revision(did))

    def test_rename_must_preserve_basic_type_suffix(self):
        did = self.open("FUNCTION GREET$(NAME$)\nGREET$=NAME$\nEND FUNCTION\n")
        param = self.symbol(did, "parameter", "NAME$")
        with self.assertRaises(WorkspaceError) as caught:
            self.ws.rename_symbol(did, param["symbol_id"], "NAME", 1)
        self.assertEqual("TYPE_SUFFIX_MISMATCH", caught.exception.code)

    def test_renumber_targets_only_semantic_references(self):
        source = '''10 ON N GOTO 100,200\n20 GOSUB 100: PRINT 100\n30 DATA 100\n40 PRINT "100"\n100 RETURN\n200 GOTO 100\n'''
        did = self.open(source)
        self.ws.renumber_line(did, 100, 150, 1)
        got = self.ws.render_document(did)
        self.assertIn("10 ON N GOTO 150,200", got)
        self.assertIn("20 GOSUB 150: PRINT 100", got)
        self.assertIn("30 DATA 100", got)
        self.assertIn('40 PRINT "100"', got)
        self.assertIn("200 GOTO 150", got)
        self.assertIn("150 RETURN", got)

    def test_line_label_identity_and_reference_index_survive_renumber(self):
        did = self.open("10 GOTO 100\n100 END\n")
        label = next(s for s in self.ws.list_symbols(did) if s["kind"] == "line_label" and s["name"] == "100")
        self.assertEqual(1, label["reference_count"])
        self.ws.renumber_line(did, 100, 150, 1)
        label2 = next(s for s in self.ws.list_symbols(did) if s["kind"] == "line_label" and s["name"] == "150")
        self.assertEqual(label["symbol_id"], label2["symbol_id"])

    def test_duplicate_and_invalid_reference_transactions_rollback(self):
        did = self.open("10 GOTO 20\n20 END\n")
        before = self.ws.render_document(did)
        with self.assertRaises(WorkspaceError) as caught:
            self.ws.renumber_line(did, 20, 10, 1)
        self.assertIn(caught.exception.code, ("DUPLICATE_LINE", "VALIDATION_FAILED"))
        self.assertEqual(before, self.ws.render_document(did))
        with self.assertRaises(WorkspaceError) as missing:
            self.ws.renumber_line(did, 999, 30, 1)
        self.assertEqual("LINE_NOT_FOUND", missing.exception.code)
        self.assertEqual(before, self.ws.render_document(did))

    def test_stale_client_transaction_rejected(self):
        did = self.open("10 FUNCTION F(SCORE)\n20 F=SCORE\n30 END FUNCTION\n")
        param = self.symbol(did, "parameter", "SCORE")
        # Client A commits; client B submits a conflicting operation against its snapshot.
        self.ws.rename_symbol(did, param["symbol_id"], "POINTS", expected_revision=1)
        with self.assertRaises(WorkspaceError) as caught:
            self.ws.rename_symbol(did, param["symbol_id"], "VALUE", expected_revision=1)
        self.assertEqual("STALE_REVISION", caught.exception.code)
        self.assertIn("POINTS", self.ws.render_document(did))

    def test_multi_operation_transaction_is_atomic(self):
        did = self.open("10 FUNCTION F(X)\n20 F=X\n30 END FUNCTION\n40 GOTO 30\n")
        x = self.symbol(did, "parameter", "X")
        before = self.ws.render_document(did)
        with self.assertRaises(WorkspaceError):
            self.ws.apply_transaction(did, 1, [
                {"operation": "rename_symbol", "symbol_id": x["symbol_id"], "new_name": "VALUE"},
                {"operation": "renumber_line", "old_line": 999, "new_line": 500},
            ])
        self.assertEqual(before, self.ws.render_document(did))
        self.assertEqual(1, self.ws.get_revision(did))
        result = self.ws.apply_transaction(did, 1, [
            {"operation": "rename_symbol", "symbol_id": x["symbol_id"], "new_name": "VALUE"},
            {"operation": "renumber_line", "old_line": 30, "new_line": 35},
        ])
        self.assertEqual(2, result["revision"])
        self.assertIn("GOTO 35", self.ws.render_document(did))

    def test_preview_is_non_mutating_and_commit_revalidates_revision(self):
        did = self.open("FUNCTION F(SCORE)\nF=SCORE+1\nEND FUNCTION\n")
        param = self.symbol(did, "parameter", "SCORE")
        original = self.ws.render_document(did)
        operations = [{"operation": "rename_symbol", "symbol_id": param["symbol_id"], "new_name": "POINTS"}]
        preview = self.ws.preview_transaction(did, 1, operations, include_diff=True)
        self.assertEqual(2, preview["expected_result_revision"])
        self.assertEqual(1, len(preview["affected_entities"]))
        self.assertIn("POINTS", preview["diff"])
        self.assertEqual(1, self.ws.get_revision(did))
        self.assertEqual(original, self.ws.render_document(did))
        self.ws.rename_symbol(did, param["symbol_id"], "OTHER", 1)
        with self.assertRaises(WorkspaceError) as stale:
            self.ws.apply_transaction(did, preview["base_revision"], operations)
        self.assertEqual("STALE_REVISION", stale.exception.code)
        self.assertIn("OTHER", self.ws.render_document(did))

    def test_implicit_declarations_are_explicitly_marked(self):
        did = self.open("PRINT TOTAL\nEND\n")
        total = self.symbol(did, "variable", "total")
        self.assertTrue(total["implicit"])

    def test_def_fn_and_external_declarations_are_indexed(self):
        did = self.open("""10 DEF FNADD(A,B)=A+B
20 EXTERNAL FUNCTION EXT_ADD(X,Y)
30 PRINT FNADD(2,3): PRINT EXT_ADD(4,5)
""")
        symbols = self.ws.list_symbols(did)
        self.assertIn(("FNADD", "function"), {(x["name"], x["kind"]) for x in symbols})
        self.assertIn(("EXT_ADD", "external_function"), {(x["name"], x["kind"]) for x in symbols})
        fnparam = self.symbol(did, "parameter", "A")
        self.assertEqual(1, fnparam["reference_count"])
        self.assertEqual(1, self.symbol(did, "function", "FNADD")["reference_count"])

    def test_function_rename_updates_bound_calls(self):
        did = self.open("FUNCTION TOTAL(X)\nTOTAL=X+1\nEND FUNCTION\nPRINT total(2)\n")
        fn = self.symbol(did, "function", "TOTAL")
        self.assertEqual(2, fn["reference_count"])  # result assignment and call site
        self.ws.rename_symbol(did, fn["symbol_id"], "SUM_VALUE", 1)
        self.assertIn("FUNCTION SUM_VALUE(X)", self.ws.render_document(did))
        self.assertIn("SUM_VALUE=X+1", self.ws.render_document(did))
        self.assertIn("PRINT SUM_VALUE(2)", self.ws.render_document(did))

    def test_dim_array_use_is_not_guessed_as_a_function(self):
        did = self.open("DIM A(10)\nPRINT A(1)\nEND\n")
        self.assertNotIn("AMBIGUOUS_CALL_OR_ARRAY", {d["code"] for d in self.ws.get_diagnostics(did)})
        a = self.symbol(did, "array", "A")
        self.assertEqual(1, a["reference_count"])

    def test_json_rpc_stdio_roundtrip(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "create_workspace"},
            {"jsonrpc": "2.0", "id": 2, "method": "open_document_from_string",
             "params": {"text": "10 END\n"}},
        ]
        proc = subprocess.run([sys.executable, "-m", "basic_workspace.server"],
                              input="".join(json.dumps(x) + "\n" for x in requests),
                              text=True, capture_output=True, cwd=root, check=True)
        rows = [json.loads(row) for row in proc.stdout.splitlines()]
        self.assertEqual([1, 2], [row["id"] for row in rows])
        self.assertIn("result", rows[1])

    def test_agent_client_lifecycle_preview_commit_and_known_identity(self):
        with WorkspaceClient(timeout=3) as client:
            adapter = AgentToolAdapter(client)
            opened = adapter.call("workspace_open", {"text": "FUNCTION F(SCORE)\nF=SCORE+1\nEND FUNCTION\n"})
            symbols = adapter.call("workspace_symbols", {"kind": "parameter", "name_query": "score"})
            symbol = symbols["items"][0]
            refs = adapter.call("workspace_references", {"symbol_id": symbol["symbol_id"]})
            self.assertEqual(2, refs["total"])
            ops = [{"operation": "rename_symbol", "symbol_id": symbol["symbol_id"], "new_name": "POINTS"}]
            preview = adapter.call("workspace_preview", {"expected_revision": opened["revision"],
                                                           "operations": ops})
            self.assertTrue(preview["valid"])
            self.assertEqual(1, client.revision)
            committed = adapter.call("workspace_commit", {"expected_revision": opened["revision"],
                                                            "operations": ops})
            self.assertEqual(2, committed["revision"])
            self.assertIn("POINTS", adapter.call("workspace_render", {})["text"])
            self.assertEqual([], adapter.call("workspace_diagnostics", {}))
            with self.assertRaises(RpcError) as fabricated:
                adapter.call("workspace_preview", {"expected_revision": 2,
                    "operations": [{"operation": "rename_symbol", "symbol_id": "sym_fake", "new_name": "X"}]})
            self.assertEqual("UNKNOWN_SYMBOL_ID", fabricated.exception.code)
            self.assertGreater(client.metrics["request_bytes"], 0)
        self.assertIsNone(client.proc)

    def test_agent_client_timeout_is_structured_and_closes_subprocess(self):
        client = WorkspaceClient(timeout=0.000001)
        with self.assertRaises(RpcError) as timed_out:
            client.workspace_open("END\n")
        self.assertEqual("TIMEOUT", timed_out.exception.code)
        self.assertIsNone(client.proc)

    def test_agent_client_bounds_and_filters_discovery(self):
        with WorkspaceClient(timeout=3) as client:
            client.workspace_open("\n".join(f"PRINT V{i}" for i in range(80)))
            page = client.workspace_symbols(limit=5, name_query="V7")
            self.assertEqual(11, page["total"])
            self.assertEqual(5, len(page["items"]))
            structure = client.workspace_structure(limit=5)
            self.assertEqual(5, len(structure["physical_lines"]))
            self.assertTrue(structure["page"]["physical_line_total"] >= 80)
            self.assertTrue(client.workspace_render(max_chars=12)["truncated"])

    def test_agent_tool_requires_discovered_line_label(self):
        with WorkspaceClient(timeout=3) as client:
            agent = AgentToolAdapter(client)
            opened = agent.call("workspace_open", {"text": "10 GOTO 20\n20 END\n"})
            op = [{"operation": "renumber_line", "old_line": 20, "new_line": 30}]
            with self.assertRaises(RpcError) as missing:
                agent.call("workspace_preview", {"expected_revision": opened["revision"], "operations": op})
            self.assertEqual("UNKNOWN_LINE_LABEL", missing.exception.code)
            agent.call("workspace_symbols", {"kind": "line_label", "name_query": "20"})
            preview = agent.call("workspace_preview", {"expected_revision": opened["revision"], "operations": op})
            self.assertTrue(preview["valid"])

    def test_compact_unique_symbol_discovery_is_exact_and_ambiguity_safe(self):
        with WorkspaceClient(timeout=3) as client:
            client.workspace_open("FUNCTION A(X)\nA=X\nEND FUNCTION\nFUNCTION B(X)\nB=X\nEND FUNCTION\n")
            unique = client.workspace_symbols(kind="function", exact_name="A", unique=True)
            self.assertTrue(unique["unique"])
            self.assertEqual("A", unique["unique_symbol"]["name"])
            self.assertEqual([], unique["items"])
            self.assertIn("revision", unique)
            self.assertIn("diagnostic_summary", unique)
            ambiguous = client.workspace_symbols(kind="parameter", exact_name="X", unique=True)
            self.assertTrue(ambiguous["ambiguous"])
            self.assertIsNone(ambiguous["unique_symbol"])

    def test_two_agent_views_share_authoritative_process_and_reject_stale_commit(self):
        with WorkspaceClient(timeout=3) as client:
            agent_a = AgentToolAdapter(client)
            opened = agent_a.call("workspace_open", {"text": "FUNCTION F(SCORE)\nF=SCORE\nEND FUNCTION\n"})
            symbol = agent_a.call("workspace_symbols", {"kind": "parameter"})["items"][0]
            agent_b = agent_a.fork()
            old_revision = opened["revision"]
            op_a = [{"operation": "rename_symbol", "symbol_id": symbol["symbol_id"], "new_name": "POINTS"}]
            with self.assertRaises(RpcError) as undiscovered:
                agent_b.call("workspace_preview", {"expected_revision": old_revision, "operations": op_a})
            self.assertEqual("UNKNOWN_SYMBOL_ID", undiscovered.exception.code)
            symbol_b = agent_b.call("workspace_symbols", {"kind": "parameter", "name_query": "SCORE"})["items"][0]
            self.assertEqual(symbol["symbol_id"], symbol_b["symbol_id"])
            agent_a.call("workspace_commit", {"expected_revision": old_revision, "operations": op_a})
            op_b = [{"operation": "rename_symbol", "symbol_id": symbol["symbol_id"], "new_name": "VALUE"}]
            with self.assertRaises(RpcError) as stale:
                agent_b.call("workspace_commit", {"expected_revision": old_revision, "operations": op_b})
            self.assertEqual("STALE_REVISION", stale.exception.code)
            self.assertIn("POINTS", agent_a.call("workspace_render", {})["text"])

    def test_lsp_facade_uses_workspace_model(self):
        facade = Facade()
        caps = facade.request("initialize", {})
        self.assertTrue(caps["capabilities"]["renameProvider"])
        uri = "memory://test/program.bas"
        facade.request("textDocument/didOpen", {"textDocument": {
            "uri": uri, "version": 1,
            "text": "FUNCTION TOTAL(SCORE)\nTOTAL=SCORE+1\nEND FUNCTION\n"}})
        symbols = facade.request("textDocument/documentSymbol", {"textDocument": {"uri": uri}})
        self.assertEqual("TOTAL", symbols[0]["name"])
        prepared = facade.request("textDocument/prepareRename", {
            "textDocument": {"uri": uri}, "position": {"line": 0, "character": 17}})
        self.assertEqual("SCORE", prepared["placeholder"])
        before = facade.workspace.render_document(facade.docid(uri))
        edit = facade.request("textDocument/rename", {
            "textDocument": {"uri": uri}, "position": {"line": 0, "character": 17},
            "newName": "POINTS"})
        self.assertEqual(1, edit["documentChanges"][0]["textDocument"]["version"])
        self.assertEqual(2, len(edit["documentChanges"][0]["edits"]))
        did = facade.docid(uri)
        self.assertEqual(before, facade.workspace.render_document(did))
        self.assertEqual(1, facade.workspace.get_revision(did))
        proposed = before.replace("TOTAL(SCORE)", "TOTAL(POINTS)").replace("TOTAL=SCORE+1", "TOTAL=POINTS+1")
        facade.request("textDocument/didChange", {"textDocument": {"uri": uri, "version": 2},
                                                   "contentChanges": [{"text": proposed}]})
        self.assertEqual(proposed, facade.workspace.render_document(did))
        self.assertEqual(2, facade.workspace.get_revision(did))
        with self.assertRaises(WorkspaceError) as stale:
            facade.request("textDocument/didChange", {"textDocument": {"uri": uri, "version": 2},
                                                       "contentChanges": [{"text": "END\n"}]})
        self.assertEqual("STALE_DOCUMENT_VERSION", stale.exception.code)

    def test_lsp_uses_utf16_positions_with_astral_characters(self):
        facade = Facade()
        caps = facade.request("initialize", {})
        self.assertEqual("utf-16", caps["capabilities"]["positionEncoding"])
        uri = "memory://utf16/test.bas"
        source = 'FUNCTION F(SCORE)\nF=SCORE\nPRINT "😀"; SCORE\nEND FUNCTION\n'
        facade.request("textDocument/didOpen", {"textDocument": {"uri": uri, "version": 1, "text": source}})
        cp_start = len('PRINT "😀"; ')
        utf16_start = len('PRINT "😀"; '.encode("utf-16-le")) // 2
        prep = facade.request("textDocument/prepareRename", {
            "textDocument": {"uri": uri}, "position": {"line": 2, "character": utf16_start + 1}})
        self.assertEqual("SCORE", prep["placeholder"])
        self.assertEqual(utf16_start, prep["range"]["start"]["character"])
        self.assertEqual(cp_start + 1, utf16_start)
        before = facade.workspace.render_document(facade.docid(uri))
        proposed_edit = facade.request("textDocument/rename", {
            "textDocument": {"uri": uri}, "position": {"line": 2, "character": utf16_start},
            "newName": "POINTS"})
        self.assertEqual(1, proposed_edit["documentChanges"][0]["textDocument"]["version"])
        edits = proposed_edit["documentChanges"][0]["edits"]
        edit = next(e for e in edits if e["range"]["start"]["line"] == 2)
        self.assertEqual(utf16_start, edit["range"]["start"]["character"])
        self.assertEqual(before, facade.workspace.render_document(facade.docid(uri)))
        after = before.replace("F(SCORE)", "F(POINTS)").replace("F=SCORE", "F=POINTS").replace("; SCORE", "; POINTS")
        facade.request("textDocument/didChange", {"textDocument": {"uri": uri, "version": 2},
                                                   "contentChanges": [{"text": after}]})
        self.assertEqual(after, facade.workspace.render_document(facade.docid(uri)))

    def test_lsp_rejects_sync_after_workspace_changes_since_rename_preview(self):
        facade = Facade()
        uri = "memory://stale/test.bas"
        facade.request("textDocument/didOpen", {"textDocument": {"uri": uri, "version": 1,
            "text": "FUNCTION F(X)\nF=X\nEND FUNCTION\n"}})
        facade.request("textDocument/rename", {"textDocument": {"uri": uri},
            "position": {"line": 0, "character": 11}, "newName": "VALUE"})
        did = facade.docid(uri)
        symbol = next(x for x in facade.workspace.list_symbols(did) if x["kind"] == "parameter")
        facade.workspace.rename_symbol(did, symbol["symbol_id"], "OTHER", 1)
        with self.assertRaises(WorkspaceError) as stale:
            facade.request("textDocument/didChange", {"textDocument": {"uri": uri, "version": 2},
                "contentChanges": [{"text": "FUNCTION F(VALUE)\nF=VALUE\nEND FUNCTION\n"}]})
        self.assertEqual("STALE_PREVIEW", stale.exception.code)

    def test_lsp_stdio_framing(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        messages = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "method": "textDocument/didOpen", "params": {
                "textDocument": {"uri": "memory://lsp/test.bas", "version": 1,
                                 "text": "FUNCTION F(X)\nF=X\nEND FUNCTION\n"}}},
            {"jsonrpc": "2.0", "id": 2, "method": "textDocument/documentSymbol", "params": {
                "textDocument": {"uri": "memory://lsp/test.bas"}}},
        ]
        payload = b""
        for message in messages:
            body = json.dumps(message).encode()
            payload += f"Content-Length: {len(body)}\r\n\r\n".encode() + body
        proc = subprocess.run([sys.executable, "-m", "basic_workspace.lsp"],
                              input=payload, capture_output=True, cwd=root, check=True)
        self.assertIn(b'"id":1', proc.stdout)
        self.assertIn(b'"id":2', proc.stdout)

    def test_multiple_documents_and_symbol_identity(self):
        a = self.open("FUNCTION A(X)\nA=X\nEND FUNCTION\n")
        b = self.open("FUNCTION B(X)\nB=X\nEND FUNCTION\n")
        sa, sb = self.symbol(a, "parameter", "X"), self.symbol(b, "parameter", "X")
        self.assertNotEqual(a, b)
        self.assertNotEqual(sa["symbol_id"], sb["symbol_id"])
        self.assertEqual(2, len(self.ws.list_documents()))

    def test_function_move_preserves_identity_and_body(self):
        did = self.open("FUNCTION A(X)\nA=X\nEND FUNCTION\nFUNCTION B(Y)\nB=Y\nEND FUNCTION\n")
        funcs = [s for s in self.ws.list_symbols(did) if s["kind"] == "function"]
        a, b = funcs
        self.ws.move_function(did, b["symbol_id"], a["symbol_id"], 1)
        text = self.ws.render_document(did)
        self.assertLess(text.index("FUNCTION B"), text.index("FUNCTION A"))
        self.assertEqual(b["symbol_id"], self.symbol(did, "function", "B")["symbol_id"])

    def test_incomplete_input_diagnostic_and_queryable(self):
        did = self.open("FUNCTION HALF(X)\nHALF=X\n")
        self.assertIn("UNCLOSED_FUNCTION", {d["code"] for d in self.ws.get_diagnostics(did)})
        self.assertTrue(self.ws.list_symbols(did))
        self.assertEqual("FUNCTION HALF(X)\nHALF=X\n", self.ws.render_document(did))
        bad = self.open('PRINT "unfinished\n')
        self.assertIn("UNTERMINATED_STRING", {d["code"] for d in self.ws.get_diagnostics(bad)})

    def test_colon_statement_and_case_insensitive_variable_index(self):
        did = self.open("10 LET Score=1: PRINT score\n20 END\n")
        vars_ = [s for s in self.ws.list_symbols(did) if s["kind"] == "variable"]
        self.assertEqual(1, len(vars_))
        self.assertEqual(2, vars_[0]["reference_count"])


if __name__ == "__main__":
    unittest.main()
