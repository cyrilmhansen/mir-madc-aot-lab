import copy
import json
import sys
import unittest
from pathlib import Path

BASIC = Path(__file__).resolve().parents[1]
PI = BASIC / "pi-integration"
RESULTS = PI / "results"
sys.path.insert(0, str(BASIC))
sys.path.insert(0, str(PI))

from basic_workspace.model import Workspace, WorkspaceError
from basic_workspace.portable_replay import replay_constructive_stream
from basic_workspace.projection import build_projection, projection_semantics
from basic_workspace.mir_execution import MirExecutionService
from cycle20_gateway import senior


STREAM_PATH = RESULTS / "cycle30-post-extraction-maintenance/real-agent-01/constructive-operations.json"


def stream_data():
    return json.loads(STREAM_PATH.read_text(encoding="utf-8"))


def replay_prefix(count):
    stream = stream_data()
    ws = Workspace()
    doc = ws.create_empty_document("memory://cycle31/prefix.bas")["document_id"]
    result = replay_constructive_stream(ws, doc, stream["operations"][:count], expected_start_revision=1)
    raw = projection_semantics(build_projection(ws, doc, result.revision))
    return result, senior.normalized_state(raw, result.live_handles)


class PortableReplayTests(unittest.TestCase):
    def test_cycle30_stream_replays_all_six_families_and_identity_states(self):
        stream = stream_data()
        ws = Workspace()
        doc = ws.create_empty_document("memory://cycle31/full.bas")["document_id"]
        result = replay_constructive_stream(ws, doc, stream["operations"],
            expected_final_handles=stream["portable_handles"],
            expected_retired_handles=stream["retired_handles"], expected_start_revision=1)
        self.assertEqual(result.revision, 14)
        self.assertEqual(len(result.live_handles), 27)
        self.assertEqual(set(result.retired_handles), {"score_class.statement.0", "score_class.statement.1"})
        self.assertTrue(set(result.retired_handles).isdisjoint(result.live_handles))
        self.assertEqual({row["operation"] for row in result.operation_events}, {
            "create_numeric_function", "edit_numeric_literals", "insert_typed_if_block",
            "rename_symbol", "edit_typed_if_condition", "replace_typed_if_block"})
        self.assertEqual([(row["base_revision"], row["resulting_revision"]) for row in result.operation_events],
                         [(i, i + 1) for i in range(1, 14)])
        clamp_id = result.live_handles["clamp_score.function"]
        self.assertEqual(ws.documents[doc].symbols[clamp_id].name, "NORMALIZE_SCORE")
        self.assertEqual(len(ws.documents[doc].functions), 5)

    def test_revision_checkpoints_are_distinguished_by_historical_support(self):
        stream = stream_data()
        checkpoints = {9: (8, "cycle26-rename-validation"), 11: (10, "cycle28-semantic-snapshot"),
                       12: (11, "cycle29-semantic-snapshot"), 13: (12, "cycle29-identity-and-behavior-attestation"),
                       14: (13, "cycle30-semantic-snapshot")}
        observed = {}
        for revision, (count, evidence_kind) in checkpoints.items():
            result, normalized = replay_prefix(count)
            self.assertEqual(result.revision, revision)
            observed[str(revision)] = {"revision": revision, "operation_count": count,
                                       "evidence_kind": evidence_kind,
                                       "normalized_fingerprint": __import__("hashlib").sha256(
                                           json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}
        # Full semantic checkpoints are compared as objects. Revision 13 has
        # no saved normalized snapshot and is explicitly attested more narrowly.
        for rel, rev in [("cycle28-conditional-refactor/real-agent-01/history.jsonl", 11),
                         ("cycle29-function-extraction/real-agent-01/history.jsonl", 12),
                         ("cycle30-post-extraction-maintenance/real-agent-01/history.jsonl", 14)]:
            rows = [json.loads(line) for line in (RESULTS / rel).read_text().splitlines() if line.strip()]
            snapshot = next(row["semantic_snapshot"] for row in rows if row.get("event") == "transaction_committed" and row.get("resulting_revision") == rev)
            _result, normalized = replay_prefix(rev - 1)
            self.assertEqual(normalized, snapshot)
        c29 = [json.loads(line) for line in (RESULTS / "cycle29-function-extraction/real-agent-01/history.jsonl").read_text().splitlines() if line.strip()]
        commit13 = next(row for row in c29 if row.get("event") == "transaction_committed" and row.get("resulting_revision") == 13)
        self.assertEqual(commit13["retired_statement_handles"], ["score_class.statement.0", "score_class.statement.1"])
        self.assertIn("13", observed)

    def test_cycle30_behavior_matches_saved_validation_with_both_mir_engines(self):
        stream = stream_data(); ws = Workspace(); doc = ws.create_empty_document("memory://cycle31/oracle.bas")["document_id"]
        replay = replay_constructive_stream(ws, doc, stream["operations"], expected_final_handles=stream["portable_handles"],
            expected_retired_handles=stream["retired_handles"], expected_start_revision=1)
        validation = json.loads((RESULTS / "cycle30-post-extraction-maintenance/real-agent-01/validation.json").read_text())
        executor = MirExecutionService(timeout=20)
        inputs = [-100, -1, 0, 1, 19, 20, 21, 24, 25, 26, 39, 40, 44, 45, 49, 50, 51, 60, 100, 200]
        observed = {engine: {} for engine in ("interp", "jit")}
        for engine in observed:
            for x in inputs:
                row = {}
                for handle in replay.live_handles:
                    if handle.endswith(".function"):
                        name = ws.documents[doc].symbols[replay.live_handles[handle]].name
                        row[name.casefold()] = executor.execute_function(ws, doc, replay.revision, replay.live_handles[handle], [x], engine)["result"]
                observed[engine][str(x)] = row
        self.assertEqual(observed, validation["observed_results"])
        self.assertEqual(observed["interp"], observed["jit"])

    def test_unknown_operation_ordering_and_unknown_call_fail_precisely(self):
        stream = stream_data()
        for operations, code in [([{"operation": "plugin_magic"}], "REPLAY_OPERATION_UNSUPPORTED"),
                                 ([stream["operations"][1]], "REPLAY_HANDLE_MISSING")]:
            ws = Workspace(); doc = ws.create_empty_document("memory://cycle31/negative.bas")["document_id"]
            with self.assertRaises(WorkspaceError) as caught:
                replay_constructive_stream(ws, doc, operations)
            self.assertEqual(caught.exception.code, code)
        bad = copy.deepcopy(stream["operations"][:2])
        bad[1]["arguments"]["body"][0]["condition"]["left"]["function_handle"] = "normalize_score.function"
        ws = Workspace(); doc = ws.create_empty_document("memory://cycle31/unknown-call.bas")["document_id"]
        with self.assertRaises(WorkspaceError) as caught:
            replay_constructive_stream(ws, doc, bad)
        self.assertEqual(caught.exception.code, "REPLAY_HANDLE_MISSING")

    def test_wrong_start_revision_missing_handle_and_bad_signature_are_rejected(self):
        stream = stream_data()
        ws = Workspace(); doc = ws.create_empty_document("memory://cycle31/stale-start.bas")["document_id"]
        with self.assertRaises(WorkspaceError) as caught:
            replay_constructive_stream(ws, doc, stream["operations"], expected_start_revision=2)
        self.assertEqual(caught.exception.code, "REPLAY_START_REVISION")
        bad = copy.deepcopy(stream["operations"][:2])
        call = bad[1]["arguments"]["body"][0]["condition"]["left"]
        call["function_handle"] = "clamp_score.function"
        call["arguments"] = []
        ws = Workspace(); doc = ws.create_empty_document("memory://cycle31/bad-arity.bas")["document_id"]
        with self.assertRaises(WorkspaceError) as caught:
            replay_constructive_stream(ws, doc, bad)
        self.assertEqual(caught.exception.code, "REPLAY_SIGNATURE_MISMATCH")

    def test_tampered_block_fingerprint_is_not_reported_as_replayed(self):
        stream = stream_data(); bad = copy.deepcopy(stream["operations"])
        bad[-2]["expected_block_fingerprint"] = "0" * 64
        ws = Workspace(); doc = ws.create_empty_document("memory://cycle31/bad-fingerprint.bas")["document_id"]
        with self.assertRaises(WorkspaceError) as caught:
            replay_constructive_stream(ws, doc, bad)
        self.assertEqual(caught.exception.code, "REPLAY_BLOCK_MISMATCH")

    def test_retired_handles_are_never_reinterpreted_or_recycled(self):
        stream = stream_data(); operations = copy.deepcopy(stream["operations"])
        old = operations[-2]
        reused = copy.deepcopy(old); reused["created_statement_handle"] = "score_class.statement.0"
        ws = Workspace(); doc = ws.create_empty_document("memory://cycle31/reused.bas")["document_id"]
        with self.assertRaises(WorkspaceError) as caught:
            replay_constructive_stream(ws, doc, operations[:-2] + [reused, operations[-1]])
        self.assertEqual(caught.exception.code, "REPLAY_IDENTITY_REUSE")
        after_retirement = copy.deepcopy(operations[-1])
        after_retirement["operation"] = "create_numeric_function"
        after_retirement.pop("mission_id", None)
        after_retirement.pop("function_handle", None)
        after_retirement.pop("edits", None)
        after_retirement["portable_handle"] = "extra.function"
        after_retirement["arguments"] = {"name": "EXTRA", "parameters": ["X"], "body": [
            {"kind": "if", "condition": {"kind": "binary", "operator": "=",
             "left": {"kind": "call", "function_handle": "score_class.statement.0",
                      "arguments": [{"kind": "local_ref", "name": "X"}]},
             "right": {"kind": "number", "value": 1}},
             "then": [{"kind": "assign", "target": {"kind": "result"}, "expression": {"kind": "number", "value": 1}}]}]}
        ws = Workspace(); doc = ws.create_empty_document("memory://cycle31/retired-use.bas")["document_id"]
        with self.assertRaises(WorkspaceError) as caught:
            replay_constructive_stream(ws, doc, operations + [after_retirement])
        self.assertEqual(caught.exception.code, "REPLAY_HANDLE_RETIRED")

    def test_tampered_retirement_and_stale_literal_target_fail(self):
        stream = stream_data(); bad = copy.deepcopy(stream["operations"])
        bad[-2]["expected_removed_statement_handles"] = ["score_class.statement.2"]
        ws = Workspace(); doc = ws.create_empty_document("memory://cycle31/bad-retirement.bas")["document_id"]
        with self.assertRaises(WorkspaceError) as caught:
            replay_constructive_stream(ws, doc, bad)
        self.assertEqual(caught.exception.code, "REPLAY_RETIREMENT_MISMATCH")
        bad = copy.deepcopy(stream["operations"]); bad[-1]["edits"][0]["expected_value"] = 21
        ws = Workspace(); doc = ws.create_empty_document("memory://cycle31/bad-literal.bas")["document_id"]
        with self.assertRaises(WorkspaceError):
            replay_constructive_stream(ws, doc, bad)


if __name__ == "__main__":
    unittest.main()
