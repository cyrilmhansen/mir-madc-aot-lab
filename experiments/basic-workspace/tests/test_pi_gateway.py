import importlib.util
import json
import socket
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location("pi_cycle16_gateway_test",ROOT/"pi-integration/gateway.py")
MOD=importlib.util.module_from_spec(SPEC);assert SPEC and SPEC.loader;sys.modules[SPEC.name]=MOD;SPEC.loader.exec_module(MOD)

BODY=[{"kind":"assign","target":{"kind":"result"},"expression":{"kind":"number","value":0}},
      {"kind":"if","condition":{"kind":"binary","operator":">=",
       "left":{"kind":"call","function_handle":"age_by_id.function","arguments":[{"kind":"local_ref","name":"ID"}]},
       "right":{"kind":"number","value":18}},
       "then":[{"kind":"assign","target":{"kind":"result"},"expression":{"kind":"number","value":1}}]}]

class PiGatewayTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="atlas-pi-gateway-test-",dir="/var/tmp")
        self.gateway=MOD.Cycle16Gateway(Path(self.temp.name))
    def tearDown(self):self.temp.cleanup()

    def test_seed_is_revision_four_and_preview_is_not_a_commit(self):
        found=self.gateway.handle("discover_functions",{},"discover")
        self.assertEqual(found["revision"],4)
        self.assertEqual(found["functions"][0]["name"],"AGE_BY_ID")
        result=self.gateway.handle("preview_create_function",{"expected_revision":4,"callee_handle":"age_by_id.function",
            "name":"IS_ADULT","parameters":["ID"],"body":BODY},"preview")
        self.assertTrue(result["ok"])
        self.assertEqual(self.gateway.ws.get_revision(self.gateway.doc),4)
        self.assertNotIn("FUNCTION IS_ADULT",self.gateway.ws.render_document(self.gateway.doc))

    def test_stale_revision_and_wrong_dependency_are_denied_without_mutation(self):
        self.gateway.handle("discover_functions",{},"discover")
        for params in ({"expected_revision":3,"callee_handle":"age_by_id.function","name":"IS_ADULT","parameters":["ID"],"body":BODY},
                       {"expected_revision":4,"callee_handle":"invented","name":"IS_ADULT","parameters":["ID"],"body":BODY}):
            response=self.gateway.handle("preview_create_function",params,"denied")
            self.assertFalse(response["ok"])
            self.assertEqual(self.gateway.ws.get_revision(self.gateway.doc),4)
        self.assertNotIn("FUNCTION IS_ADULT",self.gateway.ws.render_document(self.gateway.doc))

    def test_mission_rejects_wrong_function_name_and_unknown_method(self):
        self.gateway.handle("discover_functions",{},"discover")
        response=self.gateway.handle("preview_create_function",{"expected_revision":4,"callee_handle":"age_by_id.function",
            "name":"UNRELATED","parameters":["ID"],"body":BODY},"denied")
        self.assertFalse(response["ok"])
        self.assertEqual(self.gateway.ws.get_revision(self.gateway.doc),4)
        with self.assertRaises(Exception):self.gateway.handle("raw_source_replace",{},"bad-tool")

    def test_pi_event_deduplication_and_loopback_protocol_correlation(self):
        event={"type":"tool_execution_start","toolCallId":"call-1","toolName":"workspace_discover_functions"}
        self.assertFalse(self.gateway.record_pi(event)["deduplicated"])
        self.assertTrue(self.gateway.record_pi(event)["deduplicated"])
        server=MOD.Server(("127.0.0.1",0),self.gateway);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with socket.create_connection(server.server_address,timeout=2) as sock:
                sock.sendall(b'{"request_id":"correlation-1","method":"get_status","params":{}}\n')
                response=json.loads(sock.makefile("rb").readline())
            self.assertEqual(response["request_id"],"correlation-1")
            self.assertTrue(response["ok"]);self.assertEqual(response["result"]["revision"],4)
        finally:server.shutdown();server.server_close();thread.join(timeout=2)

    def test_invalid_preview_and_disconnected_client_do_not_mutate_workspace(self):
        self.gateway.handle("discover_functions",{},"discover")
        server=MOD.Server(("127.0.0.1",0),self.gateway);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            # An incomplete/disconnected request is not interpreted as a mutation.
            with socket.create_connection(server.server_address,timeout=2) as sock:
                sock.sendall(b'{"request_id":"cut-off","method":"preview_create_function"')
            with socket.create_connection(server.server_address,timeout=2) as sock:
                sock.sendall((json.dumps({"request_id":"bad-body","method":"preview_create_function","params":{
                    "expected_revision":4,"callee_handle":"age_by_id.function","name":"IS_ADULT",
                    "parameters":["ID"],"body":[{"kind":"call","value":{}}]}})+"\n").encode())
                response=json.loads(sock.makefile("rb").readline())
            self.assertTrue(response["ok"])
            self.assertEqual(response["request_id"],"bad-body")
            self.assertFalse(response["result"]["ok"])
            self.assertEqual(response["result"]["code"],"MISSION_BODY")
            self.assertEqual(self.gateway.ws.get_revision(self.gateway.doc),4)
            self.assertNotIn("FUNCTION IS_ADULT",self.gateway.ws.render_document(self.gateway.doc))
        finally:server.shutdown();server.server_close();thread.join(timeout=2)

    def test_oversized_bridge_frame_is_rejected_before_dispatch(self):
        server=MOD.Server(("127.0.0.1",0),self.gateway);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with socket.create_connection(server.server_address,timeout=3) as sock:
                sock.sendall(b' '* (MOD.Handler.MAX_LINE+1)+b'\n')
                response=json.loads(sock.makefile("rb").readline())
            self.assertFalse(response["ok"])
            self.assertEqual(response["error"]["code"],"FRAME_TOO_LARGE")
            self.assertEqual(self.gateway.ws.get_revision(self.gateway.doc),4)
        finally:server.shutdown();server.server_close();thread.join(timeout=2)

    def test_gateway_termination_is_detected_without_synthetic_commit(self):
        server=MOD.Server(("127.0.0.1",0),self.gateway);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        address=server.server_address
        server.shutdown();server.server_close();thread.join(timeout=2)
        with self.assertRaises(OSError):socket.create_connection(address,timeout=1)
        self.assertEqual(self.gateway.ws.get_revision(self.gateway.doc),4)
        self.assertFalse(self.gateway.gateway.committed)

if __name__=="__main__":unittest.main()
