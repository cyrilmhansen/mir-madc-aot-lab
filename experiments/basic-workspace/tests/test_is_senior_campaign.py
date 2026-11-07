from __future__ import annotations

import copy
import importlib.util
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "is_senior_campaign", ROOT / "scripts" / "is-senior-campaign.py")
campaign = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(campaign)


class IsSeniorCampaignTests(unittest.TestCase):
    def setUp(self):
        self.ws = campaign.Workspace()
        self.trace = campaign._cycle12.Trace()
        self.doc, self.aliases, self.seed = campaign._cycle12.create_seed(self.ws, self.trace)
        self.revision = self.ws.get_revision(self.doc)
        self.base = campaign.normalized_state(
            campaign.projection_semantics(campaign.build_projection(self.ws, self.doc, self.revision)),
            self.aliases)
        self.gateway = campaign.SeniorMissionGateway(self.ws, self.doc, self.aliases,
            self.base, campaign.make_mission(), self.trace, "test")
        self.gateway.discover_functions()

    def test_composes_discovered_function_and_replays_with_remapped_ids(self):
        preview = self.gateway.preview(campaign.senior_operation(), self.revision,
                                       "age_by_id.function")
        self.assertTrue(preview["ok"], preview)
        event = next(x for x in reversed(self.trace.events) if x["event"] == "preview_accepted")
        self.assertIn("age_by_id.function", campaign.candidate_call_edges(event["candidate_semantic_snapshot"])[0].values())
        committed = self.gateway.commit(preview["transaction_id"])
        self.assertTrue(committed["committed"])
        observed = campaign.validate_mission(self.ws, self.doc, self.gateway,
                                             self.ws.get_revision(self.doc))
        self.assertTrue(observed["mission_complete"], observed)
        self.assertEqual("age_by_id.function", observed["call_edges"][0]["callee"])

        stream = campaign.constructive_stream(self.seed, self.gateway.committed_request,
                                              self.gateway.aliases)
        serialized = json.dumps(stream)
        for opaque_id in self.gateway.aliases.values():
            self.assertNotIn(opaque_id, serialized)
        fresh_trace = campaign._cycle12.Trace()
        fresh, doc, aliases, replay = campaign.replay_stream(stream, fresh_trace)
        self.assertNotEqual(self.aliases["age_by_id.function"], aliases["age_by_id.function"])
        self.assertEqual(self.gateway.committed_snapshot, replay["normalized"])
        self.assertEqual(campaign.execute_program(self.ws, self.doc, 3, self.gateway.aliases),
                         campaign.execute_program(fresh, doc, replay["revision"], aliases))
        bad_stream = copy.deepcopy(stream)
        bad_stream["operations"][1]["callee_handle"] = "people.age"
        with self.assertRaises(campaign.WorkspaceError) as error:
            campaign.replay_stream(bad_stream, campaign._cycle12.Trace())
        self.assertEqual("REPLAY_HANDLE_MISSING", error.exception.code)

    def test_policy_allows_threshold_variant_but_oracle_rejects_wrong_behavior(self):
        preview = self.gateway.preview(campaign.senior_operation(threshold=49), self.revision,
                                       "age_by_id.function")
        self.assertTrue(preview["ok"], preview)
        self.assertTrue(self.gateway.commit(preview["transaction_id"])["committed"])
        result = campaign.validate_mission(self.ws, self.doc, self.gateway,
                                           self.ws.get_revision(self.doc))
        self.assertTrue(result["reliable"])
        self.assertFalse(result["mission_complete"])
        self.assertFalse(result["boundary_oracle"]["passed"])
        self.assertEqual(1.0, result["boundary_oracle"]["cases"]["49"]["observed"]["interp"]["senior_205"])

    def test_unknown_wrong_and_incompatible_calls_are_rejected_without_mutation(self):
        before = campaign.normalized_state(campaign.projection_semantics(
            campaign.build_projection(self.ws, self.doc, self.revision)), self.aliases)
        attempts = [
            (campaign.senior_operation(callee_handle="unknown"), "unknown", "UNKNOWN_PORTABLE_FUNCTION"),
            (campaign.senior_operation(callee_handle="people.id"), "age_by_id.function", "UNKNOWN_PORTABLE_FUNCTION"),
        ]
        bad_arity = campaign.senior_operation()
        bad_arity["body"][1]["condition"]["left"]["arguments"].append(campaign.local("ID"))
        attempts.append((bad_arity, "age_by_id.function", "MISSION_CALL_ARITY"))
        for request, handle, code in attempts:
            rejected = self.gateway.preview(request, self.revision, handle)
            self.assertFalse(rejected["ok"])
            self.assertEqual(code, rejected["code"])
            self.assertEqual(self.revision, self.ws.get_revision(self.doc))
            after = campaign.normalized_state(campaign.projection_semantics(
                campaign.build_projection(self.ws, self.doc, self.revision)), self.aliases)
            self.assertEqual(before, after)

    def test_stale_validation_and_contradictory_observation_never_claim_success(self):
        stale = campaign.validation_envelope(requested_revision=3, workspace_revision=2,
            observed={"interp": {}, "jit": {}}, expected={}, boundary={"passed": True},
            committed=True, base_unchanged=True, callee_bound=True)
        self.assertFalse(stale["reliable"])
        self.assertIsNone(stale["executed_revision"])
        self.assertFalse(stale["mission_complete"])
        contradictory = campaign.validation_envelope(requested_revision=2, workspace_revision=2,
            observed={"interp": {"x": 1}, "jit": {"x": 2}}, expected={"x": 1},
            boundary={"passed": True}, committed=True, base_unchanged=True, callee_bound=True)
        self.assertTrue(contradictory["reliable"])
        self.assertFalse(contradictory["engines_agree"])
        self.assertFalse(contradictory["mission_complete"])

    def test_scripted_controls_reject_without_revision_or_behavior_change(self):
        outcome = campaign.run_negative_controls(self.ws, self.doc, self.gateway, self.aliases, self.trace)
        self.assertTrue(outcome["passed"], outcome)
        self.assertEqual(self.revision, self.ws.get_revision(self.doc))

    def test_visual_report_uses_committed_composition_and_labels_scripted_evidence(self):
        preview = self.gateway.preview(campaign.senior_operation(), self.revision,
                                       "age_by_id.function")
        self.gateway.commit(preview["transaction_id"])
        event = {"sequence": 1, "event": "session_started", "campaign_kind": "scripted",
                 "campaign": "test", "objective": "compose function"}
        committed = next(x for x in reversed(self.trace.events) if x["event"] == "transaction_committed")
        committed["phase"] = "scripted-demo"
        events = [event, committed, {"sequence": 3, "event": "program_validated",
                 "phase": "host-post-model", "validation": {"mission_complete": True}},
                 {"sequence": 4, "event": "replay_completed", "success": True}]
        render_spec = importlib.util.spec_from_file_location(
            "semantic_replay_renderer", ROOT / "scripts" / "render-semantic-replay.py")
        renderer = importlib.util.module_from_spec(render_spec)
        assert render_spec.loader is not None
        render_spec.loader.exec_module(renderer)
        html_report = renderer.build_html(events, campaign.make_profile(), campaign.make_mission())
        svg_report = renderer.overview_svg(events)
        self.assertIn("IS_SENIOR → age_by_id.function", html_report)
        self.assertIn("scripted mechanics; no model actions", html_report)
        self.assertIn("Function dependencies from committed semantic state", svg_report)
        self.assertIn("PERSON_ID", svg_report)
        self.assertIn("PERSON_AGE", svg_report)


if __name__ == "__main__":
    unittest.main()
