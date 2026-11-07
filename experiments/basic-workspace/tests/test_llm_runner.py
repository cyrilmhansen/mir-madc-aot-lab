import json
from http.server import BaseHTTPRequestHandler, HTTPServer
import pathlib
import sys
import threading
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "experiment"))
import llm_runner


class FixtureHandler(BaseHTTPRequestHandler):
    request_json = None
    auth_header = None

    def do_POST(self):
        size = int(self.headers["Content-Length"])
        FixtureHandler.request_json = json.loads(self.rfile.read(size))
        FixtureHandler.auth_header = self.headers.get("Authorization")
        body = json.dumps({"id": "fixture-1", "model": "fixture-model",
            "system_fingerprint": "local-fixture", "choices": [{"index": 0,
            "message": {"role": "assistant", "content": "done", "tool_calls": []},
            "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


class LlmHarnessTests(unittest.TestCase):
    def test_endpoint_timeout_is_saved_as_a_failed_model_attempt(self):
        class TimedOutEndpoint:
            last_request_bytes = 1234
            last_response_bytes = 0
            last_elapsed_ms = 180000.0

            def complete(self, _messages, _tools):
                raise TimeoutError("timed out")

        task = {"id": "construct_double", "instruction": "Create DOUBLE(X)=X*2.",
                "function": "DOUBLE", "arguments": [9], "expected_result": 18}
        runner = llm_runner.ToolRunner("text", source="")
        result = llm_runner.run_session(TimedOutEndpoint(), "text", task, runner,
            max_calls=10, max_iterations=4, construction=True)
        self.assertEqual("endpoint_error", result["status"])
        self.assertEqual(1, result["model_request_attempts"])
        self.assertEqual(0, result["model_turns"])
        self.assertEqual(1234, result["trace"][0]["request_bytes"])
        self.assertEqual(0, result["trace"][0]["response_wire_bytes"])
        self.assertEqual("TimeoutError: timed out", result["trace"][0]["endpoint_error"])

    def test_construction_text_arm_executes_same_numeric_mir_subset(self):
        runner = llm_runner.ToolRunner("text", source=(
            "FUNCTION DOUBLE(X)\nDOUBLE = X * 2\nEND FUNCTION\n"))
        result = runner.call("execute_program", {
            "function": "DOUBLE", "arguments": [9], "engine": "interp"})
        self.assertEqual(result["result"], 18.0)
        self.assertTrue(any(
            tool["function"]["name"] == "execute_program"
            for tool in llm_runner.CONSTRUCTION_TEXT_TOOLS))

    def test_openai_compatible_request_and_provider_metadata(self):
        server = HTTPServer(("127.0.0.1", 0), FixtureHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            endpoint = llm_runner.ChatEndpoint(
                f"http://127.0.0.1:{server.server_port}/v1/chat/completions",
                "fixture-model", "test-secret-never-logged", 0.0, 64, 2.0, 19, False)
            response, elapsed = endpoint.complete(
                [{"role": "user", "content": "fixture"}], llm_runner.TEXT_TOOLS)
            self.assertEqual("fixture-model", response["model"])
            self.assertEqual(10, response["usage"]["prompt_tokens"])
            self.assertGreaterEqual(elapsed, 0)
            self.assertEqual(19, FixtureHandler.request_json["seed"])
            self.assertEqual(1.0, FixtureHandler.request_json["top_p"])
            self.assertFalse(FixtureHandler.request_json["think"])
            self.assertEqual(64, FixtureHandler.request_json["max_tokens"])
            self.assertEqual("Bearer test-secret-never-logged", FixtureHandler.auth_header)
        finally:
            server.shutdown()
            server.server_close()

    def test_offline_fixture_is_not_counted_as_model_trial(self):
        result = llm_runner.fixture_test()
        self.assertTrue(result["protocol_pass"])
        self.assertTrue(result["not_an_llm_trial"])

    def test_text_patch_reports_ambiguous_and_stale_context(self):
        runner = llm_runner.ToolRunner("text", source="X=1\nX=2\n")
        ambiguous = runner.call("apply_patch", {"expected_version": 1, "old_text": "X", "new_text": "Y"})
        self.assertEqual("PATCH_CONTEXT_MATCH_COUNT: expected one exact context, found 2", ambiguous["message"])
        stale = runner.call("apply_patch", {"expected_version": 0, "old_text": "X=1", "new_text": "Y=1"})
        self.assertIn("STALE_VERSION", stale["message"])
        self.assertEqual("X=1\nX=2\n", runner.buffer)

    def test_scheduled_second_agent_gets_server_stale_rejection_before_refresh(self):
        class StaleAdapter:
            def call(self, name, arguments):
                if name == "workspace_commit":
                    raise llm_runner.RpcError("STALE_REVISION", "base revision is stale")
                return {"ok": True}

        runner = llm_runner.ToolRunner("semantic", adapter=StaleAdapter())
        runner.require_stale_commit_revision = 1
        blocked_refresh = runner.call("workspace_structure", {})
        self.assertEqual("SCHEDULER_STALE_CHECK_REQUIRED", blocked_refresh["code"])
        stale = runner.call("workspace_commit", {
            "expected_revision": 1,
            "operations": [{"operation": "rename_symbol", "symbol_id": "s", "new_name": "VALUE"}],
        })
        self.assertEqual("STALE_REVISION", stale["code"])
        self.assertTrue(runner.stale_commit_rejected)

    def test_source_text_payload_counts_only_returned_source_fields(self):
        calls = [
            {"name": "read_source", "result": {"text": "PRINT \"x\"\n"}},
            {"name": "workspace_symbols", "result": {"unique_symbol": {"name": "TOTAL"}}},
            {"name": "workspace_references", "result": {"items": [{"text": "X"}]}},
        ]
        self.assertEqual(len('PRINT "x"\n'.encode()) + len(b"TOTAL") + len(b"X"),
                         llm_runner.source_text_payload_bytes(calls))


if __name__ == "__main__":
    unittest.main()
