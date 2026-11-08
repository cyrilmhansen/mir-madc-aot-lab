import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
INTEGRATION=ROOT/"pi-integration"
SCHEMA_PATH=INTEGRATION/"results/preflight-08/tool-schemas.json"
FAILURE_HISTORY=INTEGRATION/"results/real-pi-01/history.jsonl"
SPEC=importlib.util.spec_from_file_location("pi_schema_gateway_test",INTEGRATION/"gateway.py")
MOD=importlib.util.module_from_spec(SPEC);assert SPEC and SPEC.loader;sys.modules[SPEC.name]=MOD;SPEC.loader.exec_module(MOD)

KNOWN_GOOD={"name":"IS_ADULT","parameters":["ID"],"body":[
    {"kind":"assign","target":{"kind":"result"},"expression":{"kind":"number","value":0}},
    {"kind":"if","condition":{"kind":"binary","operator":">=",
      "left":{"kind":"call","function_handle":"age_by_id.function",
              "arguments":[{"kind":"local_ref","name":"ID"}]},
      "right":{"kind":"number","value":18}},
     "then":[{"kind":"assign","target":{"kind":"result"},"expression":{"kind":"number","value":1}}]}]}

def validate(schema,value,path="$",depth=0):
    """Small deterministic validator for keywords present in captured Pi tool JSON Schema."""
    if depth>32:return [f"{path}: schema recursion limit"]
    if "anyOf" in schema:
        if any(not validate(option,value,path,depth+1) for option in schema["anyOf"]):return []
        return [f"{path}: no anyOf branch matched"]
    errors=[]
    kind=schema.get("type")
    if kind=="object":
        if not isinstance(value,dict):return [f"{path}: expected object"]
        for key in schema.get("required",[]):
            if key not in value:errors.append(f"{path}.{key}: required")
        props=schema.get("properties",{})
        for key,child in props.items():
            if key in value:errors.extend(validate(child,value[key],f"{path}.{key}",depth+1))
        if schema.get("additionalProperties") is False:
            for key in value.keys()-props.keys():errors.append(f"{path}.{key}: additional property")
    elif kind=="array":
        if not isinstance(value,list):return [f"{path}: expected array"]
        if len(value)<schema.get("minItems",0) or len(value)>schema.get("maxItems",10**9):errors.append(f"{path}: item count")
        for i,item in enumerate(value):errors.extend(validate(schema.get("items",{}),item,f"{path}[{i}]",depth+1))
    elif kind=="string":
        if not isinstance(value,str):return [f"{path}: expected string"]
    elif kind=="integer":
        if isinstance(value,bool) or not isinstance(value,int):return [f"{path}: expected integer"]
    elif kind=="number":
        if isinstance(value,bool) or not isinstance(value,(int,float)):return [f"{path}: expected number"]
    if "const" in schema and value!=schema["const"]:errors.append(f"{path}: const mismatch")
    if "enum" in schema and value not in schema["enum"]:errors.append(f"{path}: enum mismatch")
    return errors

class PiTypedSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tools=json.loads(SCHEMA_PATH.read_text())
        cls.preview=next(row["parameters"] for row in cls.tools if row["name"]=="workspace_preview_function")

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="atlas-pi-schema-",dir="/var/tmp")
        self.gateway=MOD.Cycle16Gateway(Path(self.temp.name))
        self.gateway.handle("discover_functions",{},"discover")
    def tearDown(self):self.temp.cleanup()

    def test_captured_active_pi_schema_is_typed_bounded_and_matches_inventory(self):
        inventory=json.loads((SCHEMA_PATH.parent/"tool-inventory.json").read_text())
        self.assertEqual(inventory["tools"],["workspace_discover_functions","workspace_inspect_program",
            "workspace_preview_function","workspace_commit_preview","workspace_validate_mission"])
        self.assertEqual(self.preview["properties"]["body"]["items"].get("type"),None)
        self.assertNotEqual(self.preview["properties"]["body"]["items"],{})
        self.assertIn("anyOf",self.preview["properties"]["body"]["items"])
        self.assertNotIn("$ref",json.dumps(self.preview))
        self.assertTrue(self.preview["additionalProperties"] is False)
        self.assertTrue(self.preview["properties"]["body"]["items"].get("anyOf"))
        body_branches=self.preview["properties"]["body"]["items"]["anyOf"]
        self.assertEqual({b["properties"]["kind"]["const"] for b in body_branches},{"assign","if"})
        encoded=json.dumps(self.preview)
        for required_kind in ('"const": "number"','"const": "local_ref"','"const": "binary"','"const": "call"'):
            self.assertIn(required_kind,encoded)
        self.assertIn('"const": "age_by_id.function"',encoded)
        self.assertIn('"const": "result"',encoded)
        self.assertIn('"enum": ["+", "-", "*", "/", "=", "<>", "<", "<=", ">", ">="]',encoded)

    def test_known_good_nested_call_and_if_matches_exact_pi_schema_and_gateway(self):
        payload={"expected_revision":4,"callee_handle":"age_by_id.function",**copy.deepcopy(KNOWN_GOOD)}
        self.assertEqual(validate(self.preview,payload),[])
        preview=self.gateway.handle("preview_create_function",payload,"valid-preview")
        self.assertTrue(preview["ok"],preview)
        self.assertEqual(self.gateway.ws.get_revision(self.gateway.doc),4)
        self.assertNotIn("FUNCTION IS_ADULT",self.gateway.ws.render_document(self.gateway.doc))

    def test_all_eight_cycle16_rejected_bodies_fail_schema_and_gateway_without_mutation(self):
        rows=[json.loads(line) for line in FAILURE_HISTORY.read_text().splitlines()]
        args=[row["operation_envelope"]["arguments"] for row in rows
              if row.get("phase")=="cycle16-real-pi-agent" and row.get("event")=="operation_proposed"]
        self.assertEqual(len(args),8)
        for i,request in enumerate(args):
            payload={"expected_revision":4,"callee_handle":"age_by_id.function",**request}
            self.assertTrue(validate(self.preview,payload),f"old malformed proposal {i} unexpectedly matched Pi schema")
            response=self.gateway.handle("preview_create_function",payload,f"old-{i}")
            self.assertFalse(response["ok"])
            self.assertTrue(response["revision_unchanged"] if "revision_unchanged" in response else response["revision"]==4)
            self.assertEqual(self.gateway.ws.get_revision(self.gateway.doc),4)
            self.assertNotIn("FUNCTION IS_ADULT",self.gateway.ws.render_document(self.gateway.doc))

    def test_actionable_shape_diagnostic_and_policy_denial_are_separate(self):
        malformed=copy.deepcopy(KNOWN_GOOD);malformed["body"][0]["target"]="result"
        response=self.gateway.handle("preview_create_function",{"expected_revision":4,"callee_handle":"age_by_id.function",**malformed},"bad-target")
        self.assertEqual(response["code"],"INVALID_TYPED_STATEMENT")
        self.assertEqual(response["path"],"body[0].target")
        self.assertEqual(response["expected"],{"kind":"result"})
        self.assertEqual(response["received_kind"],"str")
        self.assertTrue(response["revision_unchanged"])
        wrong_handle=copy.deepcopy(KNOWN_GOOD)
        wrong_handle["body"][1]["condition"]["left"]["function_handle"]="wrong.function"
        wrong_payload={"expected_revision":4,"callee_handle":"age_by_id.function",**wrong_handle}
        self.assertTrue(validate(self.preview,wrong_payload))
        denied=self.gateway.handle("preview_create_function",{"expected_revision":4,"callee_handle":"age_by_id.function",**wrong_handle},"wrong-handle")
        self.assertEqual(denied["code"],"UNKNOWN_PORTABLE_FUNCTION")
        self.assertNotIn("path",denied)
        extra=copy.deepcopy(KNOWN_GOOD);extra["body"][0]["source_text"]="FUNCTION..."
        extra_payload={"expected_revision":4,"callee_handle":"age_by_id.function",**extra}
        self.assertTrue(validate(self.preview,extra_payload))
        rejected=self.gateway.handle("preview_create_function",extra_payload,"extra-field")
        self.assertEqual(rejected["code"],"INVALID_TYPED_STATEMENT")
        self.assertEqual(self.gateway.ws.get_revision(self.gateway.doc),4)

if __name__=="__main__":unittest.main()
