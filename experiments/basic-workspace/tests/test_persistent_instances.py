from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from basic_workspace.mir_execution import PersistentExecutionService
from basic_workspace.model import Workspace, WorkspaceError


WORKER = ROOT / "native" / "build" / "mir-worker"


@unittest.skipUnless(WORKER.is_file(), "build the MIR worker first")
class PersistentInstanceTests(unittest.TestCase):
    def test_ten_calls_reuse_one_compiled_mir_module(self):
        workspace = Workspace()
        document = workspace.create_empty_document()["document_id"]
        created = workspace.create_numeric_function(document, "DOUBLE", ["X"], 1,
            expression={"kind": "binary", "operator": "*",
                "left": {"kind": "local_ref", "name": "X"},
                "right": {"kind": "number", "value": 2}})
        revision = created["revision"]
        function_id = next(x["symbol_id"] for x in created["created_entities"]
                           if x["kind"] == "function")
        for engine in ("interp", "jit"):
            service = PersistentExecutionService(timeout=5)
            try:
                module = service.prepare_module(workspace, document, revision, engine)
                instance = service.create_instance(module["module_id"])
                instance_id = instance["instance_id"]
                for n in range(10):
                    result = service.call_instance_function(instance_id, function_id, [n], revision)
                    self.assertEqual(n * 2.0, result["result"])
                info = service.get_instance_info(instance_id)
                self.assertEqual(10, info["call_count"])
                self.assertEqual(1, info["mir_build_count"])
                self.assertEqual(1, info["mir_link_count"])
                service.destroy_instance(instance_id)
                self.assertEqual("INSTANCE_NOT_FOUND", self._call_dead(service, instance_id, function_id).code)
                service.release_module(module["module_id"])
            finally:
                service.close()

    def test_failed_initializer_destroys_instance_without_publishing_it(self):
        workspace = Workspace()
        document = workspace.create_empty_document()["document_id"]
        revision = workspace.declare_shared_numeric_array(document, "CELLS", 0, 1)["revision"]
        array_id = next(x["symbol_id"] for x in workspace.list_symbols(document)
                        if x["kind"] == "array")
        created = workspace.create_numeric_function(document, "INIT_BAD", [], revision,
            expression={"kind": "number", "value": 0},
            body=[{"kind": "array_assign",
                   "array_ref": {"kind": "symbol_ref", "symbol_id": array_id},
                   "index": {"kind": "number", "value": 1},
                   "expression": {"kind": "number", "value": 9}}])
        revision = created["revision"]
        initializer_id = next(x["symbol_id"] for x in created["created_entities"]
                              if x["kind"] == "function")
        service = PersistentExecutionService(timeout=5)
        try:
            module = service.prepare_module(workspace, document, revision)
            with self.assertRaises(WorkspaceError) as raised:
                service.create_instance(module["module_id"], initializer_id)
            self.assertEqual("INSTANCE_INITIALIZATION_FAILED", raised.exception.code)
            self.assertEqual([], list(service.instances))
            service.release_module(module["module_id"])
        finally:
            service.close()

    def test_worker_exit_invalidates_instance_without_restart(self):
        workspace = Workspace()
        document = workspace.create_empty_document()["document_id"]
        created = workspace.create_numeric_function(document, "DOUBLE", ["X"], 1,
            expression={"kind": "binary", "operator": "*",
                "left": {"kind": "local_ref", "name": "X"},
                "right": {"kind": "number", "value": 2}})
        function_id = next(x["symbol_id"] for x in created["created_entities"]
                           if x["kind"] == "function")
        service = PersistentExecutionService(timeout=5)
        try:
            module = service.prepare_module(workspace, document, created["revision"])
            instance = service.create_instance(module["module_id"])
            iid = instance["instance_id"]
            service.instances[iid].proc.kill()
            service.instances[iid].proc.wait()
            self.assertEqual("dead", service.get_instance_info(iid)["status"])
            with self.assertRaises(WorkspaceError) as raised:
                service.call_instance_function(iid, function_id, [3], created["revision"])
            self.assertEqual("INSTANCE_INVALID", raised.exception.code)
            self.assertEqual("dead", service.get_instance_info(iid)["status"])
            service.destroy_instance(iid)
            service.release_module(module["module_id"])
        finally:
            service.close()

    def test_shared_state_isolation_initialization_and_revision_binding(self):
        completed = subprocess.run([sys.executable,
            str(ROOT / "scripts" / "demo-persistent-address-book.py")],
            cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=20, check=False)
        self.assertEqual(0, completed.returncode, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(7, result["revision"])
        for engine in ("interp", "jit"):
            row = result["engines"][engine]
            self.assertEqual(42.0, row["initial_A"])
            self.assertEqual(42.0, row["initial_B"])
            self.assertEqual(1.0, row["set_A"])
            self.assertEqual(47.0, row["after_A"])
            self.assertEqual(42.0, row["after_B"])
            self.assertEqual(42.0, row["new_instance_C"])
            self.assertEqual(1, row["build_count"])
            self.assertEqual(1, row["link_count"])

    @staticmethod
    def _call_dead(service, instance_id, function_id):
        try:
            service.call_instance_function(instance_id, function_id, [1])
        except WorkspaceError as exc:
            return exc
        raise AssertionError("destroyed instance was callable")


if __name__ == "__main__":
    unittest.main()
