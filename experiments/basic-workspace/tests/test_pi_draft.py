import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location("cycle17_pi_gateway",ROOT/"pi-integration/gateway.py")
MOD=importlib.util.module_from_spec(SPEC);assert SPEC and SPEC.loader;sys.modules[SPEC.name]=MOD;SPEC.loader.exec_module(MOD)


def construction_ops():
    return [
        {"op_id":"op_number_18","kind":"define_number","handle":"n18","value":18},
        {"op_id":"op_param","kind":"define_parameter_ref","handle":"id_arg","name":"ID"},
        {"op_id":"op_call","kind":"define_function_call","handle":"age_call","function_handle":"age_by_id.function","arguments":["id_arg"]},
        {"op_id":"op_compare","kind":"define_binary_expression","handle":"adult_test","operator":">=","left":"age_call","right":"n18"},
        {"op_id":"op_yes","kind":"define_number","handle":"one","value":1},
        {"op_id":"op_no","kind":"define_number","handle":"zero","value":0},
        {"op_id":"op_if","kind":"append_if_block","handle":"adult_if","block":"root","condition":"adult_test","then_block":"then_body","else_block":"else_body"},
        {"op_id":"op_then","kind":"append_result_assignment","handle":"then_result","block":"then_body","expression":"one"},
        {"op_id":"op_else","kind":"append_result_assignment","handle":"else_result","block":"else_body","expression":"zero"},
    ]


class PiDraftTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="atlas-pi-draft-test-",dir="/var/tmp")
        self.output=Path(self.temp.name)
        self.service=MOD.Cycle16Gateway(self.output,"incremental")
        self.original=self.service.ws.render_document(self.service.doc)
        self.service.handle("discover_functions",{},"discover")
        self.started=self.service.handle("begin_function_draft",{"expected_revision":4,"name":"IS_ADULT",
            "parameters":["ID"],"callee_handle":"age_by_id.function"},"begin")
        self.draft_id=self.started["draft_id"]
    def tearDown(self):self.temp.cleanup()
    def apply(self,operations,rev=0):
        return self.service.handle("apply_draft_operations",{"draft_id":self.draft_id,
            "expected_draft_revision":rev,"operations":operations},"apply")

    def test_incremental_candidate_previews_then_commits_atomically_and_validates(self):
        applied=self.apply(construction_ops())
        self.assertTrue(applied["ok"]);self.assertEqual(applied["draft_revision"],9)
        self.assertEqual(self.service.ws.get_revision(self.service.doc),4)
        self.assertEqual(self.service.ws.render_document(self.service.doc),self.original)
        inspected=self.service.handle("inspect_function_draft",{"draft_id":self.draft_id},"inspect-draft")
        self.assertEqual(inspected["operation_count"],9)
        self.assertEqual(inspected["body"][0]["kind"],"if")
        preview=self.service.handle("preview_function_draft",{"draft_id":self.draft_id,
            "expected_revision":4,"expected_draft_revision":9},"preview-draft")
        self.assertTrue(preview["ok"]);self.assertTrue(preview["candidate_is_preview_only"])
        self.assertEqual(self.service.ws.get_revision(self.service.doc),4)
        committed=self.service.handle("commit_preview",{"transaction_id":preview["transaction_id"]},"commit")
        self.assertTrue(committed["committed"]);self.assertEqual(committed["revision"],5)
        self.assertTrue(self.service.draft_protocol.get(self.draft_id).committed)
        self.assertTrue((self.output/"draft-operation-history.json").is_file())
        self.assertEqual(len(json.loads((self.output/"draft-operation-history.json").read_text())["operations"]),9)
        result=self.service.handle("validate_mission",{"expected_revision":5},"host-validate")
        self.assertTrue(result["mission_complete"]);self.assertTrue(result["engines_agree"])
        self.assertTrue(result["replay"]["passed"])

    def test_ordered_batch_publishes_distinct_draft_frames_without_advancing_committed_code(self):
        applied=self.apply(construction_ops())
        self.assertTrue(applied["ok"])
        events=[json.loads(line) for line in (self.output/"visual-events.jsonl").read_text().splitlines() if line]
        steps=[event for event in events if event.get("title","").startswith("Draft step ")]
        self.assertEqual(len(steps),9)
        self.assertEqual([event["outcome"]["draft_revision"] for event in steps],list(range(1,10)))
        self.assertTrue(all(event["revision"]==4 and event["outcome"]["committed"] is False for event in steps))
        self.assertTrue(all("one genuine Pi batch" in event["provenance"] for event in steps))
        self.assertEqual(self.service.ws.get_revision(self.service.doc),4)
        self.assertEqual(self.service.ws.render_document(self.service.doc),self.original)

    def test_unknown_draft_and_unknown_expression_are_diagnostic_and_non_mutating(self):
        missing=self.service.handle("apply_draft_operations",{"draft_id":"missing","expected_draft_revision":0,
            "operations":[construction_ops()[0]]},"missing")
        self.assertEqual(missing["code"],"DRAFT_NOT_FOUND")
        result=self.apply([{"op_id":"bad_ref","kind":"append_result_assignment","handle":"stmt",
            "block":"root","expression":"not_defined"}])
        self.assertEqual(result["code"],"UNKNOWN_EXPRESSION_HANDLE")
        self.assertEqual(result["operation_id"],"bad_ref")
        self.assertEqual(result["draft_revision"],0);self.assertFalse(result["draft_changed"])
        self.assertEqual(self.service.ws.get_revision(self.service.doc),4)

    def test_wrong_handle_type_invalid_parent_and_operation_order_are_rejected(self):
        partial=self.apply([construction_ops()[0],{"op_id":"wrong_type","kind":"append_result_assignment",
            "handle":"stmt","block":"root","expression":"root"}])
        self.assertEqual(partial["code"],"DRAFT_TYPE_ERROR")
        self.assertEqual(partial["draft_revision"],0)
        self.assertEqual(self.service.draft_protocol.inspect(self.draft_id)["expression_handles"],[])
        parent=self.apply([{"op_id":"parent","kind":"append_result_assignment","handle":"s",
            "block":"missing_block","expression":"missing_expr"}])
        self.assertEqual(parent["code"],"INVALID_PARENT_BLOCK")
        order=self.apply([{"op_id":"first","kind":"define_binary_expression","handle":"b",
            "operator":"+","left":"later","right":"later"}])
        self.assertEqual(order["code"],"UNKNOWN_EXPRESSION_HANDLE")
        self.assertEqual(self.service.ws.get_revision(self.service.doc),4)

    def test_duplicate_operation_id_and_partial_batch_failure_roll_back_entire_batch(self):
        batch=[{"op_id":"same","kind":"define_number","handle":"first","value":1},
               {"op_id":"same","kind":"define_number","handle":"second","value":2}]
        result=self.apply(batch)
        self.assertEqual(result["code"],"DUPLICATE_OPERATION_ID")
        self.assertEqual(result["draft_revision"],0)
        partial=self.apply([construction_ops()[0],{"op_id":"later_bad","kind":"define_binary_expression",
            "handle":"bad","operator":"^","left":"n18","right":"n18"}])
        self.assertEqual(partial["code"],"INVALID_OPERATOR")
        self.assertEqual(self.service.draft_protocol.inspect(self.draft_id)["expression_handles"],[])
        self.assertFalse(partial["authoritative_workspace_changed"])

    def test_stale_draft_revision_and_workspace_revision_are_rejected(self):
        stale_draft=self.apply([construction_ops()[0]],rev=1)
        self.assertEqual(stale_draft["code"],"STALE_DRAFT_REVISION")
        self.assertEqual(self.service.draft_protocol.get(self.draft_id).revision,0)
        self.apply([construction_ops()[0]])
        stale_base=self.service.handle("preview_function_draft",{"draft_id":self.draft_id,
            "expected_revision":3,"expected_draft_revision":1},"stale-base")
        self.assertEqual(stale_base["code"],"STALE_WORKSPACE_REVISION")
        self.assertEqual(self.service.ws.get_revision(self.service.doc),4)

    def test_external_workspace_commit_invalidates_draft_preview(self):
        self.apply([construction_ops()[0]])
        operation={"operation":"edit_assignment_expression",
            "statement_id":self.service.aliases["people.age.205"],
            "expression":{"kind":"number","value":55.0}}
        external=self.service.ws.apply_transaction(self.service.doc,4,[operation])
        self.assertEqual(external["revision"],5)
        stale=self.service.handle("preview_function_draft",{"draft_id":self.draft_id,
            "expected_revision":4,"expected_draft_revision":1},"stale-after-external-commit")
        self.assertEqual(stale["code"],"STALE_WORKSPACE_REVISION")
        self.assertEqual(self.service.ws.get_revision(self.service.doc),5)

    def test_unauthorized_scope_commit_without_preview_and_post_commit_mutation_are_denied(self):
        wrong=self.service.handle("begin_function_draft",{"expected_revision":4,"name":"OTHER",
            "parameters":["ID"],"callee_handle":"age_by_id.function"},"wrong-name")
        self.assertEqual(wrong["code"],"MISSION_SCOPE_DENIED")
        bad_call=self.apply([{"op_id":"bad_call","kind":"define_function_call","handle":"call",
            "function_handle":"invented.function","arguments":[]}])
        self.assertEqual(bad_call["code"],"UNKNOWN_PORTABLE_FUNCTION")
        no_preview=self.service.handle("commit_preview",{"transaction_id":"nonexistent"},"no-preview")
        self.assertFalse(no_preview.get("committed",False));self.assertEqual(self.service.ws.get_revision(self.service.doc),4)
        self.apply(construction_ops())
        preview=self.service.handle("preview_function_draft",{"draft_id":self.draft_id,"expected_revision":4,
            "expected_draft_revision":9},"preview")
        self.assertTrue(preview["ok"])
        self.service.handle("commit_preview",{"transaction_id":preview["transaction_id"]},"commit")
        after=self.apply([{"op_id":"late","kind":"define_number","handle":"late","value":2}],rev=9)
        self.assertEqual(after["code"],"DRAFT_ALREADY_COMMITTED")
        self.assertEqual(self.service.ws.get_revision(self.service.doc),5)


if __name__=="__main__":unittest.main()
