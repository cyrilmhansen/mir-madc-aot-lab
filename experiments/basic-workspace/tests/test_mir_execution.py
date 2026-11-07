from __future__ import annotations

import pathlib
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from basic_workspace.client import WorkspaceClient
from basic_workspace.mir_execution import MirExecutionService
from basic_workspace.model import Workspace, WorkspaceError
from basic_workspace.projection import build_projection


WORKER = pathlib.Path(__file__).resolve().parents[1] / "native/build/mir-worker"


@unittest.skipUnless(WORKER.is_file(), "build MIR worker with scripts/build-mir-worker.sh")
class MirExecutionTests(unittest.TestCase):
    def setUp(self):
        self.workspace = Workspace()
        self.executor = MirExecutionService()

    def open(self, source):
        return self.workspace.open_document_from_string(source)["document_id"]

    def run_fn(self, did, function_name, args, engine="interp", revision=None):
        rows = self.workspace.get_document_structure(did)["functions"]
        fn = next(row for row in rows if row["name"].casefold() == function_name.casefold())
        return self.executor.execute_function(self.workspace, did,
                                              self.workspace.get_revision(did) if revision is None else revision,
                                              fn["symbol_id"], args, engine)

    def test_both_engines_precedence_parentheses_and_unary_minus(self):
        did = self.open("FUNCTION CALC(X)\nCALC = -(X + 2) * 3 + 20 / 4\nEND FUNCTION\n")
        for engine in ("interp", "jit"):
            result = self.run_fn(did, "calc", [2], engine)
            self.assertEqual(-7.0, result["result"])
            self.assertEqual(1, result["revision"])
            self.assertIn("projection", result["timings_ms"])
            self.assertIn("mir_build", result["timings_ms"])
            self.assertIn("mir_link", result["timings_ms"])
            self.assertIn("mir_invoke", result["timings_ms"])

    def test_multiple_functions_and_numeric_call(self):
        did = self.open("FUNCTION DOUBLE(X)\nDOUBLE=X*2\nEND FUNCTION\n"
                        "FUNCTION SUM(A,B)\nSUM=DOUBLE(A)+B\nEND FUNCTION\n")
        self.assertEqual(21.0, self.run_fn(did, "sum", [9, 3])["result"])
        self.assertEqual(21.0, self.run_fn(did, "sum", [9, 3], "jit")["result"])

    def test_semantic_edit_recompiles_current_revision_with_stable_identity(self):
        did = self.open("FUNCTION TOTAL(SCORE)\nTOTAL=SCORE*2\nEND FUNCTION\n")
        structure = self.workspace.get_document_structure(did)
        function_id = structure["functions"][0]["symbol_id"]
        symbols = self.workspace.list_symbols(did)
        parameter = next(s for s in symbols if s["kind"] == "parameter")
        self.assertEqual(18.0, self.executor.execute_function(self.workspace, did, 1, function_id, [9])["result"])
        self.workspace.rename_symbol(did, parameter["symbol_id"], "POINTS", 1)
        self.assertEqual(18.0, self.executor.execute_function(self.workspace, did, 2, function_id, [9], "jit")["result"])
        self.assertEqual(function_id, self.workspace.get_document_structure(did)["functions"][0]["symbol_id"])
        self.assertEqual(2, build_projection(self.workspace, did, 2).revision)
        with self.assertRaises(WorkspaceError) as stale:
            self.executor.execute_function(self.workspace, did, 1, function_id, [9])
        self.assertEqual("STALE_REVISION", stale.exception.code)

    def test_function_rename_keeps_identity_and_bound_call(self):
        did = self.open("FUNCTION DOUBLE(X)\nDOUBLE=X*2\nEND FUNCTION\n"
                        "FUNCTION APPLY(Y)\nAPPLY=double(Y)+1\nEND FUNCTION\n")
        rows = self.workspace.get_document_structure(did)["functions"]
        double_id = rows[0]["symbol_id"]
        self.assertEqual(19.0, self.executor.execute_function(self.workspace, did, 1,
                                                               rows[1]["symbol_id"], [9])["result"])
        self.workspace.rename_symbol(did, double_id, "TWICE", 1)
        self.assertEqual(19.0, self.executor.execute_function(self.workspace, did, 2,
                                                               rows[1]["symbol_id"], [9], "jit")["result"])

    def test_unsupported_syntax_fails_explicitly(self):
        did = self.open("FUNCTION F(X)\nIF X THEN F=1\nEND FUNCTION\n")
        with self.assertRaises(WorkspaceError) as caught:
            self.run_fn(did, "F", [1])
        self.assertIn(caught.exception.code, ("UNSUPPORTED_STATEMENT", "NOT_COMPILABLE"))
        did2 = self.open("FUNCTION TEXT$(X$)\nTEXT$=X$\nEND FUNCTION\n")
        with self.assertRaises(WorkspaceError) as string_error:
            self.run_fn(did2, "TEXT$", [1])
        self.assertEqual("UNSUPPORTED_TYPE", string_error.exception.code)

    def test_unknown_function_bad_arity_and_argument_type_are_rejected(self):
        did = self.open("FUNCTION F(X)\nF=X\nEND FUNCTION\n")
        fn = self.workspace.get_document_structure(did)["functions"][0]
        for identity, args, code in (("sym_not_discovered", [2], "SYMBOL_NOT_FOUND"),
                                     (fn["symbol_id"], [], "ARGUMENT_COUNT"),
                                     (fn["symbol_id"], [True], "INVALID_ARGUMENT_TYPE")):
            with self.subTest(code=code), self.assertRaises(WorkspaceError) as caught:
                self.executor.execute_function(self.workspace, did, 1, identity, args)
            self.assertEqual(code, caught.exception.code)

    def test_incomplete_function_fails_without_worker_execution(self):
        did = self.open("FUNCTION F(X)\nF=X+1\n")
        with self.assertRaises(WorkspaceError) as caught:
            self.run_fn(did, "F", [1])
        self.assertEqual("NOT_COMPILABLE", caught.exception.code)

    def test_execution_does_not_render_or_relex_basic_text(self):
        did = self.open("FUNCTION F(X)\nF=X+1\nEND FUNCTION\n")
        fn = self.workspace.get_document_structure(did)["functions"][0]
        with patch.object(self.workspace, "render_document", side_effect=AssertionError("rendered BASIC")), \
             patch("basic_workspace.model.lex", side_effect=AssertionError("relexed BASIC")):
            self.assertEqual(4.0, self.executor.execute_function(self.workspace, did, 1,
                                                                  fn["symbol_id"], [3])["result"])

    def test_json_rpc_requires_discovery_and_checks_revision(self):
        source = "FUNCTION F(X)\nF=X+1\nEND FUNCTION\n"
        with WorkspaceClient() as client:
            opened = client.workspace_open(source)
            # Open does not reveal an executable identity. Structure discovery does.
            structure = client.workspace_structure()
            fn = structure["functions"][0]
            result = client.workspace_execute_function(1, fn["symbol_id"], [4], "jit")
            self.assertEqual(5.0, result["result"])
            with self.assertRaises(Exception) as stale:
                client.workspace_execute_function(0, fn["symbol_id"], [4])
            self.assertEqual("STALE_REVISION", stale.exception.code)
            self.assertEqual(opened["document_id"], result["document_id"])


if __name__ == "__main__":
    unittest.main()
