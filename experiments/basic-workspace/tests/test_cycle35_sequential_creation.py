"""Bounded, host-controlled sequential function creation for Cycle 35."""
from __future__ import annotations
import copy, importlib.util, json, pathlib, sys, tempfile, unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
PI=ROOT/"pi-integration"
RESULTS=PI/"results/cycle35-sequential-creation"
spec=importlib.util.spec_from_file_location("cycle35_gateway_test",PI/"cycle19_gateway.py")
cycle19=importlib.util.module_from_spec(spec);sys.modules[spec.name]=cycle19;spec.loader.exec_module(cycle19)
preflight_spec=importlib.util.spec_from_file_location("cycle35_preflight_test",PI/"cycle35_preflight.py")
preflight=importlib.util.module_from_spec(preflight_spec);sys.modules[preflight_spec.name]=preflight;preflight_spec.loader.exec_module(preflight)
from basic_workspace.model import WorkspaceError

class SequentialCreationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="atlas-cycle35-test-",dir="/var/tmp")
        self.addCleanup(self.temp.cleanup);self.root=pathlib.Path(self.temp.name)

    def gateway(self,mission,output=None,**kwargs):
        return cycle19.Cycle19Gateway(output or self.root/"gateway",creation_sequence_path=RESULTS/mission,**kwargs)

    def step(self,g,index,*,validate=True):
        step=g.sequence_contract["steps"][index]
        g.handle("discover_functions",{},f"d-{index}")
        request=preflight.fn_request(step["function"]["name"])
        before=g.ws.get_revision(g.doc)
        preview=g.handle("preview_create_function",{"expected_revision":before,**request},f"p-{index}")
        self.assertTrue(preview["ok"],preview)
        self.assertEqual(g.ws.get_revision(g.doc),before)
        committed=g.handle("commit_preview",{"transaction_id":preview["transaction_id"]},f"c-{index}")
        self.assertTrue(committed["committed"],committed)
        self.assertEqual(committed["revision"],before+1)
        if not validate:return committed
        validation=g.handle("host_validate",{"expected_revision":before+1},f"v-{index}")
        self.assertTrue(validation["mission_complete"],validation)
        expected={str(x):{name:value for name,value in preflight.oracle(g.sequence_contract["sequence_id"],x).items()
            if name in set(next(iter(step["validation"]["expected_results"].values())))}
            for x in step["validation"]["inputs"]}
        self.assertEqual(validation["observed_results"]["interp"],expected)
        self.assertEqual(validation["observed_results"]["jit"],expected)
        return committed

    def advance(self,g):
        result=g.handle("create_checkpoint",{},"checkpoint")
        self.assertTrue(result["ok"],result)
        return g.handle("host_advance_creation_sequence",{"checkpoint":result["checkpoint"]},"advance")

    def run_to_completion(self,g):
        count=len(g.sequence_contract["steps"])
        for index in range(count):
            self.step(g,index)
            advanced=self.advance(g)
            self.assertTrue(advanced["ok"],advanced)
            self.assertEqual(advanced["sequence_completed"],index==count-1)
        return g

    def test_both_missions_validate_each_revision_and_replay(self):
        for filename in ("MISSION-A.json","MISSION-B.json"):
            with self.subTest(mission=filename):
                g=self.run_to_completion(self.gateway(filename,self.root/filename))
                self.assertEqual(g.ws.get_revision(g.doc),5)
                self.assertEqual(len(g._function_handles()),4)
                self.assertTrue(g.sequence_complete)
                stream=json.loads((g.output/"constructive-operations.json").read_text())
                self.assertEqual(len(stream["operations"]),4)
                self.assertEqual(stream["portable_handles"],sorted(g.aliases))
                self.assertEqual([row["revision"] for row in g.sequence_completed],[2,3,4,5])

    def test_progression_requires_validation_and_exact_checkpoint(self):
        g=self.gateway("MISSION-A.json",self.root/"progression")
        self.step(g,0,validate=False)
        denied=g.handle("host_advance_creation_sequence",{"checkpoint":{}},"premature")
        self.assertEqual(denied["code"],"SEQUENCE_STEP_NOT_VALIDATED")
        self.assertEqual(g.sequence_cursor,0)
        validation=g.handle("host_validate",{"expected_revision":2},"host-val")
        self.assertTrue(validation["mission_complete"])
        checkpoint=g.handle("create_checkpoint",{},"cp")["checkpoint"]
        altered=copy.deepcopy(checkpoint);altered["semantic_fingerprint"]="0"*64
        denied=g.handle("host_advance_creation_sequence",{"checkpoint":altered},"tampered")
        self.assertEqual(denied["code"],"SEQUENCE_CHECKPOINT_MISMATCH")
        self.assertEqual(g.sequence_cursor,0)
        accepted=g.handle("host_advance_creation_sequence",{"checkpoint":checkpoint},"advance")
        self.assertTrue(accepted["ok"]);self.assertEqual(g.sequence_cursor,1)

    def test_pi_requested_validation_cannot_advance_host_sequence(self):
        g=self.gateway("MISSION-A.json",self.root/"host-validation")
        self.step(g,0,validate=False)
        pi_validation=g.handle("validate_mission",{"expected_revision":2},"pi-validation")
        self.assertTrue(pi_validation["mission_complete"])
        denied=g.handle("create_checkpoint",{},"pi-checkpoint")
        self.assertEqual(denied["code"],"SEQUENCE_STEP_NOT_VALIDATED")
        self.assertEqual(g.sequence_cursor,0)
        host_validation=g.handle("host_validate",{"expected_revision":2},"host-validation")
        self.assertTrue(host_validation["mission_complete"])
        self.assertTrue(g.handle("create_checkpoint",{},"host-checkpoint")["ok"])

    def test_prefix_recovery_after_two_validated_commits(self):
        source=self.gateway("MISSION-B.json",self.root/"prefix-source")
        for index in range(2):
            self.step(source,index);self.assertTrue(self.advance(source)["ok"])
        prefix=source.output/"constructive-operations.json"
        checkpoint=source.output/"checkpoint-step-02.json"
        recovered=self.gateway("MISSION-B.json",self.root/"prefix-recovered",sequence_stream_path=prefix,
            sequence_checkpoint_path=checkpoint)
        self.assertTrue(recovered.resume_verification["passed"])
        self.assertEqual(recovered.ws.get_revision(recovered.doc),3)
        self.assertEqual(recovered.sequence_cursor,2)
        self.assertEqual(recovered._function_handles(),["has_credit.function","is_minor.function"])
        for index in (2,3):
            self.step(recovered,index);self.assertTrue(self.advance(recovered)["ok"])
        self.assertTrue(recovered.sequence_complete)
        self.assertEqual(recovered.ws.get_revision(recovered.doc),5)

    def test_sequence_configuration_and_step_authorization_reject_without_mutation(self):
        valid=json.loads((RESULTS/"MISSION-A.json").read_text())
        for mutate,code in ((lambda x:x.update(extra=True),"SEQUENCE_CONTRACT_INVALID"),
                (lambda x:x.update(version=2),"SEQUENCE_CONTRACT_VERSION"),
                (lambda x:x["steps"].__setitem__(1,{**x["steps"][1],"expected_base_revision":4}),"SEQUENCE_REVISION_ORDER"),
                (lambda x:x["steps"][1].update(mission_id=x["steps"][0]["mission_id"]),"SEQUENCE_MISSION_ID"),
                (lambda x:x["steps"][0]["function"].update(return_type="string"),"SEQUENCE_FUNCTION_SIGNATURE"),
                (lambda x:x["steps"][1]["function"].update(portable_handle=x["steps"][0]["function"]["portable_handle"]),"SEQUENCE_FUNCTION_HANDLE")):
            with self.subTest(code=code):
                bad=copy.deepcopy(valid);mutate(bad)
                with self.assertRaises(WorkspaceError) as caught:cycle19.Cycle19Gateway(self.root/code,creation_sequence_path=self._write_config(bad,code))
                self.assertEqual(caught.exception.code,code)
        g=self.gateway("MISSION-A.json",self.root/"authorization")
        g.handle("discover_functions",{},"discover")
        before=(g.ws.get_revision(g.doc),{"functions":[]})
        unauthorized={"expected_revision":1,"name":"NOT_CONFIGURED","parameters":["X"],"body":preflight.fn_request("BOUNDED_SCORE")["body"]}
        result=g.handle("preview_create_function",unauthorized,"unauthorized")
        self.assertFalse(result["ok"]);self.assertEqual(result["code"],"MISSION_SIGNATURE")
        self.assertEqual((g.ws.get_revision(g.doc),{"functions":[]}),before)
        result=g.handle("preview_create_function",{"expected_revision":0,**preflight.fn_request("BOUNDED_SCORE")},"stale")
        self.assertEqual(result["code"],"STALE_REVISION")
        self.assertEqual((g.ws.get_revision(g.doc),{"functions":[]}),before)
        bad_signature=preflight.fn_request("BOUNDED_SCORE");bad_signature["parameters"]=["X","Y"]
        result=g.handle("preview_create_function",{"expected_revision":1,**bad_signature},"signature")
        self.assertEqual(result["code"],"MISSION_SIGNATURE")
        self.assertEqual((g.ws.get_revision(g.doc),{"functions":[]}),before)

    def test_dependency_discovery_order_arity_and_repeated_step(self):
        g=self.gateway("MISSION-A.json",self.root/"dependency-order")
        first=preflight.fn_request("BOUNDED_SCORE")
        premature=g.handle("preview_create_function",{"expected_revision":1,**preflight.fn_request("IS_PASSING")},"skip")
        self.assertEqual(premature["code"],"MISSION_SIGNATURE")
        self.assertEqual(g.ws.get_revision(g.doc),1)
        self.step(g,0);self.advance(g)
        correct=preflight.fn_request("IS_PASSING")
        undiscovered=g.handle("preview_create_function",{"expected_revision":2,**correct},"undiscovered")
        self.assertEqual(undiscovered["code"],"FUNCTION_NOT_DISCOVERED")
        self.assertEqual(g.ws.get_revision(g.doc),2)
        g.handle("discover_functions",{},"discover-callee")
        wrong_handle=copy.deepcopy(correct);wrong_handle["body"][1]["condition"]["left"]["function_handle"]="invented.function"
        denied=g.handle("preview_create_function",{"expected_revision":2,**wrong_handle},"wrong-handle")
        self.assertEqual(denied["code"],"MISSION_DEPENDENCY_REQUIRED")
        wrong_arity=copy.deepcopy(correct);wrong_arity["body"][1]["condition"]["left"]["arguments"]=[]
        denied=g.handle("preview_create_function",{"expected_revision":2,**wrong_arity},"wrong-arity")
        self.assertEqual(denied["code"],"INVALID_TYPED_EXPRESSION")
        self.assertEqual(g.ws.get_revision(g.doc),2)
        self.step(g,1)
        self.assertEqual(g.ws.get_revision(g.doc),3)
        self.advance(g)
        repeated=g.handle("preview_create_function",{"expected_revision":3,**first},"repeat")
        self.assertEqual(repeated["code"],"MISSION_SIGNATURE")

    def test_candidate_change_after_preview_is_rejected_atomically(self):
        g=self.gateway("MISSION-A.json",self.root/"changed-preview")
        g.handle("discover_functions",{},"discover")
        preview=g.handle("preview_create_function",{"expected_revision":1,**preflight.fn_request("BOUNDED_SCORE")},"preview")
        record=g.transactions._pending[preview["transaction_id"]]
        record["metadata"]["request"]["body"][2]["condition"]["right"]["value"]=99
        before=(g.ws.get_revision(g.doc),{"functions":[]})
        denied=g.handle("commit_preview",{"transaction_id":preview["transaction_id"]},"changed-commit")
        self.assertEqual(denied["code"],"PREVIEW_CANDIDATE_CHANGED")
        self.assertEqual((g.ws.get_revision(g.doc),{"functions":[]}),before)

    def test_old_preview_cannot_cross_a_sequence_step_boundary(self):
        g=self.gateway("MISSION-A.json",self.root/"preview-boundary")
        g.handle("discover_functions",{},"discover")
        first=g.handle("preview_create_function",{"expected_revision":1,**preflight.fn_request("BOUNDED_SCORE")},"preview")
        self.assertTrue(g.handle("commit_preview",{"transaction_id":first["transaction_id"]},"commit")["committed"])
        self.assertTrue(g.handle("host_validate",{"expected_revision":2},"validate")["mission_complete"])
        self.assertTrue(self.advance(g)["ok"])
        stale=g.handle("commit_preview",{"transaction_id":first["transaction_id"]},"old-step-commit")
        self.assertEqual(stale["code"],"PREVIEW_NOT_FOUND")
        self.assertEqual(g.ws.get_revision(g.doc),2)

    def test_tampered_recovery_history_is_never_attested(self):
        source=self.gateway("MISSION-B.json",self.root/"history-source")
        for index in range(3):self.step(source,index);self.advance(source)
        base_stream=json.loads((source.output/"constructive-operations.json").read_text())
        base_checkpoint=json.loads((source.output/"checkpoint-step-03.json").read_text())
        cases=[]
        reordered=copy.deepcopy(base_stream);reordered["operations"][0],reordered["operations"][1]=reordered["operations"][1],reordered["operations"][0]
        cases.append(("reordered",reordered,base_checkpoint,"SEQUENCE_RECOVERY_ORDER"))
        removed=copy.deepcopy(base_stream);removed["operations"].pop()
        cases.append(("removed",removed,base_checkpoint,"SEQUENCE_RECOVERY_PREFIX"))
        wrong_handles=copy.deepcopy(base_stream);wrong_handles["portable_handles"].pop()
        cases.append(("portable-map",wrong_handles,base_checkpoint,"REPLAY_HANDLE_LEDGER"))
        incomplete=copy.deepcopy(base_stream);incomplete["operations"].pop()
        cases.append(("incomplete-prefix",incomplete,base_checkpoint,"SEQUENCE_RECOVERY_PREFIX"))
        tampered_checkpoint=copy.deepcopy(base_checkpoint);tampered_checkpoint["semantic_fingerprint"]="f"*64
        cases.append(("fingerprint",base_stream,tampered_checkpoint,"SEQUENCE_RECOVERY_FINGERPRINT"))
        wrong_validation=copy.deepcopy(base_checkpoint);wrong_validation["last_validation"]["actor"]="pi_tool"
        cases.append(("non-host-validation",base_stream,wrong_validation,"SEQUENCE_RECOVERY_FINGERPRINT"))
        tampered_body=copy.deepcopy(base_stream);tampered_body["operations"][0]["arguments"]["body"][1]["condition"]["operator"]="<"
        cases.append(("body",tampered_body,base_checkpoint,"SEQUENCE_RECOVERY_ORACLE"))
        tampered_dependency=copy.deepcopy(base_stream)
        tampered_dependency["operations"][2]["arguments"]["body"][1]["condition"]["left"]["function_handle"]="invented.function"
        cases.append(("dependency",tampered_dependency,base_checkpoint,"REPLAY_HANDLE_MISSING"))
        for name,stream,checkpoint,expected_code in cases:
            with self.subTest(history=name):
                stream_path=self.root/f"{name}-stream.json";checkpoint_path=self.root/f"{name}-checkpoint.json"
                stream_path.write_text(json.dumps(stream));checkpoint_path.write_text(json.dumps(checkpoint))
                with self.assertRaises(WorkspaceError) as caught:
                    self.gateway("MISSION-B.json",self.root/f"rejected-{name}",sequence_stream_path=stream_path,
                        sequence_checkpoint_path=checkpoint_path)
                self.assertEqual(caught.exception.code,expected_code)

    def test_sequence_completion_blocks_an_extra_constructor(self):
        g=self.run_to_completion(self.gateway("MISSION-A.json",self.root/"complete"))
        before=g.ws.get_revision(g.doc)
        denied=g.handle("preview_create_function",{"expected_revision":before,**preflight.fn_request("HIGH_PRIORITY")},"extra")
        self.assertEqual(denied["code"],"SEQUENCE_COMPLETE")
        self.assertEqual(g.ws.get_revision(g.doc),before)

    def _write_config(self,value,name):
        path=self.root/f"{name}.json";path.write_text(json.dumps(value));return path

    def test_host_progression_is_not_a_pi_tool(self):
        extension=(PI/"extension.ts").read_text()
        self.assertNotIn('"host_advance_creation_sequence"',extension)
        evidence=RESULTS/"production-bridge-attempt-06/mission-a/step-01/dispatch-output.json"
        probe=json.loads(evidence.read_text())
        self.assertEqual(set(probe["active_tools"]),{
            "workspace_discover_functions","workspace_inspect_program","workspace_preview_function",
            "workspace_commit_preview","workspace_validate_mission"})
        self.assertNotIn("host_advance_creation_sequence",probe["active_tools"])

if __name__=="__main__":unittest.main()
