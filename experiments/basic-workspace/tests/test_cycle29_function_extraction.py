"""Cycle 29 typed block extraction, identity retirement, and replay controls."""
from __future__ import annotations
import copy, pathlib, sys, tempfile, unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]; PI=ROOT/"pi-integration"
sys.path.insert(0,str(PI))
from cycle29_gateway import Cycle29Gateway, HELPER, NORMALIZER, SCORE

class Cycle29ExtractionTests(unittest.TestCase):
    def gateway(self):
        td=tempfile.TemporaryDirectory(prefix="atlas-cycle29-test-",dir="/var/tmp");self.addCleanup(td.cleanup)
        return Cycle29Gateway(pathlib.Path(td.name)/"campaign")

    @staticmethod
    def helper_request(revision=11):
        return {"expected_revision":revision,"name":"BASE_SCORE_CLASS","parameters":["X"],
            "callee_handle":NORMALIZER,"body":[{"kind":"if",
                "condition":{"kind":"binary","operator":"<","left":{"kind":"call","function_handle":NORMALIZER,
                    "arguments":[{"kind":"local_ref","name":"X"}]},"right":{"kind":"number","value":20}},
                "then":[{"kind":"assign","target":{"kind":"result"},"expression":{"kind":"number","value":0}}],
                "else":[{"kind":"assign","target":{"kind":"result"},"expression":{"kind":"number","value":1}}]}]}

    def phase_a(self,g):
        g._discover("a-discover")
        preview=g._preview(self.helper_request(),"a-preview")
        self.assertTrue(preview["ok"]);self.assertEqual(g.ws.get_revision(g.doc),11)
        commit=g._commit({"transaction_id":preview["transaction_id"]},"a-commit")
        self.assertTrue(commit["committed"]);self.assertEqual(commit["revision"],12)
        validation=g.validate_current(12,"host")
        self.assertTrue(validation["mission_complete"],validation["diagnostics"])
        checkpoint=g._set_checkpoint_for_b()
        self.assertTrue(g.prepare_mission_b({"checkpoint":checkpoint})["checkpoint_verified"])
        g._discover("b-discover")
        target=g._inspect("b-inspect")["extraction_target"]
        return target

    @staticmethod
    def block_request(target,revision=12):
        return {"expected_revision":revision,"function_handle":SCORE,"control_path":target["control_path"],
            "anchor_statement_handle":target["anchor_statement_handles"][0],
            "expected_block_fingerprint":target["expected_block_fingerprint"],
            "expected_removed_statement_handles":target["expected_removed_statement_handles"],
            "replacement_statements":[{"kind":"assign","target":{"kind":"result"},
                "expression":{"kind":"call","function_handle":HELPER,"arguments":[{"kind":"local_ref","name":"X"}]}}]}

    def test_authentic_revision_11_reconstruction_and_helper_creation(self):
        g=self.gateway()
        self.assertEqual(g.ws.get_revision(g.doc),11);self.assertEqual(len(g.aliases),23)
        self.assertEqual(len(g.constructive_ops),10)
        base=copy.deepcopy(g.base_snapshot)
        self.assertTrue(g._discover("d"))
        preview=g._preview(self.helper_request(),"p")
        self.assertEqual(g.ws.get_revision(g.doc),11);self.assertEqual(g.ws.render_document(g.doc),g.initial["code"])
        g._commit({"transaction_id":preview["transaction_id"]},"c")
        self.assertEqual(g.ws.get_revision(g.doc),12)
        self.assertEqual(g._normalized()["functions"][:4],base["functions"])
        result=g.validate_current(12)
        self.assertTrue(result["mission_complete"]);self.assertTrue(result["replay"]["passed"])
        self.assertEqual(result["replay"]["revision"],12)

    def test_extraction_retires_only_child_assignments_and_replays(self):
        g=self.gateway();target=self.phase_a(g);before=g.ws.render_document(g.doc)
        old_aliases=dict(g.aliases);old_ids={h:old_aliases[h] for h in target["expected_removed_statement_handles"]}
        proposal=self.block_request(target)
        preview=g._preview_block(proposal,"b-preview")
        self.assertTrue(preview["ok"]);self.assertEqual(g.ws.get_revision(g.doc),12)
        self.assertEqual(g.ws.render_document(g.doc),before)
        self.assertEqual(set(preview["identity_migration"]["retired"]),set(target["expected_removed_statement_handles"]))
        commit=g._commit_block({"transaction_id":preview["transaction_id"]},"b-commit")
        self.assertTrue(commit["committed"]);self.assertEqual(commit["revision"],13)
        for handle in target["expected_removed_statement_handles"]:self.assertNotIn(handle,g.aliases)
        self.assertNotIn(old_ids[target["expected_removed_statement_handles"][0]],g.ws.documents[g.doc].statements)
        self.assertIn("score_class.statement.extracted-base-call",g.aliases)
        self.assertEqual(g.aliases[SCORE],old_aliases[SCORE])
        for handle in ("score_class.parameter.id","score_class.statement.2","score_class.statement.3","score_class.statement.category50"):
            self.assertEqual(g.aliases[handle],old_aliases[handle])
        after=g.ws.render_document(g.doc)
        self.assertIn("SCORE_CLASS = BASE_SCORE_CLASS(X)",after)
        for name in ("FUNCTION NORMALIZE_SCORE(X)","FUNCTION IS_PASSING(X)","FUNCTION IS_AT_CAP(X)"):
            left=[line for line in before.splitlines() if line.startswith(name) or line.startswith("  ") or line.startswith("END FUNCTION")]
            self.assertIn(name,after)
        result=g.validate_current(13)
        self.assertTrue(result["mission_complete"],result["diagnostics"])
        self.assertEqual(result["replay"]["revision"],13)
        self.assertTrue(result["replay"]["passed"])
        self.assertEqual(result["replay"]["operation_count"],12)
        self.assertEqual(result["identity_migration"]["retired"] and len(result["identity_migration"]["retired"]),2)

    def test_rejected_second_mission_proposals_leave_revision_12_intact(self):
        g=self.gateway();target=self.phase_a(g);source=g.ws.render_document(g.doc);aliases=dict(g.aliases)
        good=self.block_request(target)
        cases=[]
        wrong_path=copy.deepcopy(good);wrong_path["control_path"]=[{"block":"body","index":1}];cases.append(wrong_path)
        wrong_fp=copy.deepcopy(good);wrong_fp["expected_block_fingerprint"]="0"*64;cases.append(wrong_fp)
        wrong_handles=copy.deepcopy(good);wrong_handles["expected_removed_statement_handles"]=["score_class.statement.2"];cases.append(wrong_handles)
        wrong_callee=copy.deepcopy(good);wrong_callee["replacement_statements"][0]["expression"]["function_handle"]="is_passing.function";cases.append(wrong_callee)
        wrong_arity=copy.deepcopy(good);wrong_arity["replacement_statements"][0]["expression"]["arguments"]=[];cases.append(wrong_arity)
        for i,request in enumerate(cases):
            response=g._preview_block(request,f"negative-{i}")
            self.assertFalse(response["ok"],response)
            self.assertTrue(response["revision_unchanged"])
            self.assertFalse(response["authoritative_workspace_changed"])
            self.assertEqual(g.ws.get_revision(g.doc),12);self.assertEqual(g.ws.render_document(g.doc),source)
            self.assertEqual(g.aliases,aliases)
        stale=copy.deepcopy(good);stale["expected_revision"]=11
        self.assertEqual(g._preview_block(stale,"stale")["code"],"STALE_REVISION")
        self.assertEqual(g.ws.get_revision(g.doc),12);self.assertEqual(g.ws.render_document(g.doc),source)

    def test_bad_canonical_retirement_set_and_stale_workspace_revision_reject(self):
        g=self.gateway();target=self.phase_a(g);g._discover("b-discover-again")
        raw=self.block_request(target)
        # Resolve exactly the production gateway operation, then corrupt its explicit retire set.
        op={"operation":"replace_typed_if_block","function_id":g.aliases[SCORE],"control_path":target["control_path"],
            "anchor_statement_id":g.aliases[target["anchor_statement_handles"][0]],
            "expected_block_fingerprint":g.ws._typed_if_fingerprint(g._target_projection()[1])[0],
            "expected_removed_statement_ids":[g.aliases[target["expected_removed_statement_handles"][0]]],
            "replacement_statements":[{"kind":"assign","target":{"kind":"result"},"expression":g._resolve_expr(raw["replacement_statements"][0]["expression"],g.aliases[SCORE])}]}
        source=g.ws.render_document(g.doc)
        with self.assertRaises(Exception):g.ws.preview_transaction(g.doc,12,[op])
        self.assertEqual(g.ws.get_revision(g.doc),12);self.assertEqual(g.ws.render_document(g.doc),source)
        with self.assertRaises(Exception):g.ws.replace_typed_if_block(g.doc,g.aliases[SCORE],target["control_path"],
            g.aliases[target["anchor_statement_handles"][0]],"bad",[],[],11)
        self.assertEqual(g.ws.get_revision(g.doc),12)

if __name__=="__main__":unittest.main()
