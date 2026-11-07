from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from basic_workspace.client import AgentToolAdapter, RpcError, WorkspaceClient
from basic_workspace.model import Workspace, WorkspaceError
from basic_workspace.mir_execution import MirExecutionService


WORKER = pathlib.Path(__file__).resolve().parents[1] / "native/build/mir-worker"


@unittest.skipUnless(WORKER.is_file(), "build MIR worker with scripts/build-mir-worker.sh")
class ProgramConstructionTests(unittest.TestCase):
    def test_atomic_function_constructor_resolves_transaction_local_parameter(self):
        with WorkspaceClient() as client:
            agent = AgentToolAdapter(client)
            opened = agent.call("workspace_create_empty", {})
            created = agent.call("workspace_create_function", {
                "expected_revision": opened["revision"],
                "name": "DOUBLE", "parameters": ["X"],
                "expression": {"kind": "binary", "operator": "*",
                    "left": {"kind": "local_ref", "name": "X"},
                    "right": {"kind": "number", "value": 2}}})
            self.assertEqual(2, created["revision"])
            self.assertEqual(1, len(created["created_statements"]))
            function = next(x for x in created["created_entities"] if x["kind"] == "function")
            parameter = next(x for x in created["created_entities"] if x["kind"] == "parameter")
            self.assertEqual("X", parameter["name"])
            self.assertEqual(18.0, agent.call("workspace_execute_function", {
                "expected_revision": 2, "function_id": function["symbol_id"],
                "arguments": [9], "engine": "interp"})["result"])
            self.assertEqual(18.0, agent.call("workspace_execute_function", {
                "expected_revision": 2, "function_id": function["symbol_id"],
                "arguments": [9], "engine": "jit"})["result"])

    def test_atomic_constructor_orders_locals_and_rolls_back_bad_handles(self):
        workspace = Workspace()
        did = workspace.create_empty_document()["document_id"]
        created = workspace.create_numeric_function(did, "COMBINE", ["A", "B"], 1,
            expression={"kind": "binary", "operator": "+",
                "left": {"kind": "local_ref", "name": "PRODUCT"},
                "right": {"kind": "local_ref", "name": "B"}},
            locals=[{"name": "PRODUCT", "expression": {
                "kind": "binary", "operator": "*",
                "left": {"kind": "local_ref", "name": "A"},
                "right": {"kind": "local_ref", "name": "B"}}}])
        function = next(x for x in created["created_entities"] if x["kind"] == "function")
        local = next(x for x in created["created_entities"] if x["name"] == "PRODUCT")
        self.assertEqual(2, created["revision"])
        self.assertEqual(2, len(created["created_statements"]))
        self.assertEqual(24.0, MirExecutionService().execute_function(
            workspace, did, 2, function["symbol_id"], [5, 4], "jit")["result"])
        with self.assertRaises(WorkspaceError) as raised:
            workspace.create_numeric_function(did, "BROKEN", ["X"], 2,
                expression={"kind": "local_ref", "name": "ABSENT"})
        self.assertEqual("UNKNOWN_TRANSACTION_HANDLE", raised.exception.code)
        self.assertEqual(2, workspace.get_revision(did))
        self.assertNotIn("BROKEN", [x["name"] for x in workspace.get_document_structure(did)["functions"]])
        self.assertEqual(local["symbol_id"], next(
            x["symbol_id"] for x in workspace.list_symbols(did) if x["name"] == "PRODUCT"))

    def test_agent_constructs_and_evolves_program_from_empty_document(self):
        with WorkspaceClient() as client:
            agent = AgentToolAdapter(client)
            opened = agent.call("workspace_create_empty", {})
            did = opened["document_id"]
            self.assertEqual(1, opened["revision"])

            created = agent.call("workspace_create_function", {
                "expected_revision": 1, "name": "DOUBLE", "parameters": ["X"]})
            double = next(x for x in created["created_entities"] if x["kind"] == "function")
            x = next(x for x in created["created_entities"] if x["kind"] == "parameter")
            self.assertEqual(2, created["revision"])
            self.assertEqual(0.0, agent.call("workspace_execute_function", {
                "expected_revision": 2, "function_id": double["symbol_id"], "arguments": [9]})["result"])

            statements = agent.call("workspace_statements", {"function_id": double["symbol_id"]})
            result_stmt = statements["items"][0]
            twice = {"kind": "binary", "operator": "*",
                     "left": {"kind": "symbol_ref", "symbol_id": x["symbol_id"]},
                     "right": {"kind": "number", "value": 2}}
            preview = agent.call("workspace_preview", {"expected_revision": 2,
                "operations": [{"operation": "edit_assignment_expression",
                                "statement_id": result_stmt["statement_id"], "expression": twice}]})
            self.assertEqual(2, preview["base_revision"])
            self.assertEqual(2, client.revision)
            edited = agent.call("workspace_edit_expression", {
                "expected_revision": 2, "statement_id": result_stmt["statement_id"],
                "expression": twice})
            self.assertTrue(edited["committed"])
            self.assertEqual(18.0, agent.call("workspace_execute_function", {
                "expected_revision": 3, "function_id": double["symbol_id"],
                "arguments": [9], "engine": "interp"})["result"])

            calc_created = agent.call("workspace_create_function", {
                "expected_revision": 3, "name": "CALCULATE", "parameters": ["Y"]})
            calc = next(x for x in calc_created["created_entities"] if x["kind"] == "function")
            y = next(x for x in calc_created["created_entities"] if x["kind"] == "parameter")
            calc_stmt = agent.call("workspace_statements", {"function_id": calc["symbol_id"]})["items"][0]
            call_expr = {"kind": "binary", "operator": "+",
                         "left": {"kind": "call", "function_id": double["symbol_id"],
                                  "arguments": [{"kind": "symbol_ref", "symbol_id": y["symbol_id"]}]},
                         "right": {"kind": "number", "value": 3}}
            agent.call("workspace_edit_expression", {"expected_revision": 4,
                "statement_id": calc_stmt["statement_id"], "expression": call_expr})
            self.assertEqual(21.0, agent.call("workspace_execute_function", {
                "expected_revision": 5, "function_id": calc["symbol_id"], "arguments": [9]})["result"])

            triple = {"kind": "binary", "operator": "*",
                      "left": {"kind": "symbol_ref", "symbol_id": x["symbol_id"]},
                      "right": {"kind": "number", "value": 3}}
            agent.call("workspace_edit_expression", {"expected_revision": 5,
                "statement_id": result_stmt["statement_id"], "expression": triple})
            self.assertEqual(30.0, agent.call("workspace_execute_function", {
                "expected_revision": 6, "function_id": calc["symbol_id"], "arguments": [9], "engine": "jit"})["result"])

            renamed = agent.call("workspace_commit", {"expected_revision": 6,
                "operations": [{"operation": "rename_symbol", "symbol_id": double["symbol_id"],
                                "new_name": "TRIPLE"}]})
            self.assertEqual(7, renamed["revision"])
            for engine in ("interp", "jit"):
                self.assertEqual(30.0, agent.call("workspace_execute_function", {
                    "expected_revision": 7, "function_id": calc["symbol_id"],
                    "arguments": [9], "engine": engine})["result"])
            rendered = agent.call("workspace_render", {})["text"]
            self.assertEqual("FUNCTION TRIPLE(X)\n  TRIPLE = (X * 3)\nEND FUNCTION\n"
                             "FUNCTION CALCULATE(Y)\n  CALCULATE = (TRIPLE(Y) + 3)\nEND FUNCTION\n", rendered)
            self.assertEqual(7, client.revision)

    def test_insert_local_before_result_and_preserve_statement_identity(self):
        workspace = Workspace()
        did = workspace.create_empty_document()["document_id"]
        created = workspace.create_numeric_function(did, "PLUSONE", ["X"], 1)
        fn = next(x for x in created["created_entities"] if x["kind"] == "function")
        param = next(x for x in created["created_entities"] if x["kind"] == "parameter")
        result_stmt = created["created_statements"][0]
        executor = MirExecutionService()
        expression = {"kind": "binary", "operator": "+",
                      "left": {"kind": "symbol_ref", "symbol_id": param["symbol_id"]},
                      "right": {"kind": "number", "value": 1}}
        inserted = workspace.insert_numeric_assignment(did, fn["symbol_id"],
            {"kind": "local", "name": "TMP"}, expression, 2,
            before_statement_id=result_stmt["statement_id"])
        tmp = next(x for x in inserted["created_entities"] if x["kind"] == "variable")
        new_stmt = inserted["created_statements"][0]
        self.assertEqual("TMP", tmp["name"])
        self.assertNotEqual(result_stmt["statement_id"], new_stmt["statement_id"])
        self.assertEqual(result_stmt["statement_id"], workspace.list_function_statements(
            did, fn["symbol_id"])["items"][1]["statement_id"])
        replacement = {"kind": "binary", "operator": "*",
                       "left": {"kind": "symbol_ref", "symbol_id": tmp["symbol_id"]},
                       "right": {"kind": "number", "value": 2}}
        workspace.edit_assignment_expression(did, result_stmt["statement_id"], replacement, 3)
        self.assertEqual(20.0, executor.execute_function(workspace, did, 4,
                         fn["symbol_id"], [9], "jit")["result"])

    def test_constructive_transactions_reject_bad_bindings_atomically(self):
        workspace = Workspace()
        did = workspace.create_empty_document()["document_id"]
        created = workspace.create_numeric_function(did, "F", ["X"], 1)
        fn = next(x for x in created["created_entities"] if x["kind"] == "function")
        x = next(x for x in created["created_entities"] if x["kind"] == "parameter")
        statement = created["created_statements"][0]
        before = workspace.render_document(did)
        executor = MirExecutionService()
        self.assertEqual(0.0, executor.execute_function(workspace, did, 2,
                          fn["symbol_id"], [7])["result"])
        for expression, code in (
            ({"kind": "symbol_ref", "symbol_id": "sym_fake"}, "SYMBOL_NOT_FOUND"),
            ({"kind": "binary", "operator": "%", "left": {"kind": "number", "value": 1},
              "right": {"kind": "number", "value": 2}}, "INVALID_OPERATOR"),
            ({"kind": "call", "function_id": fn["symbol_id"], "arguments": []}, "ARGUMENT_COUNT"),
            ({"kind": "number", "value": float("inf")}, "NON_FINITE_CONSTANT"),
        ):
            with self.subTest(code=code), self.assertRaises(WorkspaceError) as caught:
                workspace.edit_assignment_expression(did, statement["statement_id"], expression, 2)
            self.assertEqual(code, caught.exception.code)
            self.assertEqual(2, workspace.get_revision(did))
            self.assertEqual(before, workspace.render_document(did))
        self.assertEqual(0.0, executor.execute_function(workspace, did, 2,
                          fn["symbol_id"], [7])["result"])
        with self.assertRaises(WorkspaceError) as collision:
            workspace.create_numeric_function(did, "f", ["X"], 2)
        self.assertEqual("NAME_COLLISION", collision.exception.code)
        self.assertEqual(before, workspace.render_document(did))
        with self.assertRaises(WorkspaceError) as stale:
            workspace.edit_assignment_expression(did, statement["statement_id"],
                {"kind": "symbol_ref", "symbol_id": x["symbol_id"]}, 1)
        self.assertEqual("STALE_REVISION", stale.exception.code)

    def test_cross_scope_symbol_reference_and_bad_position_are_rejected(self):
        workspace = Workspace()
        did = workspace.create_empty_document()["document_id"]
        left = workspace.create_numeric_function(did, "LEFTF", ["A"], 1)
        right = workspace.create_numeric_function(did, "RIGHTF", ["B"], 2)
        left_fn = next(x for x in left["created_entities"] if x["kind"] == "function")
        right_fn = next(x for x in right["created_entities"] if x["kind"] == "function")
        a = next(x for x in left["created_entities"] if x["kind"] == "parameter")
        rhs = right["created_statements"][0]
        before = workspace.render_document(did)
        with self.assertRaises(WorkspaceError) as cross:
            workspace.edit_assignment_expression(did, rhs["statement_id"],
                {"kind": "symbol_ref", "symbol_id": a["symbol_id"]}, 3)
        self.assertEqual("CROSS_SCOPE_REFERENCE", cross.exception.code)
        with self.assertRaises(WorkspaceError) as bad_position:
            workspace.insert_numeric_assignment(did, right_fn["symbol_id"],
                {"kind": "result"}, {"kind": "number", "value": 1}, 3,
                before_statement_id=left["created_statements"][0]["statement_id"])
        self.assertEqual("CROSS_SCOPE_STATEMENT", bad_position.exception.code)
        self.assertEqual(before, workspace.render_document(did))
        self.assertEqual(3, workspace.get_revision(did))

    def test_recursive_call_graph_is_rejected_atomically(self):
        workspace = Workspace()
        did = workspace.create_empty_document()["document_id"]
        first = workspace.create_numeric_function(did, "FIRST", ["X"], 1)
        second = workspace.create_numeric_function(did, "SECOND", ["Y"], 2)
        first_fn = next(x for x in first["created_entities"] if x["kind"] == "function")
        second_fn = next(x for x in second["created_entities"] if x["kind"] == "function")
        x = next(x for x in first["created_entities"] if x["kind"] == "parameter")
        y = next(x for x in second["created_entities"] if x["kind"] == "parameter")
        first_stmt = first["created_statements"][0]
        second_stmt = second["created_statements"][0]
        workspace.edit_assignment_expression(did, first_stmt["statement_id"],
            {"kind": "call", "function_id": second_fn["symbol_id"],
             "arguments": [{"kind": "symbol_ref", "symbol_id": x["symbol_id"]}]}, 3)
        before = workspace.render_document(did)
        with self.assertRaises(WorkspaceError) as caught:
            workspace.edit_assignment_expression(did, second_stmt["statement_id"],
                {"kind": "call", "function_id": first_fn["symbol_id"],
                 "arguments": [{"kind": "symbol_ref", "symbol_id": y["symbol_id"]}]}, 4)
        self.assertEqual("RECURSIVE_CALL_UNSUPPORTED", caught.exception.code)
        self.assertEqual(4, workspace.get_revision(did))
        self.assertEqual(before, workspace.render_document(did))


if __name__ == "__main__":
    unittest.main()
