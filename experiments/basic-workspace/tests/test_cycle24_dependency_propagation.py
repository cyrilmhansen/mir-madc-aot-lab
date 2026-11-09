"""Cycle 24 multi-dependency construction and downstream-change controls."""
from __future__ import annotations
import importlib.util, json, pathlib, shutil, subprocess, sys, tempfile, unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
PI=ROOT/"pi-integration"
BASE=PI/"results/cycle21-reusable-maintenance/real-agent-01"
CONTRACTS=PI/"results/cycle24-dependency-propagation/contracts"
spec=importlib.util.spec_from_file_location("cycle24_gateway_test",PI/"cycle19_gateway.py")
cycle19=importlib.util.module_from_spec(spec);sys.modules[spec.name]=cycle19;spec.loader.exec_module(cycle19)
from basic_workspace.model import WorkspaceError
from cycle20_gateway import Cycle20Gateway

def score_body():
    num=lambda value:{"kind":"number","value":value}
    call=lambda handle:{"kind":"call","function_handle":handle,"arguments":[{"kind":"local_ref","name":"X"}]}
    assign=lambda value:{"kind":"assign","target":{"kind":"result"},"expression":num(value)}
    return [
        {"kind":"if","condition":{"kind":"binary","operator":"<","left":call("clamp_score.function"),"right":num(20)},"then":[assign(0)]},
        {"kind":"if","condition":{"kind":"binary","operator":">=","left":call("clamp_score.function"),"right":num(20)},"then":[assign(1)]},
        {"kind":"if","condition":{"kind":"binary","operator":">=","left":call("is_passing.function"),"right":num(1)},"then":[assign(2)]}]

def seeded_gateway(out):
    return cycle19.Cycle19Gateway(out,creation_contract_path=CONTRACTS/"mission-1-score-class.json",
        seed_contract_path=CONTRACTS/"seed-revision5.json",baseline_stream_path=BASE/"constructive-operations.json",
        baseline_history_path=BASE/"history.jsonl",baseline_validation_path=BASE/"validation.json")

class MultiDependencyCreationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="atlas-cycle24-gateway-",dir="/var/tmp")
        self.addCleanup(self.tmp.cleanup);self.g=seeded_gateway(pathlib.Path(self.tmp.name)/"run")

    def test_authentic_cycle21_stream_reconstructs_exact_revision5(self):
        self.assertEqual(self.g.revision,5)
        self.assertEqual([row["name"] for row in self.g.base_snapshot["functions"]],["CLAMP_SCORE","IS_PASSING"])
        self.assertEqual(len(self.g.aliases),11)
        self.assertEqual(sorted(self.g._dependencies()),[
            {"caller":"IS_PASSING","callee":"CLAMP_SCORE"}])
        self.assertTrue(self.g.resume_verification["passed"])
        observed=self.g._run_functions(5)
        expected={str(x):{"clamp_score":float(min(50,max(0,x))),
            "is_passing":float(min(50,max(0,x))>=40)} for x in self.g.current_contract["validation"]["inputs"]}
        self.assertEqual(observed,{"interp":expected,"jit":expected})

    def test_two_discovered_calls_preview_atomically_commit_and_replay(self):
        g=self.g; discovered=g.handle("discover_functions",{},"discover")
        self.assertEqual({row["handle"] for row in discovered["functions"]},{"clamp_score.function","is_passing.function"})
        args={"expected_revision":5,"name":"SCORE_CLASS","parameters":["X"],"body":score_body()}
        preview=g.handle("preview_create_function",args,"preview")
        self.assertTrue(preview["ok"]);self.assertEqual(preview["bound_callee_handles"],
            ["clamp_score.function","is_passing.function"])
        self.assertEqual(g.ws.get_revision(g.doc),5)
        committed=g.handle("commit_preview",{"transaction_id":preview["transaction_id"]},"commit")
        self.assertTrue(committed["committed"]);self.assertEqual(committed["revision"],6)
        validation=g.handle("host_validate",{"expected_revision":6},"host")
        self.assertTrue(validation["mission_complete"],validation["diagnostics"])
        self.assertEqual(validation["replay"]["identity_remappings"],17)
        self.assertTrue(validation["replay"]["binding_equivalence"])
        self.assertEqual(validation["observed_results"]["interp"]["39"]["score_class"],1)
        self.assertEqual(validation["observed_results"]["jit"]["40"]["score_class"],2)

    def test_unknown_and_unauthorized_calls_and_stale_revision_do_not_mutate(self):
        g=self.g;g.handle("discover_functions",{},"discover")
        args={"expected_revision":5,"name":"SCORE_CLASS","parameters":["X"],"body":score_body()}
        before=(g.ws.get_revision(g.doc),list(g.ws.documents[g.doc].tokens))
        wrong=json.loads(json.dumps(args));wrong["body"][1]["condition"]["left"]["function_handle"]="unknown.function"
        self.assertEqual(g.handle("preview_create_function",wrong,"unknown")["code"],"MISSION_DEPENDENCY_REQUIRED")
        missing=json.loads(json.dumps(args));missing["body"]=missing["body"][:2]
        self.assertEqual(g.handle("preview_create_function",missing,"missing")["code"],"MISSION_DEPENDENCY_REQUIRED")
        stale=json.loads(json.dumps(args));stale["expected_revision"]=4
        self.assertEqual(g.handle("preview_create_function",stale,"stale")["code"],"STALE_REVISION")
        self.assertEqual((g.ws.get_revision(g.doc),list(g.ws.documents[g.doc].tokens)),before)

    def test_denied_threshold_edit_preserves_the_committed_third_function(self):
        g=self.g;g.handle("discover_functions",{},"discover")
        args={"expected_revision":5,"name":"SCORE_CLASS","parameters":["X"],"body":score_body()}
        preview=g.handle("preview_create_function",args,"preview")
        g.handle("commit_preview",{"transaction_id":preview["transaction_id"]},"commit")
        validation=g.handle("host_validate",{"expected_revision":6},"host")
        self.assertTrue(validation["mission_complete"])
        maint=Cycle20Gateway(pathlib.Path(self.tmp.name)/"maintenance",
            contract_path=CONTRACTS/"mission-2-threshold45.json",
            baseline_stream_path=pathlib.Path(self.tmp.name)/"run"/"constructive-operations.json",
            baseline_history_path=pathlib.Path(self.tmp.name)/"run"/"history.jsonl",
            baseline_validation_path=pathlib.Path(self.tmp.name)/"run"/"mission-3-validation-host.json")
        before=(maint.ws.get_revision(maint.doc),maint.ws.render_document(maint.doc),maint._normalized())
        maint.handle("discover_functions",{},"discover")
        denied=maint.handle("preview_semantic_edit",{"expected_revision":6,"function_handle":"score_class.function",
            "edits":[{"target":{"function_handle":"score_class.function","control_path":[{"block":"body","index":0}],
                "expression_path":[1]},"expected_value":20,"replacement_value":45}]},"denied")
        self.assertFalse(denied["ok"])
        self.assertEqual(denied["code"],"MISSION_EDIT_SCOPE")
        self.assertEqual((maint.ws.get_revision(maint.doc),maint.ws.render_document(maint.doc),maint._normalized()),before)

    def test_production_typescript_jsonl_and_shared_kernel_preflight(self):
        if not shutil.which("bun"):
            self.skipTest("Bun is required for the production extension/JSONL boundary")
        with tempfile.TemporaryDirectory(prefix="atlas-cycle24-dispatch-",dir="/var/tmp") as temp:
            out=pathlib.Path(temp)/"preflight"
            proc=subprocess.run([sys.executable,str(PI/"cycle24_preflight.py"),"--output",str(out)],
                capture_output=True,text=True,timeout=180)
            self.assertEqual(proc.returncode,0,proc.stderr[-3000:]+proc.stdout[-3000:])
            report=json.loads((out/"summary.json").read_text())
            self.assertEqual(report["function_creation"]["committed_revision"],6)
            self.assertTrue(report["function_creation"]["host_oracle_and_replay"])
            self.assertEqual(report["numeric_maintenance"]["committed_revision"],7)
            self.assertTrue(report["numeric_maintenance"]["host_oracle_and_replay"])
            self.assertEqual(report["shared_transaction_lifecycle"],
                "SemanticTransactionKernel.preview/commit used for both operation families")

if __name__=="__main__":unittest.main()
