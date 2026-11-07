from __future__ import annotations

import json
import pathlib
import struct
import subprocess
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from basic_workspace.mir_execution import MirExecutionService
from basic_workspace.model import Workspace, WorkspaceError


WORKER = pathlib.Path(__file__).resolve().parents[1] / "native/build/mir-worker"


@unittest.skipUnless(WORKER.is_file(), "build MIR worker with scripts/build-mir-worker.sh")
class NumericArrayTests(unittest.TestCase):
    def setUp(self):
        self.workspace = Workspace()
        self.executor = MirExecutionService()
        self.document_id = self.workspace.create_empty_document()["document_id"]

    def create_value_at(self):
        assignments = [
            {"array_ref": {"kind": "local_ref", "name": "VALUES"},
             "index": {"kind": "number", "value": i},
             "expression": {"kind": "number", "value": value}}
            for i, value in enumerate((11, 22, 33, 44))
        ]
        created = self.workspace.create_numeric_function(
            self.document_id, "VALUE_AT", ["I"], 1,
            arrays=[{"name": "VALUES", "upper_bound": 3}],
            array_assignments=assignments,
            expression={"kind": "array_element",
                        "array_ref": {"kind": "local_ref", "name": "VALUES"},
                        "index": {"kind": "local_ref", "name": "I"}})
        function = next(x for x in created["created_entities"] if x["kind"] == "function")
        array = next(x for x in created["created_entities"] if x["kind"] == "array")
        return created, function, array

    def test_atomic_construction_interpreter_jit_and_inclusive_upper_bound(self):
        created, function, array = self.create_value_at()
        self.assertEqual(2, created["revision"])
        self.assertEqual((0, 3), (array["lower_bound"], array["upper_bound"]))
        self.assertEqual(4, array["capacity"])
        expected = {0: 11.0, 2: 33.0, 3: 44.0}
        for engine in ("interp", "jit"):
            for index, value in expected.items():
                with self.subTest(engine=engine, index=index):
                    result = self.executor.execute_function(
                        self.workspace, self.document_id, 2, function["symbol_id"], [index], engine)
                    self.assertEqual(value, result["result"])
        self.assertEqual(
            "FUNCTION VALUE_AT(I)\n  DIM VALUES(3)\n"
            "  VALUES(0) = 11\n  VALUES(1) = 22\n"
            "  VALUES(2) = 33\n  VALUES(3) = 44\n"
            "  VALUE_AT = VALUES(I)\nEND FUNCTION\n",
            self.workspace.render_document(self.document_id))

    def test_semantic_value_edit_preserves_function_array_and_other_statements(self):
        _, function, array = self.create_value_at()
        rows_before = self.workspace.list_function_statements(self.document_id, function["symbol_id"])["items"]
        target = next(x for x in rows_before if x["kind"] == "array_assignment" and
                      x["expression_summary"] == "33")
        self.assertEqual(33.0, self.executor.execute_function(
            self.workspace, self.document_id, 2, function["symbol_id"], [2], "interp")["result"])
        edit = self.workspace.edit_assignment_expression(self.document_id, target["statement_id"],
            {"kind": "number", "value": 77}, 2)
        self.assertEqual(3, edit["revision"])
        rows_after = self.workspace.list_function_statements(self.document_id, function["symbol_id"])["items"]
        self.assertEqual({x["statement_id"] for x in rows_before},
                         {x["statement_id"] for x in rows_after})
        symbols_after = self.workspace.list_symbols(self.document_id)
        self.assertIn(function["symbol_id"], [x["symbol_id"] for x in symbols_after])
        self.assertIn(array["symbol_id"], [x["symbol_id"] for x in symbols_after])
        self.assertEqual(77.0, self.executor.execute_function(
            self.workspace, self.document_id, 3, function["symbol_id"], [2], "interp")["result"])
        self.assertEqual(77.0, self.executor.execute_function(
            self.workspace, self.document_id, 3, function["symbol_id"], [2], "jit")["result"])
        with self.assertRaises(WorkspaceError) as stale:
            self.executor.execute_function(self.workspace, self.document_id, 2,
                                           function["symbol_id"], [2], "jit")
        self.assertEqual("STALE_REVISION", stale.exception.code)

    def test_historical_truncation_rule_and_structured_bounds_errors(self):
        _, function, _ = self.create_value_at()
        for index, expected in ((1.9, 22.0), (-0.5, 11.0)):
            for engine in ("interp", "jit"):
                with self.subTest(index=index, engine=engine):
                    self.assertEqual(expected, self.executor.execute_function(
                        self.workspace, self.document_id, 2, function["symbol_id"], [index], engine)["result"])
        for index in (-1.0, -1.5, 4.0, 1000.0):
            for engine in ("interp", "jit"):
                with self.subTest(index=index, engine=engine), self.assertRaises(WorkspaceError) as caught:
                    self.executor.execute_function(self.workspace, self.document_id, 2,
                                                   function["symbol_id"], [index], engine)
                self.assertEqual("ARRAY_BOUNDS", caught.exception.code)

    def test_two_parallel_arrays_keep_entity_ids_distinct_from_physical_slots(self):
        body = [
            {"array_ref": {"kind": "local_ref", "name": "PERSON_ID"},
             "index": {"kind": "number", "value": i},
             "expression": {"kind": "number", "value": ident}}
            for i, ident in enumerate((101, 205, 900))
        ] + [
            {"array_ref": {"kind": "local_ref", "name": "PERSON_AGE"},
             "index": {"kind": "number", "value": i},
             "expression": {"kind": "number", "value": age}}
            for i, age in enumerate((31, 42, 53))
        ]
        created = self.workspace.create_numeric_function(self.document_id, "AGE_AT", ["I"], 1,
            arrays=[{"name": "PERSON_ID", "upper_bound": 2},
                    {"name": "PERSON_AGE", "upper_bound": 2}],
            array_assignments=body,
            expression={"kind": "array_element",
                        "array_ref": {"kind": "local_ref", "name": "PERSON_AGE"},
                        "index": {"kind": "local_ref", "name": "I"}})
        function = next(x for x in created["created_entities"] if x["kind"] == "function")
        arrays = [x for x in created["created_entities"] if x["kind"] == "array"]
        self.assertEqual({"PERSON_ID", "PERSON_AGE"}, {x["name"] for x in arrays})
        # The model stores logical IDs as ordinary array values; index 2 returns
        # the age in slot 2 even though that slot's entity ID is 900.
        for engine in ("interp", "jit"):
            self.assertEqual(53.0, self.executor.execute_function(
                self.workspace, self.document_id, 2, function["symbol_id"], [2], engine)["result"])
        id_result = self.workspace.edit_assignment_expression(self.document_id,
            created["created_statements"][-1]["statement_id"],
            {"kind": "array_element", "array_ref": {"kind": "symbol_ref",
              "symbol_id": next(x["symbol_id"] for x in arrays if x["name"] == "PERSON_ID")},
             "index": {"kind": "symbol_ref",
              "symbol_id": next(x["symbol_id"] for x in self.workspace.list_symbols(self.document_id)
                                if x["kind"] == "parameter" and x["name"] == "I")}}, 2)
        self.assertEqual(3, id_result["revision"])
        self.assertEqual(900.0, self.executor.execute_function(
            self.workspace, self.document_id, 3, function["symbol_id"], [2], "jit")["result"])

    def test_array_scope_lifetime_and_rejections(self):
        _, function, _ = self.create_value_at()
        # Local arrays are initialized anew on every call, as with historical BASIC.
        for engine in ("interp", "jit"):
            self.assertEqual(33.0, self.executor.execute_function(
                self.workspace, self.document_id, 2, function["symbol_id"], [2], engine)["result"])
            self.assertEqual(33.0, self.executor.execute_function(
                self.workspace, self.document_id, 2, function["symbol_id"], [2], engine)["result"])
        before = self.workspace.render_document(self.document_id)
        with self.assertRaises(WorkspaceError) as stale:
            self.workspace.create_numeric_function(self.document_id, "STALE", ["I"], 1,
                arrays=[{"name": "A", "upper_bound": 2}])
        self.assertEqual("STALE_REVISION", stale.exception.code)
        with self.assertRaises(WorkspaceError) as bad_bound:
            self.workspace.create_numeric_function(self.document_id, "BAD", ["I"], 2,
                arrays=[{"name": "A", "upper_bound": 256}])
        self.assertEqual("INVALID_ARRAY_BOUND", bad_bound.exception.code)
        with self.assertRaises(WorkspaceError) as bad_handle:
            self.workspace.create_numeric_function(self.document_id, "BADREF", ["I"], 2,
                arrays=[{"name": "A", "upper_bound": 2}],
                expression={"kind": "array_element",
                            "array_ref": {"kind": "local_ref", "name": "MISSING"},
                            "index": {"kind": "local_ref", "name": "I"}})
        self.assertEqual("UNKNOWN_TRANSACTION_HANDLE", bad_handle.exception.code)
        self.assertEqual(before, self.workspace.render_document(self.document_id))
        self.assertEqual(2, self.workspace.get_revision(self.document_id))

    def test_dynamic_local_array_mutation_is_reset_for_each_execution(self):
        created = self.workspace.create_numeric_function(self.document_id, "INCREMENTED", ["I"], 1,
            arrays=[{"name": "A", "upper_bound": 0}],
            array_assignments=[
                {"array_ref": {"kind": "local_ref", "name": "A"},
                 "index": {"kind": "number", "value": 0},
                 "expression": {"kind": "number", "value": 1}},
                {"array_ref": {"kind": "local_ref", "name": "A"},
                 "index": {"kind": "number", "value": 0},
                 "expression": {"kind": "binary", "operator": "+",
                    "left": {"kind": "array_element",
                        "array_ref": {"kind": "local_ref", "name": "A"},
                        "index": {"kind": "number", "value": 0}},
                    "right": {"kind": "number", "value": 1}}}],
            expression={"kind": "array_element",
                        "array_ref": {"kind": "local_ref", "name": "A"},
                        "index": {"kind": "number", "value": 0}})
        fn = next(x for x in created["created_entities"] if x["kind"] == "function")
        for engine in ("interp", "jit"):
            self.assertEqual(2.0, self.executor.execute_function(
                self.workspace, self.document_id, 2, fn["symbol_id"], [0], engine)["result"])
            self.assertEqual(2.0, self.executor.execute_function(
                self.workspace, self.document_id, 2, fn["symbol_id"], [0], engine)["result"])

    def test_arrays_start_zero_and_dynamic_indexed_writes_are_checked(self):
        zeroed = self.workspace.create_numeric_function(
            self.document_id, "ZEROED", ["I"], 1,
            arrays=[{"name": "A", "upper_bound": 2}],
            expression={"kind": "array_element",
                        "array_ref": {"kind": "local_ref", "name": "A"},
                        "index": {"kind": "local_ref", "name": "I"}})
        zero_fn = next(row for row in zeroed["created_entities"] if row["kind"] == "function")
        for engine in ("interp", "jit"):
            self.assertEqual(0.0, self.executor.execute_function(
                self.workspace, self.document_id, 2, zero_fn["symbol_id"], [2], engine)["result"])

        setter = self.workspace.create_numeric_function(
            self.document_id, "SET_AT", ["I", "V"], 2,
            arrays=[{"name": "B", "upper_bound": 2}],
            array_assignments=[{"array_ref": {"kind": "local_ref", "name": "B"},
                                "index": {"kind": "local_ref", "name": "I"},
                                "expression": {"kind": "local_ref", "name": "V"}}],
            expression={"kind": "array_element",
                        "array_ref": {"kind": "local_ref", "name": "B"},
                        "index": {"kind": "local_ref", "name": "I"}})
        set_fn = next(row for row in setter["created_entities"] if row["kind"] == "function")
        for engine in ("interp", "jit"):
            self.assertEqual(42.0, self.executor.execute_function(
                self.workspace, self.document_id, 3, set_fn["symbol_id"], [2, 42], engine)["result"])
            with self.assertRaises(WorkspaceError) as caught:
                self.executor.execute_function(self.workspace, self.document_id, 3,
                                               set_fn["symbol_id"], [3, 42], engine)
            self.assertEqual("ARRAY_BOUNDS", caught.exception.code)

    def test_worker_rejects_malformed_array_bounds_and_keeps_bwm1_compatibility(self):
        header = b"BWM2" + struct.pack("<IIII", 2, 0, 0, 1)
        function = struct.pack("<IIII", 0, 0, 1, 0)
        malformed = header + function + struct.pack("<II", 0, 0xFFFFFFFF)
        malformed += struct.pack("<II", 0, 0)
        rejected = subprocess.run([str(WORKER)], input=malformed, capture_output=True, timeout=5)
        self.assertEqual(0, rejected.returncode)
        self.assertEqual("INVALID_PROJECTION", json.loads(rejected.stdout)["code"])

        # Legacy scalar BWM1 payload: zero-arg function returning constant 5.
        legacy = b"BWM1" + struct.pack("<IIII", 1, 0, 0, 1)
        legacy += struct.pack("<III", 0, 0, 1)
        legacy += struct.pack("<B3xI", 1, 0) + b"\x01" + struct.pack("<d", 5.0)
        legacy += struct.pack("<II", 0, 0)
        completed = subprocess.run([str(WORKER)], input=legacy, capture_output=True, timeout=5)
        self.assertEqual(0, completed.returncode)
        result = json.loads(completed.stdout)
        self.assertTrue(result["ok"])
        self.assertEqual(5.0, float.fromhex(result["result_hex"]))

    def test_worker_rejects_malformed_cross_function_reference(self):
        # One function contains a call to function slot 9. The decoder must
        # reject this before MIR lowering, rather than indexing a short proto
        # array. BWM2 function: no args/locals/arrays, one result assignment.
        payload = b"BWM2" + struct.pack("<IIII", 2, 0, 0, 1)
        payload += struct.pack("<IIII", 0, 0, 0, 1)
        payload += struct.pack("<B3xI", 1, 0)  # result target
        payload += struct.pack("<BII", 9, 9, 0)  # EX_CALL callee=9, nargs=0
        payload += struct.pack("<II", 0, 0)  # requested function, invocation argc
        completed = subprocess.run([str(WORKER)], input=payload, capture_output=True, timeout=5)
        self.assertEqual(0, completed.returncode)
        response = json.loads(completed.stdout)
        self.assertEqual("INVALID_PROJECTION", response["code"])

    def test_duplicate_or_ambiguous_array_declarations_are_rejected(self):
        source_cases = (
            "FUNCTION DUP(I)\n  DIM A(2)\n  DIM A(2)\n  DUP = 0\nEND FUNCTION\n",
            "FUNCTION COLLIDE(I)\n  DIM I(2)\n  COLLIDE = 0\nEND FUNCTION\n",
            "FUNCTION OUT(I)\n  DIM INNER(2)\n  OUT = 0\nEND FUNCTION\n"
            "FUNCTION INNER(X)\n  INNER = X\nEND FUNCTION\n",
        )
        for source in source_cases:
            with self.subTest(source=source.splitlines()[0]):
                opened = self.workspace.open_document_from_string(source)
                self.assertTrue(any(d["severity"] == "error" for d in opened["diagnostics"]))


if __name__ == "__main__":
    unittest.main()
