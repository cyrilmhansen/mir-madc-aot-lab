import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PI=ROOT/"pi-integration"
SPEC=importlib.util.spec_from_file_location("cycle18_pi_gateway",PI/"gateway.py")
MOD=importlib.util.module_from_spec(SPEC);assert SPEC and SPEC.loader;sys.modules[SPEC.name]=MOD;SPEC.loader.exec_module(MOD)
RESULTS=PI/"results"/"cycle18-composition"
ADAPTER_SPEC=importlib.util.spec_from_file_location("cycle18_pi_schema_adapter",PI/"adapt_schema_failures.py")
ADAPTER=importlib.util.module_from_spec(ADAPTER_SPEC);assert ADAPTER_SPEC and ADAPTER_SPEC.loader;sys.modules[ADAPTER_SPEC.name]=ADAPTER;ADAPTER_SPEC.loader.exec_module(ADAPTER)


def schema_matches(schema,value):
    if "anyOf" in schema:return any(schema_matches(branch,value) for branch in schema["anyOf"])
    typ=schema.get("type")
    if typ=="object":
        if not isinstance(value,dict) or any(k not in value for k in schema.get("required",[])):return False
        if schema.get("additionalProperties") is False and set(value)-set(schema.get("properties",{})):return False
        return all(k not in schema.get("properties",{}) or schema_matches(s,value[k])
                   for k,s in schema.get("properties",{}).items() if k in value)
    if typ=="array":return isinstance(value,list) and len(value)>=schema.get("minItems",0) and len(value)<=schema.get("maxItems",10**9) and all(schema_matches(schema.get("items",{}),v) for v in value)
    if typ=="string":return isinstance(value,str) and ("const" not in schema or value==schema["const"]) and ("enum" not in schema or value in schema["enum"])
    if typ=="integer":return isinstance(value,int) and not isinstance(value,bool)
    if typ=="number":return isinstance(value,(int,float)) and not isinstance(value,bool)
    return "const" not in schema or value==schema["const"]


def atomic_body(function_handle="age_by_id.function"):
    body=[{"kind":"assign","target":{"kind":"result"},"expression":{"kind":"number","value":-1}}]
    for threshold,value in ((0,0),(18,1),(50,2)):
        body.append({"kind":"if","condition":{"kind":"binary","operator":">=",
            "left":{"kind":"call","function_handle":function_handle,"arguments":[{"kind":"local_ref","name":"ID"}]},
            "right":{"kind":"number","value":threshold}},
            "then":[{"kind":"assign","target":{"kind":"result"},"expression":{"kind":"number","value":value}}]})
    return body


def draft_operations():
    rows=[
      ("param","define_parameter_ref",{"handle":"id","name":"ID"}),
      ("age","define_function_call",{"handle":"age","function_handle":"age_by_id.function","arguments":["id"]}),
      ("minus_one","define_number",{"handle":"minus_one","value":-1}),
      ("n0","define_number",{"handle":"n0","value":0}),
      ("n18","define_number",{"handle":"n18","value":18}),
      ("n50","define_number",{"handle":"n50","value":50}),
      ("v0","define_number",{"handle":"v0","value":0}),
      ("v1","define_number",{"handle":"v1","value":1}),
      ("v2","define_number",{"handle":"v2","value":2}),
      ("c0","define_binary_expression",{"handle":"c0","operator":">=","left":"age","right":"n0"}),
      ("c18","define_binary_expression",{"handle":"c18","operator":">=","left":"age","right":"n18"}),
      ("c50","define_binary_expression",{"handle":"c50","operator":">=","left":"age","right":"n50"}),
      ("default","append_result_assignment",{"handle":"default","block":"root","expression":"minus_one"}),
      ("if0","append_if_block",{"handle":"if0","block":"root","condition":"c0","then_block":"then0","else_block":"else0"}),
      ("if18","append_if_block",{"handle":"if18","block":"root","condition":"c18","then_block":"then18","else_block":"else18"}),
      ("if50","append_if_block",{"handle":"if50","block":"root","condition":"c50","then_block":"then50","else_block":"else50"}),
      ("set0","append_result_assignment",{"handle":"set0","block":"then0","expression":"v0"}),
      ("set1","append_result_assignment",{"handle":"set1","block":"then18","expression":"v1"}),
      ("set2","append_result_assignment",{"handle":"set2","block":"then50","expression":"v2"}),
    ]
    return [{"op_id":f"op_{name}","kind":kind,**args} for name,kind,args in rows]


class PiCompositionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="atlas-cycle18-test-",dir="/var/tmp")
        self.output=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()

    def test_live_atomic_schema_accepts_category_and_a_different_generic_call_handle(self):
        schemas=json.loads((ROOT/"tests/fixtures/pi-cycle18/workspace_preview_function.json").read_text())["tools"]
        tool=next(x for x in schemas if x["name"]=="workspace_preview_function")
        params=tool["parameters"]
        request={"expected_revision":4,"callee_handle":"age_by_id.function","name":"AGE_CATEGORY",
            "parameters":["ID"],"body":atomic_body()}
        self.assertTrue(schema_matches(params,request))
        # A different discovered portable handle is syntactically the same kind
        # of reference; mission policy is checked by Python after schema validation.
        request["callee_handle"]="is_senior.function"
        request["body"]=atomic_body("is_senior.function")
        self.assertTrue(schema_matches(params,request))
        request["body"][0]["target"]={"kind":"parameter","name":"ID"}
        self.assertFalse(schema_matches(params,request))

    def test_live_draft_schema_is_flat_and_accepts_reused_call_handle(self):
        schemas=json.loads((ROOT/"tests/fixtures/pi-cycle18/workspace_apply_draft_operations.json").read_text())["tools"]
        tool=next(x for x in schemas if x["name"]=="workspace_apply_draft_operations")
        params=tool["parameters"]
        payload={"draft_id":"draft-local","expected_draft_revision":0,"operations":draft_operations()}
        self.assertTrue(schema_matches(params,payload))
        call=next(x for x in payload["operations"] if x["kind"]=="define_function_call")
        call["function_handle"]="is_senior.function"
        self.assertTrue(schema_matches(params,payload))
        self.assertEqual(params["properties"]["operations"]["maxItems"],32)

    def test_generic_handle_resolves_to_another_discovered_callable_and_mission_can_authorize_it(self):
        base=MOD.Cycle16Gateway(self.output,"atomic","category")
        listed=base.gateway.discover_functions()
        senior=[row for row in listed["functions"] if row["handle"]=="is_senior.function"]
        self.assertEqual(len(senior),1);self.assertEqual(senior[0]["parameter_count"],1)
        # The AGE_CATEGORY mission itself forbids this target.
        forbidden={"name":"AGE_CATEGORY","parameters":["ID"],"body":atomic_body("is_senior.function")}
        rejected=base.gateway.preview(forbidden,4,"is_senior.function")
        self.assertFalse(rejected["ok"])
        self.assertIn(rejected["code"],{"UNKNOWN_PORTABLE_FUNCTION","MISSION_DEPENDENCY_FORBIDDEN"})
        self.assertEqual(base.ws.get_revision(base.doc),4)
        # In a separately configured, narrow mission whose allowed dependency is
        # IS_SENIOR, the same generic call is resolved and previewed successfully.
        alt=MOD.senior.SeniorMissionGateway(base.ws,base.doc,base.aliases,base.base,
            {"mission_id":"cycle18-test-different-callee"},base.trace,"deterministic-test",
            function_name="CALL_PROBE",function_handle="call_probe.function",
            required_callee_handle="is_senior.function",
            discoverable_function_handles={"age_by_id.function","is_senior.function"})
        alt.discover_functions()
        allowed={"name":"CALL_PROBE","parameters":["ID"],"body":atomic_body("is_senior.function")}
        preview=alt.preview(allowed,4,"is_senior.function")
        self.assertTrue(preview["ok"],preview)
        self.assertEqual(preview["bound_callee_handle"],"is_senior.function")
        self.assertEqual(base.ws.get_revision(base.doc),4)

    def test_syntax_accepts_bounded_generic_call_shape_but_gateway_checks_discovered_arity(self):
        body=atomic_body()
        body[1]["condition"]["left"]["arguments"]=[
            {"kind":"local_ref","name":"ID"},{"kind":"number","value":101}]
        self.assertIsNone(MOD.Cycle16Gateway.typed_shape_error({
            "name":"AGE_CATEGORY","parameters":["ID"],"body":body}))
        gateway=MOD.Cycle16Gateway(self.output,"atomic","category")
        gateway.gateway.discover_functions()
        rejected=gateway.gateway.preview({"name":"AGE_CATEGORY","parameters":["ID"],"body":body},4,
            "age_by_id.function")
        self.assertFalse(rejected["ok"])
        self.assertIn(rejected["code"],{"MISSION_CALL_ARITY","MISSION_BODY"})
        self.assertEqual(gateway.ws.get_revision(gateway.doc),4)

    def test_observed_pi_schema_error_adapts_to_rejection_without_committed_change(self):
        events=[{"event_id":"initial","event_type":"initial","revision":4},
                {"event_id":"accepted","event_type":"preview","revision":4},
                {"event_id":"commit","event_type":"commit","revision":5,"snapshot":"COMMITTED"}]
        (self.output/"visual-events.jsonl").write_text("".join(json.dumps(x)+"\n" for x in events))
        pi=[{"type":"tool_execution_start","toolName":"workspace_preview_function",
             "toolCallId":"call-real-event","args":{"name":"AGE_CATEGORY","body":[{"kind":"if"}]}},
            {"type":"tool_execution_end","toolName":"workspace_preview_function",
             "toolCallId":"call-real-event","isError":True,
             "result":{"content":[{"type":"text","text":"schema rejected body[0].else"}]}}]
        (self.output/"pi-session.jsonl").write_text("".join(json.dumps(x)+"\n" for x in pi))
        self.assertEqual(ADAPTER.adapt(self.output),1)
        frames=[json.loads(line) for line in (self.output/"visual-events.jsonl").read_text().splitlines()]
        self.assertEqual([x["event_type"] for x in frames],["initial","rejection","preview","commit"])
        rejection=frames[1]
        self.assertEqual(rejection["source_event_ref"],"call-real-event")
        self.assertFalse(rejection["outcome"]["committed"])
        self.assertFalse(rejection["outcome"]["authoritative_workspace_changed"])
        self.assertEqual(frames[-1]["snapshot"],"COMMITTED")
        self.assertEqual(ADAPTER.adapt(self.output),0)
        self.assertEqual(len((self.output/"visual-events.jsonl").read_text().splitlines()),4)

    def test_incremental_category_graph_commits_atomically_and_passes_full_oracle(self):
        gateway=MOD.Cycle16Gateway(self.output,"incremental","category")
        gateway.gateway.discover_functions()
        start=gateway.handle("begin_function_draft",{"expected_revision":4,"name":"AGE_CATEGORY",
            "parameters":["ID"],"callee_handle":"age_by_id.function"},"begin")
        self.assertTrue(start["ok"],start)
        result=gateway.handle("apply_draft_operations",{"draft_id":start["draft_id"],
            "expected_draft_revision":0,"operations":draft_operations()},"batch")
        self.assertTrue(result["ok"],result);self.assertEqual(result["draft_revision"],19)
        self.assertEqual(gateway.ws.get_revision(gateway.doc),4)
        preview=gateway.handle("preview_function_draft",{"draft_id":start["draft_id"],
            "expected_revision":4,"expected_draft_revision":19},"preview")
        self.assertTrue(preview["ok"],preview);self.assertEqual(gateway.ws.get_revision(gateway.doc),4)
        committed=gateway.handle("commit_preview",{"transaction_id":preview["transaction_id"]},"commit")
        self.assertTrue(committed["committed"]);self.assertEqual(committed["revision"],5)
        validation=gateway.validate_category(5)
        self.assertTrue(validation["mission_complete"],validation)
        self.assertTrue(validation["boundary_oracle"]["passed"])
        self.assertTrue(validation["replay"]["passed"])
        frames=[json.loads(line) for line in (self.output/"visual-events.jsonl").read_text().splitlines() if line]
        steps=[x for x in frames if x.get("title","").startswith("Draft step ")]
        self.assertEqual(len(steps),19)
        self.assertEqual(gateway.ws.get_revision(gateway.doc),5)


if __name__=="__main__":unittest.main()
