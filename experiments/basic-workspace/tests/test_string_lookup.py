from __future__ import annotations

import pathlib
import json
import struct
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from basic_workspace.mir_execution import MirExecutionService, encode_projection
from basic_workspace.client import WorkspaceClient
from basic_workspace.model import Workspace, WorkspaceError
from basic_workspace.projection import build_projection


WORKER = pathlib.Path(__file__).resolve().parents[1] / "native/build/mir-worker"


def lookup_body():
    body = []
    for index, (entity_id, name) in enumerate(((101, "Alice"), (205, "Bob"), (900, "Chloé"))):
        body.extend((
            {"kind": "array_assign", "array_ref": {"kind": "local_ref", "name": "PERSON_ID"},
             "index": {"kind": "number", "value": index}, "expression": {"kind": "number", "value": entity_id}},
            {"kind": "array_assign", "array_ref": {"kind": "local_ref", "name": "PERSON_NAMES$"},
             "index": {"kind": "number", "value": index}, "expression": {"kind": "string", "value": name}},
        ))
    body.extend((
        {"kind": "assign", "target": {"kind": "result"}, "expression": {"kind": "string", "value": ""}},
        {"kind": "for", "variable": "I", "start": {"kind": "number", "value": 0},
         "end": {"kind": "number", "value": 2}, "body": [{
             "kind": "if", "condition": {"kind": "binary", "operator": "=",
                 "left": {"kind": "array_element", "array_ref": {"kind": "local_ref", "name": "PERSON_ID"},
                          "index": {"kind": "local_ref", "name": "I"}},
                 "right": {"kind": "local_ref", "name": "WANTED"}},
             "then": [{"kind": "assign", "target": {"kind": "result"},
                       "expression": {"kind": "array_element", "array_ref": {"kind": "local_ref", "name": "PERSON_NAMES$"},
                                      "index": {"kind": "local_ref", "name": "I"}}}]}]},
    ))
    return body


@unittest.skipUnless(WORKER.is_file(), "build MIR worker with scripts/build-mir-worker.sh")
class StringLookupTests(unittest.TestCase):
    def setUp(self):
        self.workspace = Workspace()
        self.document_id = self.workspace.create_empty_document()["document_id"]
        created = self.workspace.create_string_function(
            self.document_id, "PERSON_NAME$", ["WANTED"], 1,
            arrays=[{"name": "PERSON_ID", "upper_bound": 2},
                    {"name": "PERSON_NAMES$", "upper_bound": 2}],
            body=lookup_body())
        self.revision = created["revision"]
        self.function_id = next(f["symbol_id"] for f in self.workspace.get_document_structure(self.document_id)["functions"]
                                if f["name"] == "PERSON_NAME$")
        self.arrays = {s["name"]: s for s in self.workspace.list_symbols(self.document_id)
                       if s["kind"] == "array"}
        self.executor = MirExecutionService()

    def execute(self, entity_id, engine, revision=None):
        return self.executor.execute_function(self.workspace, self.document_id,
            self.revision if revision is None else revision, self.function_id, [entity_id], engine)

    def test_lookup_both_engines_and_empty_missing_values(self):
        expected = {101: "Alice", 205: "Bob", 900: "Chloé", 999: "", 2: ""}
        for engine in ("interp", "jit"):
            for entity_id, value in expected.items():
                with self.subTest(engine=engine, entity_id=entity_id):
                    result = self.execute(entity_id, engine)
                    self.assertEqual("string", result["result_type"])
                    self.assertEqual(value, result["result"])

    def test_semantic_string_edit_preserves_identity_and_recompiles(self):
        before = self.workspace.list_function_statements(self.document_id, self.function_id)
        statement = next(row for row in before["items"]
                         if row["target_symbol_id"] == self.arrays["PERSON_NAMES$"]["symbol_id"]
                         and row["expression_summary"] == '"Bob"')
        ids_before = {row["statement_id"] for row in before["items"]}
        result = self.workspace.edit_assignment_expression(
            self.document_id, statement["statement_id"],
            {"kind": "string", "value": "Robert"}, self.revision)
        self.revision = result["revision"]
        self.assertEqual("Robert", self.execute(205, "interp")["result"])
        self.assertEqual("Robert", self.execute(205, "jit")["result"])
        self.assertEqual("Alice", self.execute(101, "interp")["result"])
        self.assertEqual(self.function_id, self.workspace.get_document_structure(self.document_id)["functions"][0]["symbol_id"])
        after = self.workspace.list_function_statements(self.document_id, self.function_id)
        self.assertTrue(ids_before.issubset({row["statement_id"] for row in after["items"]}))
        self.assertEqual({"PERSON_ID": self.arrays["PERSON_ID"]["symbol_id"],
                          "PERSON_NAMES$": self.arrays["PERSON_NAMES$"]["symbol_id"]},
                         {s["name"]: s["symbol_id"] for s in self.workspace.list_symbols(self.document_id) if s["kind"] == "array"})
        with self.assertRaises(WorkspaceError) as stale:
            self.execute(205, "interp", revision=2)
        self.assertEqual("STALE_REVISION", stale.exception.code)

    def test_wrong_type_edit_rolls_back(self):
        before = self.workspace.list_function_statements(self.document_id, self.function_id)
        statement = next(row for row in before["items"]
                         if row["target_symbol_id"] == self.arrays["PERSON_NAMES$"]["symbol_id"]
                         and row["expression_summary"] == '"Bob"')
        with self.assertRaises(WorkspaceError) as caught:
            self.workspace.edit_assignment_expression(self.document_id, statement["statement_id"],
                {"kind": "number", "value": 17}, self.revision)
        self.assertEqual("TYPE_MISMATCH", caught.exception.code)
        self.assertEqual(self.revision, self.workspace.get_revision(self.document_id))
        self.assertEqual("Bob", self.execute(205, "jit")["result"])

    def test_array_metadata_and_empty_initialization(self):
        symbols = {s["name"]: s for s in self.workspace.list_symbols(self.document_id) if s["kind"] == "array"}
        self.assertEqual("string", symbols["PERSON_NAMES$"]["element_type"])
        self.assertEqual("numeric", symbols["PERSON_ID"]["element_type"])

    def test_execution_never_renders_or_relexes(self):
        with patch.object(self.workspace, "render_document", side_effect=AssertionError("render")), \
             patch("basic_workspace.model.lex", side_effect=AssertionError("relex")):
            self.assertEqual("Chloé", self.execute(900, "jit")["result"])

    def test_string_literal_limits(self):
        for value, code in (("a\0b", "INVALID_STRING"), ("line\nbreak", "INVALID_STRING"),
                            ("x" * 4097, "STRING_LIMIT"), ("\ud800", "INVALID_UTF8")):
            did = self.workspace.create_empty_document()["document_id"]
            with self.assertRaises(WorkspaceError) as caught:
                self.workspace.create_string_function(did, "TEXT$", [], 1,
                    expression={"kind": "string", "value": value})
            self.assertEqual(code, caught.exception.code)

    def test_projection_is_revision_bound_and_contains_string_types(self):
        projection = build_projection(self.workspace, self.document_id, self.revision)
        fn = next(item for item in projection.functions if item.symbol_id == self.function_id)
        self.assertEqual("string", fn.return_type)
        self.assertEqual("string", next(a.element_type for a in fn.arrays if a.name == "PERSON_NAMES$"))
        with self.assertRaises(WorkspaceError) as stale:
            build_projection(self.workspace, self.document_id, self.revision - 1)
        self.assertEqual("STALE_REVISION", stale.exception.code)

    def test_string_local_and_json_rpc_agent_constructor(self):
        did = self.workspace.create_empty_document()["document_id"]
        created = self.workspace.create_string_function(did, "LABEL$", [], 1,
            locals=[{"name": "TEXT$", "expression": {"kind": "string", "value": "A \"quoted\" label"}}],
            expression={"kind": "local_ref", "name": "TEXT$"})
        fn = self.workspace.get_document_structure(did)["functions"][0]
        self.assertEqual("A \"quoted\" label", MirExecutionService().execute_function(
            self.workspace, did, created["revision"], fn["symbol_id"], [], "interp")["result"])
        with WorkspaceClient() as client:
            client.workspace_create_empty()
            made = client.workspace_create_function(1, "TEXT$", [],
                expression={"kind": "string", "value": "from json-rpc"})
            structure = client.workspace_structure()
            function = structure["functions"][0]
            output = client.workspace_execute_function(made["revision"], function["symbol_id"], [], "jit")
            self.assertEqual("from json-rpc", output["result"])

    def test_string_array_bounds_and_default_empty_cell(self):
        did = self.workspace.create_empty_document()["document_id"]
        made = self.workspace.create_string_function(did, "CELL$", ["I"], 1,
            arrays=[{"name": "CELLS$", "upper_bound": 1}],
            expression={"kind": "array_element",
                        "array_ref": {"kind": "local_ref", "name": "CELLS$"},
                        "index": {"kind": "local_ref", "name": "I"}})
        fn = self.workspace.get_document_structure(did)["functions"][0]
        runner = MirExecutionService()
        self.assertEqual("", runner.execute_function(self.workspace, did, made["revision"],
                                                        fn["symbol_id"], [0], "jit")["result"])
        with self.assertRaises(WorkspaceError) as caught:
            runner.execute_function(self.workspace, did, made["revision"], fn["symbol_id"], [2])
        self.assertEqual("ARRAY_BOUNDS", caught.exception.code)

    def test_malformed_bwm4_string_lengths_are_rejected(self):
        did = self.workspace.open_document_from_string(
            'FUNCTION TEXT$()\nTEXT$ = "ok"\nEND FUNCTION\n')["document_id"]
        fn = self.workspace.get_document_structure(did)["functions"][0]
        projection = build_projection(self.workspace, did, 1)
        payload = bytearray(encode_projection(projection, 0, [], "interp"))
        marker = payload.find(b"\x11")
        self.assertGreaterEqual(marker, 0)
        payload[marker + 1:marker + 5] = struct.pack("<I", 4097)
        completed = subprocess.run([str(WORKER)], input=payload, capture_output=True, check=False)
        self.assertEqual(0, completed.returncode)
        response = json.loads(completed.stdout)
        self.assertFalse(response["ok"])
        self.assertEqual("INVALID_PROJECTION", response["code"])
        invalid_utf8 = bytearray(encode_projection(projection, 0, [], "interp"))
        marker = invalid_utf8.find(b"\x11")
        invalid_utf8[marker + 5:marker + 7] = b"\xff\x80"
        completed = subprocess.run([str(WORKER)], input=invalid_utf8, capture_output=True, check=False)
        self.assertEqual(0, completed.returncode)
        response = json.loads(completed.stdout)
        self.assertFalse(response["ok"])
        self.assertEqual("INVALID_PROJECTION", response["code"])


if __name__ == "__main__":
    unittest.main()
