"""Cycle 25 bounded structural insertion and identity continuity controls."""
from __future__ import annotations
import json, sys, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PI=ROOT/"pi-integration"
sys.path.insert(0,str(PI))
from cycle25_gateway import Cycle25Gateway, NEW_STATEMENT_HANDLE, INPUTS
from basic_workspace.model import Workspace, WorkspaceError


def request(revision=7, *, function="score_class.function", anchor="score_class.statement.3", operator="=", callee="clamp_score.function", value=50, result=3):
    return {"expected_revision":revision,"function_handle":function,"before_statement_handle":anchor,
      "statement":{"kind":"if","condition":{"kind":"binary","operator":operator,
        "left":{"kind":"call","function_handle":callee,"arguments":[{"kind":"local_ref","name":"X"}]},
        "right":{"kind":"number","value":value}},
        "then":[{"kind":"assign","target":{"kind":"result"},"expression":{"kind":"number","value":result}}]}}


class Cycle25StructuralEditTests(unittest.TestCase):
    def gateway(self):
        td=tempfile.TemporaryDirectory(prefix="cycle25-",dir="/var/tmp")
        self.addCleanup(td.cleanup)
        return Cycle25Gateway(Path(td.name)/"gateway")

    def test_authentic_revision7_reconstruction_and_preview_preserves_all_17_identities(self):
        g=self.gateway()
        self.assertEqual(g.ws.get_revision(g.doc),7)
        self.assertEqual(len(g.aliases),17)
        original_code=g.ws.render_document(g.doc)
        original_ids={t.uid:t.text for t in g.ws.documents[g.doc].tokens}
        g.discover();g.inspect()
        operations,candidate,new_aliases,candidate_ws,applied,observed=g._candidate(request())
        self.assertEqual(g.ws.get_revision(g.doc),7)
        self.assertEqual(g.ws.render_document(g.doc),original_code)
        self.assertEqual(len(applied["created_statements"]),1)
        self.assertEqual(set(g.aliases).difference(new_aliases),set())
        self.assertEqual(set(new_aliases)-set(g.aliases),{NEW_STATEMENT_HANDLE})
        self.assertTrue(set(original_ids).issubset({t.uid for t in candidate_ws.documents[g.doc].tokens}))
        self.assertEqual(observed["interp"],observed["jit"])
        self.assertEqual(observed["interp"]["50"]["score_class"],3.0)
        self.assertEqual(observed["interp"]["49"]["score_class"],2.0)

    def test_reconstructed_revision7_display_matches_preserved_cycle24_snapshot(self):
        g=self.gateway()
        historical=ROOT/"pi-integration/results/cycle24-dependency-propagation/combined-replay/visual-source.json"
        source=json.loads(historical.read_text(encoding="utf-8"))
        self.assertEqual(source["snapshots"]["7"],g.initial_code)
        self.assertEqual(g.ws.get_revision(g.doc),7)

    def test_kernel_preview_commit_and_replay_allocate_only_new_assignment_identity(self):
        g=self.gateway();g.discover();g.inspect();before=g._find(g.baseline,"score_class.function")
        preview=g._preview(request(),"test-preview")
        self.assertTrue(preview["ok"]);self.assertTrue(preview["candidate_is_preview_only"])
        self.assertEqual(g.ws.get_revision(g.doc),7)
        commit=g._commit({"transaction_id":preview["transaction_id"]},"test-commit")
        self.assertTrue(commit["committed"]);self.assertEqual(commit["revision"],8)
        self.assertEqual(len(g.aliases),18)
        self.assertEqual(g._find(g.baseline,"score_class.function"),before)
        self.assertTrue(all(g.aliases[h]==g.base_aliases[h] for h in g.base_aliases))
        validation=g.validate(8,"test-validation","host")
        self.assertTrue(validation["mission_complete"])
        self.assertTrue(validation["replay"]["passed"])
        self.assertEqual(validation["replay"]["identity_remappings"],18)
        self.assertTrue(validation["existing_identity_bindings_preserved"])

    def test_scope_anchor_dependency_and_typed_candidate_denials_do_not_mutate(self):
        g=self.gateway();g.discover();g.inspect();baseline=g.ws.render_document(g.doc)
        cases=[
            (request(function="is_passing.function"),"MISSION_EDIT_SCOPE"),
            (request(anchor="score_class.statement.2"),"INVALID_INSERTION_ANCHOR"),
            (request(callee="is_passing.function"),"MISSION_DEPENDENCY_FORBIDDEN"),
            (request(operator=">="),"MISSION_IF_CONDITION"),
            (request(result=4),"MISSION_FOURTH_CATEGORY"),
        ]
        for candidate,code in cases:
            with self.subTest(code=code):
                with self.assertRaises(WorkspaceError) as caught:g._candidate(candidate)
                self.assertEqual(caught.exception.code,code)
                self.assertEqual(g.ws.get_revision(g.doc),7)
                self.assertEqual(g.ws.render_document(g.doc),baseline)

    def test_stale_revision_and_unknown_anchor_are_rejected(self):
        g=self.gateway();g.discover();g.inspect()
        for candidate,code in ((request(revision=6),"STALE_REVISION"),(request(anchor="missing.statement"),"INVALID_INSERTION_ANCHOR")):
            with self.assertRaises(WorkspaceError) as caught:g._candidate(candidate)
            self.assertEqual(caught.exception.code,code)
            self.assertEqual(g.ws.get_revision(g.doc),7)

    def test_workspace_multi_operation_failure_rolls_back_prior_structural_candidate(self):
        g=self.gateway();g.discover();g.inspect();op,_,_,_,_,_=g._candidate(request())
        before=g.ws.render_document(g.doc); rev=g.ws.get_revision(g.doc)
        with self.assertRaises(WorkspaceError):
            g.ws.apply_transaction(g.doc,rev,[op[0],{"operation":"unsupported_after_candidate"}])
        self.assertEqual(g.ws.get_revision(g.doc),rev)
        self.assertEqual(g.ws.render_document(g.doc),before)

    def test_invalid_body_and_non_boundary_anchor_fail_workspace_transaction(self):
        g=self.gateway();g.discover();g.inspect()
        op,_,_,_,_,_=g._candidate(request())
        bad=dict(op[0]);bad["statement"]={"kind":"if","condition":{"kind":"number","value":1},"then":[]}
        with self.assertRaises(WorkspaceError):g.ws.apply_transaction(g.doc,7,[bad])
        self.assertEqual(g.ws.get_revision(g.doc),7)
        bad_anchor=dict(op[0]);bad_anchor["before_statement_id"]=g.aliases["score_class.statement.2"]
        with self.assertRaises(WorkspaceError) as caught:g.ws.apply_transaction(g.doc,7,[bad_anchor])
        self.assertEqual(caught.exception.code,"INVALID_INSERTION_ANCHOR")
        self.assertEqual(g.ws.get_revision(g.doc),7)

if __name__=="__main__":unittest.main()
