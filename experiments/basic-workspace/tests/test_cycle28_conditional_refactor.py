"""Cycle 28 identity-anchored IF condition replacement controls."""
from __future__ import annotations
import copy, sys, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; PI=ROOT/"pi-integration"
sys.path.insert(0,str(PI))
from cycle28_gateway import Cycle28Gateway, PATH, ANCHOR
from basic_workspace.model import WorkspaceError

class Cycle28ConditionalEditTests(unittest.TestCase):
    def gateway(self):
        td=tempfile.TemporaryDirectory(prefix="atlas-cycle28-test-",dir="/var/tmp")
        self.addCleanup(td.cleanup)
        return Cycle28Gateway(Path(td.name)/"gateway",PI/"results/cycle28-conditional-refactor/contracts/mission.json")

    def request(self,g):
        return {"expected_revision":10,"function_handle":"score_class.function","control_path":copy.deepcopy(PATH),
            "anchor_statement_handle":ANCHOR,"expected_condition":copy.deepcopy(g.expected_old),
            "condition":{"kind":"binary","operator":"=","left":{"kind":"call","function_handle":"is_at_cap.function","arguments":[{"kind":"local_ref","name":"X"}]},"right":{"kind":"number","value":1}}}

    def test_real_typed_edit_preserves_identities_and_only_changes_condition_line(self):
        g=self.gateway(); g.discover(); before=g.initial_code; aliases=dict(g.aliases)
        p=g.preview(self.request(g),"test-preview")
        self.assertTrue(p["ok"]); self.assertEqual(g.ws.get_revision(g.doc),10)
        self.assertEqual(g.ws.render_document(g.doc),before)
        c=g.commit({"transaction_id":p["transaction_id"]},"test-commit")
        self.assertTrue(c["committed"]); self.assertEqual(c["revision"],11); self.assertEqual(g.aliases,aliases)
        after=g.ws.render_document(g.doc)
        changed=[i for i,(a,b) in enumerate(zip(before.splitlines(),after.splitlines())) if a!=b]
        self.assertEqual(len(changed),1)
        self.assertIn("IS_AT_CAP(X) = 1",after.splitlines()[changed[0]])
        self.assertIn("NORMALIZE_SCORE(X) = 50",before.splitlines()[changed[0]])
        result=g.validate({"expected_revision":11})
        self.assertTrue(result["mission_complete"]); self.assertEqual(result["replay"]["identity_remappings"],23)
        self.assertEqual(g.aliases,aliases)

    def test_wrong_target_old_condition_and_undiscovered_call_are_side_effect_free(self):
        g=self.gateway();g.discover(); original=g.ws.render_document(g.doc)
        cases=[]
        wrong=self.request(g);wrong["control_path"][0]["index"]=1;cases.append(wrong)
        old=self.request(g);old["expected_condition"]["right"]["value"]=49;cases.append(old)
        unknown=self.request(g);unknown["condition"]["left"]["function_handle"]="missing.function";cases.append(unknown)
        wrong_call=self.request(g);wrong_call["condition"]["left"]["function_handle"]="is_passing.function";cases.append(wrong_call)
        for i,req in enumerate(cases):
            response=g.preview(req,f"rejected-{i}")
            self.assertFalse(response["ok"]);self.assertTrue(response["revision_unchanged"])
            self.assertFalse(response["authoritative_workspace_changed"])
            self.assertEqual(g.ws.get_revision(g.doc),10);self.assertEqual(g.ws.render_document(g.doc),original)

    def test_missing_anchor_stale_revision_and_unknown_fields_rejected(self):
        g=self.gateway();g.discover();original=g.ws.render_document(g.doc)
        bad=self.request(g);bad["anchor_statement_handle"]="unknown.statement"
        self.assertFalse(g.preview(bad,"anchor")["ok"])
        stale=self.request(g);stale["expected_revision"]=9
        self.assertEqual(g.preview(stale,"stale")["code"],"STALE_REVISION")
        extra=self.request(g);extra["statement_handle"]=ANCHOR
        self.assertEqual(g.preview(extra,"extra")["code"],"UNKNOWN_SEMANTIC_FIELD")
        self.assertEqual(g.ws.get_revision(g.doc),10);self.assertEqual(g.ws.render_document(g.doc),original)

    def test_unknown_gateway_identity_fails_canonical_operation(self):
        g=self.gateway();g.discover();req=self.request(g);ops=g._operation(req);op=ops[0]
        op["anchor_statement_id"]="statement_unknown"
        with self.assertRaises(WorkspaceError):g.ws.preview_transaction(g.doc,10,[op],include_diff=True)
        self.assertEqual(g.ws.get_revision(g.doc),10)

if __name__=="__main__":unittest.main()
