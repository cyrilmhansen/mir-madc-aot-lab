import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location("cycle17_schema_gateway",ROOT/"pi-integration/gateway.py")
MOD=importlib.util.module_from_spec(SPEC);assert SPEC and SPEC.loader;sys.modules[SPEC.name]=MOD;SPEC.loader.exec_module(MOD)
RESULTS=ROOT/"pi-integration"/"results"/"cycle17-granularity"


def matches(schema,value):
    if "anyOf" in schema:return any(matches(branch,value) for branch in schema["anyOf"])
    t=schema.get("type")
    if t=="object":
        if not isinstance(value,dict):return False
        if any(k not in value for k in schema.get("required",[])):return False
        if schema.get("additionalProperties") is False and set(value)-set(schema.get("properties",{})):return False
        return all(k not in schema.get("properties",{}) or matches(s,value[k]) for k,s in schema.get("properties",{}).items() if k in value)
    if t=="array":
        return isinstance(value,list) and len(value)>=schema.get("minItems",0) and len(value)<=schema.get("maxItems",10**9) and all(matches(schema.get("items",{}),x) for x in value)
    if t=="string":return isinstance(value,str) and ("const" not in schema or value==schema["const"]) and ("enum" not in schema or value in schema["enum"])
    if t=="integer":return isinstance(value,int) and not isinstance(value,bool)
    if t=="number":return isinstance(value,(int,float)) and not isinstance(value,bool)
    if "const" in schema:return value==schema["const"]
    return True


def ops():
    return [
      {"op_id":"n18","kind":"define_number","handle":"e18","value":18},
      {"op_id":"neg","kind":"define_unary_expression","handle":"negative_eighteen","operator":"-","operand":"e18"},
      {"op_id":"id","kind":"define_parameter_ref","handle":"id_ref","name":"ID"},
      {"op_id":"call","kind":"define_function_call","handle":"age","function_handle":"age_by_id.function","arguments":["id_ref"]},
      {"op_id":"cmp","kind":"define_binary_expression","handle":"condition","operator":">=","left":"age","right":"e18"},
      {"op_id":"yes","kind":"define_number","handle":"yes_value","value":1},
      {"op_id":"no","kind":"define_number","handle":"no_value","value":0},
      {"op_id":"if","kind":"append_if_block","handle":"if_stmt","block":"root","condition":"condition","then_block":"then_block","else_block":"else_block"},
      {"op_id":"then","kind":"append_result_assignment","handle":"then_stmt","block":"then_block","expression":"yes_value"},
      {"op_id":"else","kind":"append_result_assignment","handle":"else_stmt","block":"else_block","expression":"no_value"},
    ]


class PiGranularitySchemaTests(unittest.TestCase):
    def test_exact_pi_15_incremental_schema_accepts_ops_and_gateway(self):
        schemas=json.loads((RESULTS/"preflight-incremental-unary"/"tool-schemas.json").read_text())
        names=[x["name"] for x in schemas]
        self.assertEqual(len(names),8)
        self.assertIn("workspace_apply_draft_operations",names)
        schema=next(x["parameters"] for x in schemas if x["name"]=="workspace_apply_draft_operations")
        payload={"draft_id":"draft_handle","expected_draft_revision":0,"operations":ops()}
        self.assertTrue(matches(schema,payload))
        extra=json.loads(json.dumps(payload));extra["operations"][0]["source_text"]="not allowed"
        self.assertFalse(matches(schema,extra))
        with tempfile.TemporaryDirectory(prefix="atlas-pi-schema-draft-",dir="/var/tmp") as td:
            gateway=MOD.Cycle16Gateway(Path(td),"incremental")
            gateway.handle("discover_functions",{},"discover")
            draft=gateway.handle("begin_function_draft",{"expected_revision":4,"name":"IS_ADULT",
                "parameters":["ID"],"callee_handle":"age_by_id.function"},"begin")
            payload["draft_id"]=draft["draft_id"]
            self.assertTrue(matches(schema,payload))
            response=gateway.handle("apply_draft_operations",payload,"apply")
            self.assertTrue(response["ok"])
            self.assertEqual(gateway.ws.get_revision(gateway.doc),4)

    def test_incremental_tool_schema_is_smaller_than_atomic_constructor_schema(self):
        atomic_path=RESULTS/"preflight-atomic"/"tool-schemas.json"
        incremental_path=RESULTS/"preflight-incremental"/"tool-schemas.json"
        expanded_path=RESULTS/"preflight-incremental-unary"/"tool-schemas.json"
        atomic=atomic_path.stat().st_size; incremental=incremental_path.stat().st_size
        expanded=expanded_path.stat().st_size
        self.assertEqual(len(json.loads(atomic_path.read_text())),5)
        self.assertEqual(len(json.loads(incremental_path.read_text())),8)
        self.assertEqual(len(json.loads(expanded_path.read_text())),8)
        self.assertLess(incremental,atomic)
        self.assertEqual((atomic,incremental,expanded),(20343,8709,9662))
        self.assertEqual(expanded-incremental,953)


if __name__=="__main__":unittest.main()
