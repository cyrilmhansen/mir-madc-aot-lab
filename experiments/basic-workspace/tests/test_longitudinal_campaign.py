import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cycle = load("longitudinal_campaign_tests", "longitudinal-campaign.py")


class LongitudinalCampaignTests(unittest.TestCase):
    def test_age_edit_mission_goal_is_configurable_to_55(self):
        age = cycle.age.make_mission(55)
        self.assertEqual(55.0, age["functional_goal"]["new_age"])
        self.assertIn("to 55", age["objective"])
        self.assertEqual(55.0, age["required_post_edit_validations"][0]["expected"])

    def test_generic_mission_gateway_creates_adult_caller_without_changing_existing_functions(self):
        ws = cycle.Workspace()
        trace = cycle.age.Trace()
        doc, aliases, seed = cycle.age.create_seed(ws, trace)
        senior_request = {"name": "IS_SENIOR", "parameters": ["ID"], "body": [
            {"kind": "assign", "target": {"kind": "result"}, "expression": {"kind": "number", "value": 0}},
            {"kind": "if", "condition": {"kind": "binary", "operator": ">=",
                "left": {"kind": "call", "function_handle": "age_by_id.function",
                         "arguments": [{"kind": "local_ref", "name": "ID"}]},
                "right": {"kind": "number", "value": 50}},
             "then": [{"kind": "assign", "target": {"kind": "result"}, "expression": {"kind": "number", "value": 1}}]}]}
        resolved = cycle.senior.resolve_function_handles(senior_request, aliases, {"age_by_id.function"})
        result = ws.apply_transaction(doc, seed["revision"], [{"operation": "create_numeric_function", **resolved}])
        raw = cycle.senior.projection_semantics(cycle.senior.build_projection(ws, doc, result["revision"]))
        aliases = cycle.senior.aliases_for_new_function(raw, aliases, "IS_SENIOR", "is_senior.function")
        age_edit = ws.edit_assignment_expression(doc, aliases["people.age.205"],
                                                {"kind": "number", "value": 55}, result["revision"])
        raw = cycle.senior.projection_semantics(cycle.senior.build_projection(ws, doc, age_edit["revision"]))
        before = cycle.senior.normalized_state(raw, aliases)
        mission = cycle.make_adult_mission()
        gateway = cycle.senior.SeniorMissionGateway(ws, doc, aliases, before, mission, trace,
            "mission-3-test", function_name="IS_ADULT", function_handle="is_adult.function")
        self.assertEqual(1, len(gateway.discover_functions()["functions"]))
        request = {"name": "IS_ADULT", "parameters": ["ID"], "body": [
            {"kind": "assign", "target": {"kind": "result"}, "expression": {"kind": "number", "value": 0}},
            {"kind": "if", "condition": {"kind": "binary", "operator": ">=",
                "left": {"kind": "call", "function_handle": "age_by_id.function",
                         "arguments": [{"kind": "local_ref", "name": "ID"}]},
                "right": {"kind": "number", "value": 18}},
             "then": [{"kind": "assign", "target": {"kind": "result"}, "expression": {"kind": "number", "value": 1}}]}]}
        preview = gateway.preview(request, ws.get_revision(doc), "age_by_id.function")
        self.assertTrue(preview["ok"])
        committed = gateway.commit(preview["transaction_id"])
        self.assertTrue(committed["committed"])
        current = cycle.senior.normalized_state(cycle.senior.projection_semantics(
            cycle.senior.build_projection(ws, doc, ws.get_revision(doc))), gateway.aliases)
        self.assertEqual(before["functions"], [f for f in current["functions"] if f["handle"] != "is_adult.function"])
        check = cycle.adult_validator(ws, doc, gateway, ws.get_revision(doc))
        self.assertTrue(check["mission_complete"])

    def test_checkpoint_guards_revision_profile_bindings_mission_and_fingerprint(self):
        ws = cycle.Workspace(); trace = cycle.age.Trace()
        doc, aliases, _ = cycle.age.create_seed(ws, trace)
        normalized = cycle.senior.normalized_state(cycle.senior.projection_semantics(
            cycle.senior.build_projection(ws, doc, ws.get_revision(doc))), aliases)
        ws._cycle14_aliases = aliases
        checkpoint = cycle.make_checkpoint(ws, doc, aliases, [], {}, cycle.make_adult_mission())
        self.assertTrue(cycle.validate_checkpoint(checkpoint, ws, doc, cycle.PROFILE_ID, aliases)["ok"])
        cases = []
        stale = {**checkpoint, "document": {**checkpoint["document"], "revision": 0}}
        cases.append((stale, cycle.PROFILE_ID, True, "STALE_CHECKPOINT_REVISION"))
        profile = {**checkpoint, "execution_profile_id": "other"}
        cases.append((profile, cycle.PROFILE_ID, True, "CHECKPOINT_PROFILE_MISMATCH"))
        no_mission = {**checkpoint, "active_mission": None}
        cases.append((no_mission, cycle.PROFILE_ID, False, "CHECKPOINT_MISSION_MISSING"))
        fingerprint = {**checkpoint, "semantic_fingerprint": "f" * 64}
        cases.append((fingerprint, cycle.PROFILE_ID, True, "CHECKPOINT_FINGERPRINT_MISMATCH"))
        missing = {**checkpoint, "verified_facts": {**checkpoint["verified_facts"],
            "functions": [x for x in checkpoint["verified_facts"]["functions"] if x["handle"] != "age_by_id.function"]}}
        cases.append((missing, cycle.PROFILE_ID, True, "CHECKPOINT_FUNCTION_MISSING"))
        unknown = {**checkpoint, "verified_facts": {**checkpoint["verified_facts"],
            "dependencies": [{"caller":"age_by_id.function","callee":"ghost.function"}]}}
        cases.append((unknown, cycle.PROFILE_ID, True, "CHECKPOINT_PORTABLE_HANDLE_UNKNOWN"))
        for candidate, profile_id, has_mission, code in cases:
            with self.subTest(code=code):
                result = cycle.validate_checkpoint(candidate, ws, doc, profile_id, aliases, has_mission)
                self.assertFalse(result["ok"])
                self.assertEqual(code, result["code"])
                self.assertEqual(2, ws.get_revision(doc))
        self.assertEqual(normalized, cycle.senior.normalized_state(cycle.senior.projection_semantics(
            cycle.senior.build_projection(ws, doc, ws.get_revision(doc))), aliases))


if __name__ == "__main__":
    unittest.main()
