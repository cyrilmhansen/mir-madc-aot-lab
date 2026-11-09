"""Cycle 26 rename identity, transaction, replay, and inverse controls."""
from __future__ import annotations
import copy,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];PI=ROOT/"pi-integration"
sys.path.insert(0,str(PI))
from cycle26_gateway import Cycle26Gateway,HANDLE,OLD_NAME,NEW_NAME
from basic_workspace.model import WorkspaceError

class Cycle26SemanticRenameTests(unittest.TestCase):
    def gateway(self):
        td=tempfile.TemporaryDirectory(prefix="cycle26-",dir="/var/tmp");self.addCleanup(td.cleanup)
        return Cycle26Gateway(Path(td.name)/"gateway")

    def request(self,revision=8,handle=HANDLE,expected=OLD_NAME,new=NEW_NAME):
        return {"expected_revision":revision,"function_handle":handle,"expected_name":expected,"new_name":new}

    def test_cycle25_stream_reconstructs_revision8_and_historical_indent_drift_is_only_whitespace(self):
        g=self.gateway()
        self.assertEqual(g.ws.get_revision(g.doc),8);self.assertEqual(len(g.aliases),18)
        self.assertTrue(g.historical_display_whitespace_only)
        self.assertTrue(g.baseline["functions"])
        self.assertEqual(g.aliases[HANDLE],g.base_aliases[HANDLE])

    def test_rename_preview_and_commit_preserve_function_parameter_statement_and_token_ids(self):
        g=self.gateway();g.discover();inspection=g.inspect()
        self.assertEqual(inspection["target"]["current_source_name"],OLD_NAME)
        self.assertGreater(len(inspection["target"]["references"]),1)
        source=g.ws.render_document(g.doc);aliases=dict(g.aliases)
        tokens={t.uid:t.text for t in g.ws.documents[g.doc].tokens}
        result=g._preview_rename(self.request(),"test-preview")
        self.assertTrue(result["ok"]);self.assertTrue(result["candidate_is_preview_only"])
        self.assertTrue(result["semantic_identity_preserved"]);self.assertEqual(g.ws.get_revision(g.doc),8)
        self.assertEqual(g.ws.render_document(g.doc),source)
        committed=g._commit_rename({"transaction_id":result["transaction_id"]},"test-commit")
        self.assertTrue(committed["committed"]);self.assertEqual(committed["revision"],9)
        self.assertEqual(g.aliases,aliases);self.assertEqual(g.aliases[HANDLE],aliases[HANDLE])
        after={t.uid:t.text for t in g.ws.documents[g.doc].tokens}
        self.assertEqual(set(after),set(tokens));self.assertEqual(sum(tokens[u]!=after[u] for u in tokens),len(result["changed_token_ids"]))
        self.assertIn("NORMALIZE_SCORE",g.ws.render_document(g.doc));self.assertNotIn("CLAMP_SCORE",g.ws.render_document(g.doc))
        self.assertTrue(all(t.text==NEW_NAME for t in g.ws.documents[g.doc].tokens if t.uid in result["changed_token_ids"]))
        validation=g.validate(9,"test-validation","host")
        self.assertTrue(validation["mission_complete"]);self.assertTrue(validation["function_identity_preserved"])
        self.assertTrue(validation["parameter_statement_token_identities_preserved"])
        self.assertTrue(validation["replay"]["passed"]);self.assertEqual(validation["replay"]["identity_remappings"],18)

    def test_mission_denials_and_workspace_collision_invalid_name_stale_revision_are_nonmutating(self):
        g=self.gateway();g.discover();g.inspect();source=g.ws.render_document(g.doc)
        cases=[(self.request(handle="unknown.function"),"MISSION_RENAME_SCOPE"),
               (self.request(handle="is_passing.function"),"MISSION_RENAME_SCOPE"),
               (self.request(expected="OTHER"),"RENAME_PRECONDITION_FAILED"),
               (self.request(new="SCORE_CLASS"),"MISSION_RENAME_NAME"),
               (self.request(revision=7),"STALE_REVISION")]
        for req,code in cases:
            with self.subTest(code=code):
                with self.assertRaises(WorkspaceError) as caught:g._candidate(req)
                self.assertEqual(caught.exception.code,code)
                self.assertEqual(g.ws.get_revision(g.doc),8);self.assertEqual(g.ws.render_document(g.doc),source)
        sid=g.aliases[HANDLE]
        for name,code in (("IS_PASSING","NAME_COLLISION"),("BAD NAME","INVALID_NAME")):
            clone=copy.deepcopy(g.ws)
            with self.subTest(name=name):
                with self.assertRaises(WorkspaceError) as caught:clone.rename_symbol(g.doc,sid,name,8)
                self.assertEqual(caught.exception.code,code)
                self.assertEqual(g.ws.get_revision(g.doc),8);self.assertEqual(g.ws.render_document(g.doc),source)

    def test_inverse_rename_restores_canonical_source_byte_for_byte(self):
        g=self.gateway();before=g.ws.render_document(g.doc)
        before_ids={t.uid:t.text for t in g.ws.documents[g.doc].tokens};function_id=g.aliases[HANDLE]
        g.ws.rename_symbol(g.doc,function_id,NEW_NAME,8)
        self.assertEqual(g.ws.get_revision(g.doc),9)
        g.ws.rename_symbol(g.doc,function_id,OLD_NAME,9)
        self.assertEqual(g.ws.get_revision(g.doc),10)
        self.assertEqual(g.ws.render_document(g.doc),before)
        self.assertEqual({t.uid:t.text for t in g.ws.documents[g.doc].tokens},before_ids)
        self.assertEqual(g.ws.documents[g.doc].symbols[function_id].name,OLD_NAME)

if __name__=="__main__":unittest.main()
