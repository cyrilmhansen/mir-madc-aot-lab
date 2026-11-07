from __future__ import annotations

import copy
import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("age_by_id_campaign", ROOT / "scripts" / "age-by-id-campaign.py")
campaign = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(campaign)


class AgeByIdSemanticReplayTests(unittest.TestCase):
    def setUp(self):
        from basic_workspace.model import Workspace
        self.workspace = Workspace()
        self.trace = campaign.Trace()
        self.document_id, self.aliases, self.seed = campaign.create_seed(self.workspace, self.trace)
        self.mission = campaign.make_mission()

    def test_candidate_preview_is_typed_and_nonmutating(self):
        from basic_workspace.model import WorkspaceError
        before_revision = self.workspace.get_revision(self.document_id)
        before = campaign.semantic_snapshot(self.workspace, self.document_id, self.aliases)
        gateway = campaign.MissionGateway(self.workspace, self.document_id, self.aliases,
                                          self.seed["projection"], self.mission, self.trace, "test")
        accepted = gateway.preview(self.aliases["people.age.205"], 48, before_revision)
        self.assertTrue(accepted["ok"])
        self.assertTrue(accepted["allowed_but_goal_value"])
        preview_event = next(x for x in reversed(self.trace.events) if x["event"] == "preview_accepted")
        candidate_target = campaign.find_statement(preview_event["candidate_semantic_snapshot"], "people.age.205")
        self.assertEqual(48.0, candidate_target["expression"]["value"])
        self.assertEqual(before_revision, self.workspace.get_revision(self.document_id))
        self.assertEqual(before, campaign.semantic_snapshot(self.workspace, self.document_id, self.aliases))
        self.assertEqual("MISSION_VALUE_RANGE", gateway.preview(
            self.aliases["people.age.205"], 131, before_revision)["code"])
        with self.assertRaises(WorkspaceError):
            self.workspace.apply_transaction(self.document_id, before_revision - 1, [])

    def test_commit_rechecks_stale_preview_without_extra_mutation(self):
        from basic_workspace.model import WorkspaceError
        from basic_workspace.projection import build_projection
        gateway = campaign.MissionGateway(self.workspace, self.document_id, self.aliases,
                                          self.seed["projection"], self.mission, self.trace, "test")
        preview = gateway.preview(self.aliases["people.age.205"], 47, 2)
        self.assertTrue(preview["ok"])
        # Simulate another authorized workspace transaction winning the race.
        self.workspace.edit_assignment_expression(self.document_id,
            self.aliases["people.age.101"], campaign.n(26), 2)
        live_revision = self.workspace.get_revision(self.document_id)
        rejected = gateway.commit(preview["transaction_id"])
        self.assertFalse(rejected["ok"])
        self.assertEqual("STALE_REVISION", rejected["code"])
        self.assertEqual(live_revision, self.workspace.get_revision(self.document_id))
        self.assertEqual(26.0, self.workspace.list_function_statements(
            self.document_id, self.aliases["age_by_id.function"])["items"][3]["expression_summary"] and
            float(self.workspace.list_function_statements(self.document_id,
                 self.aliases["age_by_id.function"])["items"][3]["expression_summary"]))

    def test_unknown_portable_handle_fails_replay(self):
        from basic_workspace.model import WorkspaceError
        stream = campaign.make_stream(self.seed, self.aliases, None)
        stream["operations"].append({"operation": "edit_assignment_expression",
            "target_handle": "people.age.missing", "expression": campaign.n(47)})
        with self.assertRaises(WorkspaceError) as error:
            campaign.replay_stream(stream, self.mission, campaign.Trace())
        self.assertEqual("REPLAY_HANDLE_MISSING", error.exception.code)

    def test_validation_response_is_revision_and_phase_bound(self):
        executor = campaign.MirExecutionService(timeout=10)
        gateway = campaign.MissionGateway(self.workspace, self.document_id, self.aliases,
            self.seed["projection"], self.mission, self.trace, "test")
        bridge = campaign.AgentGatewayTools(self.workspace, self.document_id, self.aliases,
            gateway, executor, self.trace)
        before = bridge.dispatch("run_lookup_checks", {"expected_revision": 2})
        self.assertTrue(before["reliable"])
        self.assertEqual(2, before["executed_revision"])
        self.assertEqual("pre-edit", before["phase"])
        self.assertEqual({"205": 42.0}, {"205": before["expected_results"]["205"]})
        self.assertEqual(before["observed_results"]["interp"], before["expected_results"])
        self.assertTrue(before["engines_agree"])
        self.assertFalse(before["mission_complete"])

        preview = gateway.preview(self.aliases["people.age.205"], 47, 2)
        self.assertTrue(preview["ok"])
        self.assertTrue(gateway.commit(preview["transaction_id"])["committed"])
        after = bridge.dispatch("run_lookup_checks", {"expected_revision": 3})
        self.assertTrue(after["reliable"])
        self.assertEqual(3, after["executed_revision"])
        self.assertEqual("post-edit", after["phase"])
        self.assertEqual(47.0, after["expected_results"]["205"])
        self.assertTrue(after["per_engine_matches"]["interp"])
        self.assertTrue(after["per_engine_matches"]["jit"])
        self.assertTrue(after["mission_complete"])

        stale = bridge.dispatch("run_lookup_checks", {"expected_revision": 2})
        self.assertFalse(stale["reliable"])
        self.assertEqual("STALE_VALIDATION_REVISION", stale["code"])
        self.assertIsNone(stale["executed_revision"])
        self.assertFalse(stale["mission_complete"])

    def test_recorded_real_agent_calls_match_dispatched_tool_events(self):
        import json
        root = ROOT / "results" / "semantic-replay" / "age-by-id"
        session = json.loads((root / "agent-session.json").read_text(encoding="utf-8"))
        events = [json.loads(line) for line in (root / "history.jsonl").read_text(encoding="utf-8").splitlines()]
        tool_events = [e for e in events if e["event"] == "model_tool_call"]
        result_events = [e for e in events if e["event"] == "tool_result"]
        recorded = [call for turn in session["transcript"] for call in turn.get("tool_calls", [])]
        self.assertEqual("completed", session["metadata"]["status"])
        self.assertEqual(session["metadata"]["tool_calls"], len(recorded))
        self.assertEqual(len(recorded), len(tool_events))
        self.assertEqual(len(recorded), len(result_events))
        for call, observed, result in zip(recorded, tool_events, result_events):
            self.assertEqual(call["id"], observed["tool_call_id"])
            self.assertEqual(call["name"], observed["tool"])
            self.assertEqual(call["arguments"], observed["arguments"])
            self.assertEqual(call["id"], result["tool_call_id"])
        first_prompt = session["transcript"][0]["request_messages"]
        self.assertNotIn("stmt_", json.dumps(first_prompt))

    def test_portable_stream_uses_handles_not_workspace_ids(self):
        stream = campaign.make_stream(self.seed, self.aliases, 47)
        encoded = str(stream)
        self.assertNotIn("sym_", encoded)
        self.assertNotIn("stmt_", encoded)
        self.assertEqual("people.age.205", stream["operations"][1]["target_handle"])

    def test_structural_comparison_detects_nested_semantic_changes(self):
        normalized = copy.deepcopy(self.seed["projection"])
        altered = copy.deepcopy(normalized)
        loop = next(x for x in altered["functions"][0]["statements"] if x["kind"] == "for")
        self.assertEqual("for", loop["kind"])
        loop["body"][0]["condition"]["children"][0]["value"] = "people.age"
        self.assertNotEqual(normalized, altered)
        self.assertNotEqual(campaign.binding_edges(normalized), campaign.binding_edges(altered))

    def test_logical_id_is_verified_through_initializer_map(self):
        self.assertEqual({0: 101, 1: 205, 2: 900}, self.seed["id_to_slot"])
        target = campaign.find_statement(self.seed["projection"], "people.age.205")
        self.assertEqual(1.0, target["target_index"]["value"])


if __name__ == "__main__":
    unittest.main()
