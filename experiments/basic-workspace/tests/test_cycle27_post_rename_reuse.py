"""Cycle 27: portable function identity remains callable after source rename."""
from __future__ import annotations
import copy, json, sys, tempfile, unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]; PI=ROOT/"pi-integration"
sys.path.insert(0,str(PI))
from cycle19_gateway import Cycle19Gateway

CAMPAIGN=PI/"results/cycle27-post-rename-reuse"
BASE=PI/"results/cycle26-semantic-rename/real-agent-01"
INPUTS=[-100,-1,0,1,19,20,39,40,44,45,49,50,51,60,100,200]

def body(call_handle="clamp_score.function",argument="X",arity=1):
    args=[{"kind":"local_ref","name":argument} for _ in range(arity)]
    return [{"kind":"assign","target":{"kind":"result"},"expression":{"kind":"number","value":0}},
        {"kind":"if","condition":{"kind":"binary","operator":"=",
            "left":{"kind":"call","function_handle":call_handle,"arguments":args},
            "right":{"kind":"number","value":50}},"then":[{"kind":"assign",
            "target":{"kind":"result"},"expression":{"kind":"number","value":1}}]}]

class Cycle27PostRenameTests(unittest.TestCase):
    def gateway(self):
        td=tempfile.TemporaryDirectory(prefix="atlas-cycle27-gateway-");self.addCleanup(td.cleanup)
        return Cycle19Gateway(Path(td.name),creation_contract_path=CAMPAIGN/"contracts/is-at-cap.json",
            seed_contract_path=CAMPAIGN/"contracts/seed-revision9-verification.json",
            baseline_stream_path=BASE/"constructive-operations.json",baseline_history_path=BASE/"history.jsonl",
            baseline_validation_path=BASE/"mission-validation-host.json")

    def request(self,**updates):
        result={"expected_revision":9,"name":"IS_AT_CAP","parameters":["X"],"body":body()}
        result.update(updates);return result

    def test_authentic_cycle26_stream_rebuilds_revision9_and_reuses_old_handle(self):
        g=self.gateway()
        self.assertEqual(g.revision,9);self.assertEqual(len(g.aliases),18)
        norm=g.base_snapshot; fn=next(x for x in norm["functions"] if x["handle"]=="clamp_score.function")
        self.assertEqual(fn["name"],"NORMALIZE_SCORE")
        self.assertEqual({x["name"] for x in norm["functions"]},{"NORMALIZE_SCORE","IS_PASSING","SCORE_CLASS"})
        stream,replayed,observed,remapped,mapping=g._replay()
        self.assertEqual(len(stream["operations"]),8);self.assertEqual(remapped,18)
        self.assertEqual(len(mapping),18);self.assertEqual(norm,replayed)
        for engine in ("interp","jit"):
            self.assertEqual(observed[engine],g._run_functions(9)[engine])
            self.assertEqual(observed[engine]["50"],{"normalize_score":50.0,"is_passing":1.0,"score_class":3.0})

    def test_preview_commit_binds_to_original_handle_and_replay_adds_identity(self):
        g=self.gateway();g.handle("discover_functions",{},"discover");g.handle("inspect_program",{},"inspect")
        original_id=g.aliases["clamp_score.function"]
        before=copy.deepcopy(g.base_snapshot)
        preview=g._preview(self.request(),"preview")
        self.assertTrue(preview["ok"]);self.assertTrue(preview["candidate_is_preview_only"])
        self.assertEqual(g.ws.get_revision(g.doc),9);self.assertEqual(g.base_snapshot,before)
        committed=g._commit({"transaction_id":preview["transaction_id"]},"commit")
        self.assertTrue(committed["committed"]);self.assertEqual(committed["revision"],10)
        self.assertEqual(g.aliases["clamp_score.function"],original_id)
        result=g.validate_current(10,"host")
        self.assertTrue(result["mission_complete"]);self.assertTrue(result["values_match"])
        self.assertTrue(result["engines_agree"]);self.assertEqual(result["replay"]["identity_remappings"],23)
        source=g.ws.render_document(g.doc)
        self.assertIn("NORMALIZE_SCORE(X)",source);self.assertIn("FUNCTION IS_AT_CAP(X)",source)
        self.assertNotIn("FUNCTION CLAMP_SCORE",source)

    def test_invalid_handles_and_old_source_variable_are_nonmutating(self):
        g=self.gateway();g.handle("discover_functions",{},"discover");source=g.ws.render_document(g.doc)
        cases=[(self.request(body=body("normalize_score.function")),"MISSION_DEPENDENCY_REQUIRED"),
            (self.request(body=body("missing.function")),"MISSION_DEPENDENCY_REQUIRED"),
            (self.request(body=body(arity=0)),"FUNCTION_SIGNATURE_MISMATCH"),
            (self.request(body=body(argument="CLAMP_SCORE")),"UNKNOWN_TRANSACTION_HANDLE"),
            (self.request(replace_function_body={"function_handle":"clamp_score.function"}),"MISSION_OPERATION_FORBIDDEN"),
            (self.request(name="NORMALIZE_SCORE"),"MISSION_SIGNATURE"),
            (self.request(expected_revision=8),"STALE_REVISION")]
        for request,code in cases:
            with self.subTest(code=code):
                semantic={key:value for key,value in request.items() if key!="expected_revision"}
                with self.assertRaises(Exception) as caught:g._candidate(semantic,request["expected_revision"],None)
                self.assertEqual(getattr(caught.exception,"code",None),code)
                self.assertEqual(g.ws.get_revision(g.doc),9);self.assertEqual(g.ws.render_document(g.doc),source)

    def test_undiscovered_call_and_changed_candidate_before_commit_are_rejected(self):
        g=self.gateway();source=g.ws.render_document(g.doc)
        undiscovered=g._preview(self.request(),"before-discovery")
        self.assertEqual(undiscovered.get("code"),"FUNCTION_NOT_DISCOVERED")
        self.assertEqual(g.ws.get_revision(g.doc),9);self.assertEqual(g.ws.render_document(g.doc),source)
        g.handle("discover_functions",{},"discover");g.handle("inspect_program",{},"inspect")
        preview=g._preview(self.request(),"candidate-preview")
        self.assertTrue(preview["ok"]);self.assertEqual(g.ws.get_revision(g.doc),9)
        g.current_contract["required_callees"]=["is_passing.function"]
        rejected=g._commit({"transaction_id":preview["transaction_id"]},"changed-candidate")
        self.assertFalse(rejected.get("committed"));self.assertEqual(rejected.get("code"),"MISSION_DEPENDENCY_REQUIRED")
        self.assertEqual(g.ws.get_revision(g.doc),9);self.assertEqual(g.ws.render_document(g.doc),source)

    def test_corrected_report_uses_revision9_without_rewriting_runner_output(self):
        run=CAMPAIGN/"real-agent-01"
        original=json.loads((run/"summary.json").read_text())
        corrected=json.loads((run/"summary-corrected.json").read_text())
        mission=json.loads((run/"MISSION-3.json").read_text())
        self.assertEqual(original["baseline_revision"],5)
        self.assertEqual(corrected["baseline_revision"],mission["base_document_revision"])
        self.assertEqual(corrected["baseline_revision"],9)
        self.assertEqual(corrected["mission_id"],mission["mission_id"])
        self.assertTrue(corrected["summary_correction"]["fields_corrected"])

    def test_offline_frames_keep_preview_uncommitted_and_show_renamed_binding(self):
        report=json.loads((CAMPAIGN/"real-agent-01/visual-verification.json").read_text())
        self.assertTrue(report["passed"])
        self.assertEqual(report["frame_count"],12)
        checks=report["checks"]
        self.assertTrue(all(checks.values()))

if __name__=="__main__":unittest.main()
