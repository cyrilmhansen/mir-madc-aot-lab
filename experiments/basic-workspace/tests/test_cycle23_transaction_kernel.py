"""Shared preview/commit lifecycle regressions across creation and maintenance."""
from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PI = ROOT / "pi-integration"
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(PI))

from basic_workspace.model import WorkspaceError  # noqa: E402
from cycle19_gateway import Cycle19Gateway  # noqa: E402
from transaction_kernel import SemanticTransactionKernel  # noqa: E402

SCHEMA_DIR = PI / "results/cycle21-reusable-maintenance/schema-preflight-02"


def clamp_request():
    ref = lambda: {"kind": "local_ref", "name": "X"}
    num = lambda value: {"kind": "number", "value": value}
    assign = lambda expr: {"kind": "assign", "target": {"kind": "result"}, "expression": expr}
    compare = lambda op, left, right: {"kind": "binary", "operator": op, "left": left, "right": right}
    return {"name": "CLAMP_SCORE", "parameters": ["X"], "body": [assign(ref()),
        {"kind": "if", "condition": compare("<", ref(), num(0)), "then": [assign(num(0))]},
        {"kind": "if", "condition": compare(">", ref(), num(100)), "then": [assign(num(100))]}]}


class SharedTransactionKernelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="atlas-cycle23-kernel-", dir="/var/tmp")
        self.addCleanup(self.tmp.cleanup)
        self.gateway = Cycle19Gateway(pathlib.Path(self.tmp.name))

    def test_function_creation_uses_kernel_preview_commit_and_duplicate_stale_rule(self):
        g = self.gateway
        result = g.handle("preview_create_function", {"expected_revision": 1, **clamp_request()}, "preview")
        self.assertTrue(result["ok"])
        self.assertEqual(g.ws.get_revision(g.doc), 1)
        record = g.transactions.get(result["transaction_id"])
        self.assertEqual(record["operation_kind"], "create_numeric_function")
        self.assertEqual(record["status"], "previewed")
        commit = g.handle("commit_preview", {"transaction_id": result["transaction_id"]}, "commit")
        self.assertTrue(commit["committed"])
        self.assertEqual(g.ws.get_revision(g.doc), 2)
        duplicate = g.handle("commit_preview", {"transaction_id": result["transaction_id"]}, "duplicate")
        self.assertEqual(duplicate["code"], "STALE_REVISION")
        self.assertEqual(g.ws.get_revision(g.doc), 2)

    def test_changed_candidate_is_rejected_without_authoritative_mutation(self):
        g = self.gateway
        preview = g.handle("preview_create_function", {"expected_revision": 1, **clamp_request()}, "preview")
        before = (g.ws.get_revision(g.doc), list(g.ws.documents[g.doc].tokens))
        with self.assertRaises(WorkspaceError) as caught:
            g.transactions.commit(preview["transaction_id"],
                lambda record, revision: (record["operations"], {"unexpected": True}, {}))
        self.assertEqual(caught.exception.code, "PREVIEW_CANDIDATE_CHANGED")
        self.assertEqual((g.ws.get_revision(g.doc), g.ws.documents[g.doc].tokens), before)

    def test_shared_lifecycle_has_bounded_adapter_surface(self):
        self.assertTrue(callable(SemanticTransactionKernel.preview))
        self.assertTrue(callable(SemanticTransactionKernel.commit))
        self.assertTrue(callable(SemanticTransactionKernel.clear))
        self.assertFalse(hasattr(SemanticTransactionKernel, "authorize"))
        self.assertFalse(hasattr(SemanticTransactionKernel, "validate_semantics"))

    @unittest.skipUnless(shutil.which("bun") and (SCHEMA_DIR / "tool-schemas.json").is_file(),
        "production TypeScript/JSONL preflight requires Bun and the captured Pi schema")
    def test_production_extension_dispatch_covers_creation_and_maintenance(self):
        with tempfile.TemporaryDirectory(prefix="atlas-cycle23-dispatch-", dir="/var/tmp") as temp:
            output = pathlib.Path(temp) / "preflight"
            completed = subprocess.run([sys.executable, str(PI / "cycle23_transaction_preflight.py"),
                "--output", str(output), "--maintenance-schema-dir", str(SCHEMA_DIR)],
                capture_output=True, text=True, timeout=180)
            self.assertEqual(completed.returncode, 0, completed.stderr[-2500:] + completed.stdout[-2500:])
            import json
            summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            self.assertFalse(summary["inference_performed"])
            self.assertEqual(summary["function_creation"]["committed_revision"], 2)
            self.assertTrue(summary["function_creation"]["fresh_replay"])
            self.assertTrue(summary["numeric_maintenance"]["cycle21_production_dispatch_checks"])
            self.assertEqual(summary["numeric_maintenance"]["mission_a_historical_proposals"], 4)


if __name__ == "__main__":
    unittest.main()
