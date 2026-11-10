"""Cycle37 verified-handoff rename authorization and identity regression tests."""
from __future__ import annotations
import copy, json, shutil, sys, tempfile, unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]; PI=ROOT/"pi-integration"
RESULTS=PI/"results/cycle37-reusable-rename/production-bridge-attempt-03"
sys.path.insert(0,str(PI));sys.path.insert(0,str(ROOT))
from basic_workspace.model import WorkspaceError
from cycle26_gateway import Cycle26Gateway
from verified_handoff import build_handoff, verify_handoff


class Cycle37ReusableRenameTests(unittest.TestCase):
    def temp(self):
        td=tempfile.TemporaryDirectory(prefix="cycle37-rename-",dir="/var/tmp");self.addCleanup(td.cleanup)
        return Path(td.name)

    def paths(self,label):
        mission=RESULTS/label
        return (mission/"rename-contract.json",mission/"handoff/handoff.json",mission/"handoff/host-trust-anchor.json",
            mission/"creation/gateway-evidence")

    def gateway(self,label,output=None,contract=None,handoff=None,anchor=None,source=None):
        cp,hp,ap,root=self.paths(label)
        return Cycle26Gateway(output or self.temp()/"gateway",contract or cp,verified_handoff_path=handoff or hp,
            handoff_anchor_path=anchor or ap,handoff_evidence_root=source or root)

    def request(self,g,new_name=None,**overrides):
        c=g.contract
        row={"expected_revision":g.base_revision,"function_handle":c["target_handle"],
            "expected_name":c["expected_source_name"],"new_name":new_name or c["new_source_name"]}
        row.update(overrides);return row

    def test_both_authenticated_missions_rename_and_replay(self):
        for label in ("mission-a","mission-b"):
            with self.subTest(label=label):
                g=self.gateway(label);self.assertEqual(g.ws.get_revision(g.doc),5)
                base_source=g.ws.render_document(g.doc);base_aliases=dict(g.aliases);g.discover();inspection=g.inspect()
                self.assertEqual(inspection["target"]["current_source_name"],g.contract["expected_source_name"])
                preview=g._preview_rename(self.request(g),"cycle37-test-preview")
                self.assertTrue(preview["ok"]);self.assertEqual(g.ws.get_revision(g.doc),5)
                self.assertEqual(g.ws.render_document(g.doc),base_source)
                self.assertEqual(g.aliases,base_aliases)
                committed=g._commit_rename({"transaction_id":preview["transaction_id"]},"cycle37-test-commit")
                self.assertTrue(committed["committed"]);self.assertEqual(committed["revision"],6)
                result=g.validate(6,"cycle37-test-validation","host")
                self.assertTrue(result["mission_complete"],result)
                self.assertTrue(result["all_portable_identities_preserved"])
                self.assertTrue(result["dependency_identity_edges_unchanged"])
                self.assertEqual(g.aliases,base_aliases)
                self.assertIn(g.contract["new_source_name"],g.ws.render_document(g.doc))
                self.assertNotIn(g.contract["expected_source_name"],g.ws.render_document(g.doc))

    def test_rename_policy_denies_unseen_wrong_scope_wrong_old_new_stale_and_extra_fields(self):
        g=self.gateway("mission-a");req=self.request(g)
        with self.assertRaises(WorkspaceError) as unseen:g._candidate(req)
        self.assertEqual(unseen.exception.code,"FUNCTION_NOT_DISCOVERED")
        g.discover();before=g.ws.render_document(g.doc)
        cases=[({**req,"function_handle":"invented.function"},"MISSION_RENAME_SCOPE"),
            ({**req,"function_handle":"is_passing.function"},"MISSION_RENAME_SCOPE"),
            ({**req,"expected_name":"WRONG"},"RENAME_PRECONDITION_FAILED"),
            ({**req,"new_name":"NOT_AUTHORIZED"},"MISSION_RENAME_NAME"),
            ({**req,"expected_revision":4},"STALE_REVISION"),
            ({**req,"operations":[{"operation":"rename_symbol"}]},"INVALID_RENAME_REQUEST")]
        for request,code in cases:
            with self.subTest(code=code):
                with self.assertRaises(WorkspaceError) as caught:g._candidate(request)
                self.assertEqual(caught.exception.code,code)
                self.assertEqual(g.ws.get_revision(g.doc),5);self.assertEqual(g.ws.render_document(g.doc),before)

    def test_workspace_collision_and_invalid_identifier_are_canonical_denials(self):
        for new_name,expected_code in (("IS_PASSING","NAME_COLLISION"),("BAD NAME","INVALID_NAME")):
            with self.subTest(name=new_name):
                base=self.temp();contract_path,handoff_path,anchor_path,source=self.paths("mission-a")
                contract=json.loads(contract_path.read_text());contract["mission_id"]+="."+expected_code.lower()
                contract["new_source_name"]=new_name;changed=base/"contract.json"
                changed.write_text(json.dumps(contract,indent=2)+"\n")
                sequence=source/"creation-sequence.json"
                bundle=base/"handoff.json";anchor=base/"anchor.json"
                build_handoff(source,sequence,changed,bundle,anchor)
                g=self.gateway("mission-a",base/"gateway",changed,bundle,anchor,source);g.discover()
                with self.assertRaises(WorkspaceError) as caught:g._candidate(self.request(g))
                self.assertEqual(caught.exception.code,expected_code)
                self.assertEqual(g.ws.get_revision(g.doc),5)

    def test_contract_and_candidate_changes_after_preview_do_not_commit(self):
        for mutate_contract in (False,True):
            with self.subTest(mutate_contract=mutate_contract):
                base=self.temp();contract_path,handoff,anchor,source=self.paths("mission-a")
                local_contract=base/"contract.json";shutil.copyfile(contract_path,local_contract)
                g=self.gateway("mission-a",base/"gateway",local_contract,handoff,anchor,source);g.discover()
                before=g.ws.render_document(g.doc);preview=g._preview_rename(self.request(g),"pending")
                self.assertTrue(preview["ok"])
                if mutate_contract:
                    local_contract.write_text(local_contract.read_text()+" ")
                    expected="RENAME_CONTRACT_CHANGED"
                else:
                    g.transactions._pending[preview["transaction_id"]]["metadata"]["request"]["expected_name"]="WRONG_NAME"
                    expected="RENAME_PRECONDITION_FAILED"
                result=g._commit_rename({"transaction_id":preview["transaction_id"]},"commit")
                self.assertFalse(result["committed"]);self.assertEqual(result["code"],expected)
                self.assertEqual(g.ws.get_revision(g.doc),5);self.assertEqual(g.ws.render_document(g.doc),before)

    def test_intervening_target_change_causes_stale_preview_and_preserves_raced_state(self):
        g=self.gateway("mission-a");g.discover();preview=g._preview_rename(self.request(g),"pending")
        target=g.aliases[g.contract["target_handle"]]
        g.ws.rename_symbol(g.doc,target,"TEMP_SCORE",5)
        raced_revision=g.ws.get_revision(g.doc);raced_source=g.ws.render_document(g.doc)
        result=g._commit_rename({"transaction_id":preview["transaction_id"]},"stale-commit")
        self.assertFalse(result["committed"]);self.assertEqual(result["code"],"STALE_REVISION")
        self.assertEqual(g.ws.get_revision(g.doc),raced_revision);self.assertEqual(g.ws.render_document(g.doc),raced_source)

    def test_handoff_bundle_contract_and_source_artifact_tampering_fail_closed(self):
        cp,hp,ap,source=self.paths("mission-a")
        cp_b,_,_,_=self.paths("mission-b")
        with self.assertRaises(WorkspaceError) as wrong:verify_handoff(hp,ap,source,cp_b)
        self.assertIn(wrong.exception.code,{"HANDOFF_TRUST_BINDING","HANDOFF_DESTINATION_MISMATCH"})
        base=self.temp();tampered=base/"handoff.json"
        bundle=json.loads(hp.read_text());bundle["semantic_fingerprint"]="0"*64
        tampered.write_text(json.dumps(bundle))
        with self.assertRaises(WorkspaceError) as bundle_error:verify_handoff(tampered,ap,source,cp)
        self.assertEqual(bundle_error.exception.code,"HANDOFF_TRUST_ANCHOR_MISMATCH")
        copied=base/"evidence";shutil.copytree(source,copied)
        stream=copied/"constructive-operations.json";data=json.loads(stream.read_text())
        data["operations"][0]["arguments"]["name"]="TAMPERED"
        stream.write_text(json.dumps(data))
        with self.assertRaises(WorkspaceError) as evidence_error:verify_handoff(hp,ap,copied,cp)
        self.assertEqual(evidence_error.exception.code,"HANDOFF_ARTIFACT_DIGEST")
        with self.assertRaises(WorkspaceError) as missing:Cycle26Gateway(base/"missing",cp)
        self.assertEqual(missing.exception.code,"HANDOFF_ARGUMENTS")

    def test_inverse_and_repeated_rename_preserve_semantics_and_references(self):
        g=self.gateway("mission-a");source=g.ws.render_document(g.doc);aliases=dict(g.aliases)
        expected=g._observe_by_handle(g.ws,g.doc,5,g.aliases,g.contract["validation_inputs"])
        symbol_id=g.aliases["bounded_score.function"]
        g.ws.rename_symbol(g.doc,symbol_id,"NORMALIZED_SCORE",5)
        self.assertEqual(g._observe_by_handle(g.ws,g.doc,6,g.aliases,g.contract["validation_inputs"]),expected)
        g.ws.rename_symbol(g.doc,symbol_id,"BOUNDED_SCORE",6)
        self.assertEqual(g.ws.render_document(g.doc),source);self.assertEqual(g.aliases,aliases)
        self.assertEqual(g._observe_by_handle(g.ws,g.doc,7,g.aliases,g.contract["validation_inputs"]),expected)
        self.assertEqual(g.aliases["bounded_score.function"],symbol_id)

    def test_wrong_contract_version_and_unknown_fields_fail_closed(self):
        g=self.gateway("mission-a")
        from rename_policy import validate_v2_contract
        cases=[]
        bad=copy.deepcopy(g.contract);bad["version"]=3;cases.append((bad,"RENAME_CONTRACT_VERSION"))
        bad=copy.deepcopy(g.contract);bad["untrusted_policy"]=True;cases.append((bad,"RENAME_CONTRACT_SCHEMA"))
        for contract,code in cases:
            with self.subTest(code=code):
                with self.assertRaises(WorkspaceError) as caught:validate_v2_contract(contract)
                self.assertEqual(caught.exception.code,code)

if __name__=="__main__":unittest.main()
