from __future__ import annotations

import pathlib
import json
import struct
import subprocess
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from basic_workspace.mir_execution import MirExecutionService
from basic_workspace.model import Workspace, WorkspaceError


WORKER = pathlib.Path(__file__).resolve().parents[1] / "native/build/mir-worker"


def num(value):
    return {"kind": "number", "value": value}


def local(name):
    return {"kind": "local_ref", "name": name}


def ref(name):
    return {"kind": "symbol_ref", "symbol_id": name}


def array(name, index):
    return {"kind": "array_element", "array_ref": local(name), "index": index}


@unittest.skipUnless(WORKER.is_file(), "build MIR worker with scripts/build-mir-worker.sh")
class ControlFlowLookupTests(unittest.TestCase):
    def setUp(self):
        self.workspace = Workspace()
        self.document_id = self.workspace.create_empty_document()["document_id"]
        self.executor = MirExecutionService()

    def create_lookup(self):
        body = []
        people = ((101, 25), (205, 42), (900, 53))
        for name, column in (("PERSON_ID", 0), ("PERSON_AGE", 1)):
            for index, person in enumerate(people):
                body.append({"kind": "array_assign", "array_ref": local(name),
                             "index": num(index), "expression": num(person[column])})
        condition = {"kind": "binary", "operator": "=",
                     "left": array("PERSON_ID", local("I")),
                     "right": local("WANTED")}
        body.append({"kind": "assign", "target": {"kind": "result"}, "expression": num(-1)})
        body.append({"kind": "for", "variable": "I", "start": num(0), "end": num(2),
                     "body": [{"kind": "if", "condition": condition,
                               "then": [{"kind": "assign", "target": {"kind": "result"},
                                         "expression": array("PERSON_AGE", local("I"))}]}]})
        created = self.workspace.create_numeric_function(
            self.document_id, "AGE_BY_ID", ["WANTED"], 1,
            arrays=[{"name": "PERSON_ID", "upper_bound": 2},
                    {"name": "PERSON_AGE", "upper_bound": 2}],
            body=body)
        function = next(e for e in created["created_entities"] if e["kind"] == "function")
        arrays = {e["name"]: e for e in created["created_entities"] if e["kind"] == "array"}
        return created, function, arrays

    def test_entity_id_lookup_interpreter_and_jit(self):
        created, function, arrays = self.create_lookup()
        self.assertEqual(2, created["revision"])
        self.assertEqual({"PERSON_ID", "PERSON_AGE"}, set(arrays))
        expected = {101: 25.0, 205: 42.0, 900: 53.0, 999: -1.0, 2: -1.0}
        for engine in ("interp", "jit"):
            actual = {key: self.executor.execute_function(self.workspace, self.document_id, 2,
                function["symbol_id"], [key], engine)["result"] for key in expected}
            self.assertEqual(expected, actual)

    def test_semantic_age_update_preserves_function_arrays_and_statements(self):
        _, function, arrays = self.create_lookup()
        before = self.workspace.list_function_statements(self.document_id, function["symbol_id"])["items"]
        target = next(item for item in before if item["kind"] == "array_assignment" and
                      item["expression_summary"] == "42")
        self.assertEqual(42.0, self.executor.execute_function(self.workspace, self.document_id, 2,
            function["symbol_id"], [205], "jit")["result"])
        edit = self.workspace.edit_assignment_expression(self.document_id,
            target["statement_id"], num(47), 2)
        self.assertEqual(3, edit["revision"])
        with self.assertRaises(WorkspaceError):
            self.workspace.create_numeric_function(self.document_id, "BROKEN", [], 3,
                body=[{"kind":"for", "variable":"J", "start":num(0), "end":num(2),
                       "step":num(0), "body":[]}])
        self.assertEqual(3, self.workspace.get_revision(self.document_id))
        after = self.workspace.list_function_statements(self.document_id, function["symbol_id"])["items"]
        self.assertEqual({s["statement_id"] for s in before}, {s["statement_id"] for s in after})
        symbols = {item["symbol_id"] for item in self.workspace.list_symbols(self.document_id)}
        self.assertTrue({function["symbol_id"], *(a["symbol_id"] for a in arrays.values())} <= symbols)
        for engine in ("interp", "jit"):
            self.assertEqual(47.0, self.executor.execute_function(self.workspace, self.document_id, 3,
                function["symbol_id"], [205], engine)["result"])
            self.assertEqual(25.0, self.executor.execute_function(self.workspace, self.document_id, 3,
                function["symbol_id"], [101], engine)["result"])
        with self.assertRaises(WorkspaceError) as stale:
            self.executor.execute_function(self.workspace, self.document_id, 2,
                function["symbol_id"], [205], "interp")
        self.assertEqual("STALE_REVISION", stale.exception.code)

    def test_if_else_comparisons_and_nested_branches(self):
        created = self.workspace.create_numeric_function(self.document_id, "CLASSIFY", ["X"], 1,
            locals=[{"name": "R", "expression": num(0)}],
            body=[{"kind": "if", "condition": {"kind": "binary", "operator": "<",
                     "left": local("X"), "right": num(0)},
                   "then": [{"kind": "assign", "target": {"kind": "local", "name": "R"},
                             "expression": num(-1)}],
                   "else": [{"kind": "if", "condition": {"kind": "binary", "operator": "=",
                               "left": local("X"), "right": num(0)},
                             "then": [{"kind": "assign", "target": {"kind": "local", "name": "R"},
                                       "expression": num(0)}],
                             "else": [{"kind": "assign", "target": {"kind": "local", "name": "R"},
                                       "expression": num(1)}]}]}], expression=local("R"))
        function = next(e for e in created["created_entities"] if e["kind"] == "function")
        for engine in ("interp", "jit"):
            self.assertEqual([-1.0, 0.0, 1.0], [self.executor.execute_function(
                self.workspace, self.document_id, 2, function["symbol_id"], [x], engine)["result"]
                for x in (-3, 0, 2)])

    def test_fixed_step_and_zero_iteration_loops(self):
        created = self.workspace.create_numeric_function(self.document_id, "SUM", [], 1,
            locals=[{"name":"R","expression":num(0)}],
            body=[{"kind":"for","variable":"I","start":num(1),"end":num(3),
                   "body":[{"kind":"assign","target":{"kind":"local","name":"R"},
                     "expression":{"kind":"binary","operator":"+","left":local("R"),"right":local("I")}}]}],
            expression=local("R"))
        function = next(e for e in created["created_entities"] if e["kind"] == "function")
        for engine in ("interp", "jit"):
            self.assertEqual(6.0, self.executor.execute_function(self.workspace, self.document_id, 2,
                function["symbol_id"], [], engine)["result"])

        d2 = self.workspace.create_empty_document()["document_id"]
        created2 = self.workspace.create_numeric_function(d2, "EMPTY_RANGE", [], 1,
            locals=[{"name":"R","expression":num(9)}],
            body=[{"kind":"for","variable":"I","start":num(5),"end":num(2),
                   "body":[{"kind":"assign","target":{"kind":"local","name":"R"},
                     "expression":num(0)}]}], expression=local("R"))
        f2 = next(e for e in created2["created_entities"] if e["kind"] == "function")
        for engine in ("interp", "jit"):
            self.assertEqual(9.0, self.executor.execute_function(self.workspace, d2, 2,
                f2["symbol_id"], [], engine)["result"])

        d3 = self.workspace.create_empty_document()["document_id"]
        created3 = self.workspace.create_numeric_function(d3, "NEGATIVE_STEP", [], 1,
            locals=[{"name":"R","expression":num(0)}],
            body=[{"kind":"for","variable":"I","start":num(3),"end":num(-1),"step":num(-2),
                   "body":[{"kind":"assign","target":{"kind":"local","name":"R"},
                     "expression":{"kind":"binary","operator":"+","left":local("R"),"right":local("I")}}]}],
            expression=local("R"))
        f3 = next(e for e in created3["created_entities"] if e["kind"] == "function")
        for engine in ("interp", "jit"):
            self.assertEqual(3.0, self.executor.execute_function(self.workspace, d3, 2,
                f3["symbol_id"], [], engine)["result"])

    def test_runtime_iteration_guard_is_distinct_from_timeout(self):
        created = self.workspace.create_numeric_function(self.document_id, "STUCK", [], 1,
            body=[{"kind":"for","variable":"I","start":num(0),"end":num(1),
                   "body":[{"kind":"assign","target":{"kind":"local","name":"I"},
                            "expression":num(0)}]}])
        function = next(e for e in created["created_entities"] if e["kind"] == "function")
        for engine in ("interp", "jit"):
            with self.subTest(engine=engine), self.assertRaises(WorkspaceError) as caught:
                self.executor.execute_function(self.workspace, self.document_id, 2,
                    function["symbol_id"], [], engine)
            self.assertEqual("LOOP_LIMIT", caught.exception.code)

    def test_malformed_bwm3_loop_is_rejected_before_mir_lowering(self):
        # One function containing a FOR with a zero step. The record is
        # otherwise complete and bounded, so rejection exercises BWM3 parsing.
        payload = bytearray(b"BWM3" + struct.pack("<IIII", 3, 0, 0, 1))
        payload.extend(struct.pack("<IIII", 0, 0, 0, 1))  # function header
        payload.extend(struct.pack("<BBHI", 2, 0, 0, 0))  # FOR record
        for value in (0.0, 1.0, 0.0):
            payload.extend(b"\x01" + struct.pack("<d", value))
        payload.extend(struct.pack("<II", 1, 0))  # guard limit, empty body
        payload.extend(struct.pack("<II", 0, 0))  # invocation target and argc
        completed = subprocess.run([str(WORKER)], input=bytes(payload),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=2, check=False)
        self.assertEqual(0, completed.returncode, completed.stderr.decode("utf-8", "replace"))
        response = json.loads(completed.stdout)
        self.assertFalse(response["ok"])
        self.assertIn(response["code"], ("INVALID_PROJECTION", "MIR_BUILD_FAILED"))

    def test_bad_loop_and_nested_body_roll_back(self):
        before = self.workspace.render_document(self.document_id)
        for body in (
            [{"kind":"for","variable":"I","start":num(0),"end":num(2),"step":num(0),"body":[]}],
            [{"kind":"for","variable":"I","start":num(0),"end":num(10001),"body":[]}],
            [{"kind":"if","condition":{"kind":"binary","operator":"=","left":local("MISSING"),"right":num(1)},"then":[]}],
        ):
            with self.assertRaises(WorkspaceError):
                self.workspace.create_numeric_function(self.document_id, "BAD", ["X"], 1, body=body)
            self.assertEqual(before, self.workspace.render_document(self.document_id))
            self.assertEqual(1, self.workspace.get_revision(self.document_id))


if __name__ == "__main__":
    unittest.main()
