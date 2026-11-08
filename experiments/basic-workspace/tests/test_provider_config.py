import json
import pathlib
import sys
import threading
import unittest
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from experiment.provider_config import (ProviderConfigError, resolve_config,
                                        run_preflight, safe_metadata)


class PreflightHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"data": [{"id": "fixture-model"}]}).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(body)))
        self.end_headers(); self.wfile.write(body)

    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.seen_payload = request
        body = json.dumps({"choices": [{"message": {"tool_calls": [{
            "function": {"name": "preflight_ok", "arguments": "{\"ok\":true}"}}]},
            "finish_reason": "tool_calls"}], "usage": {"prompt_tokens": 12,
            "completion_tokens": 3, "prompt_tokens_details": {"cached_tokens": 0}}}).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(body)))
        self.end_headers(); self.wfile.write(body)

    def log_message(self, *_):
        pass


class ProviderConfigTests(unittest.TestCase):
    def test_legacy_and_current_alias_conflict_is_explicit(self):
        with self.assertRaisesRegex(ProviderConfigError, "conflicting environment"):
            resolve_config(pathlib.Path("/no/provider-config"), {
                "BASIC_WS_CHAT_COMPLETIONS_URL": "http://a/v1/chat/completions",
                "BASIC_WORKSPACE_LLM_ENDPOINT": "http://b/v1/chat/completions",
                "BASIC_WS_MODEL": "m"})

    def test_environment_overrides_local_candidate_and_requires_complete_pair(self):
        path = pathlib.Path("/no/provider-config")
        config = resolve_config(path, {"BASIC_WS_CHAT_COMPLETIONS_URL": "http://127.0.0.1:9/v1/chat/completions",
                                       "BASIC_WS_MODEL": "override-model",
                                       "BASIC_WS_MAX_OUTPUT_TOKENS": "77"})
        self.assertEqual("override-model", config["model"])
        self.assertEqual(77, config["max_output_tokens"])
        with self.assertRaisesRegex(ProviderConfigError, "model identifier"):
            resolve_config(path, {"BASIC_WS_CHAT_COMPLETIONS_URL": "http://127.0.0.1/v1/chat/completions"})

    def test_metadata_never_contains_endpoint_or_credentials(self):
        config = {"endpoint_url": "http://user:secret@192.168.1.1:1234/v1/chat/completions",
                  "model": "fixture-model"}
        metadata = safe_metadata(config)
        rendered = json.dumps(metadata)
        self.assertEqual("private", metadata["host_class"])
        self.assertNotIn("192.168.1.1", rendered)
        self.assertNotIn("secret", rendered)

    def test_preflight_confirms_model_and_actual_tool_call(self):
        server = HTTPServer(("127.0.0.1", 0), PreflightHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        endpoint = f"http://127.0.0.1:{server.server_port}/v1/chat/completions"
        config = {"endpoint_url": endpoint, "model": "fixture-model", "api_key": None,
                  "request_timeout_seconds": 2, "max_output_tokens": 1400,
                  "preflight_max_output_tokens": 1400, "temperature": 0.0,
                  "top_p": 1.0, "seed": None, "think": None}
        try:
            result = run_preflight(config, 2)
            self.assertEqual("verified_compatible", result["status"])
            self.assertTrue(all(row["ok"] for row in result["stages"]))
            self.assertEqual("auto", server.seen_payload["tool_choice"])
            self.assertEqual(1400, server.seen_payload["max_tokens"])
            self.assertNotIn("top_p", server.seen_payload)
            tool = server.seen_payload["tools"][0]["function"]
            self.assertEqual(["ok"], tool["parameters"]["required"])
            self.assertEqual("boolean", tool["parameters"]["properties"]["ok"]["type"])
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=2)

    def _mocked_preflight(self, response=None, error=None, models=None,
                          diagnose_required=False):
        from experiment import provider_config as pc

        class ModelListing:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def read(self, _limit):
                return json.dumps({"data": [{"id": x} for x in (models if models is not None else ["fixture-model"])]}).encode()

        class Endpoint:
            last_request_bytes = 200
            last_response_bytes = 80
            last_elapsed_ms = 4.0
            def complete(self, messages, tools, tool_choice="auto"):
                calls.append({"messages": messages, "tools": tools, "tool_choice": tool_choice})
                if callable(error): error(tool_choice)
                if error: raise error
                return response, 4.0

        calls = []
        config = {"endpoint_url": "http://127.0.0.1:7/v1/chat/completions",
                  "model": "fixture-model", "api_key": None, "request_timeout_seconds": 10,
                  "max_output_tokens": 1400, "preflight_max_output_tokens": 1400,
                  "temperature": 0.0, "top_p": 1.0, "seed": None, "think": None}
        with patch.object(pc, "urlopen", return_value=ModelListing()):
            result = run_preflight(config, endpoint_factory=lambda _: Endpoint(),
                                   diagnose_required=diagnose_required)
        return result, calls

    @staticmethod
    def _tool_response(name="preflight_ok", arguments='{"ok":true}', finish="tool_calls"):
        return {"choices": [{"finish_reason": finish, "message": {"tool_calls": [
            {"function": {"name": name, "arguments": arguments}}]}}],
            "usage": {"prompt_tokens": 50, "completion_tokens": 10,
                      "prompt_tokens_details": {"cached_tokens": 12}}}

    def test_mocked_preflight_classifies_success_truncation_timeout_malformed_and_wrong_tool(self):
        cases = [
            (self._tool_response(), None, "verified_compatible"),
            ({"choices": [{"finish_reason": "length", "message": {"content": "partial"}}]}, None,
             "output_limit_exhausted"),
            (None, TimeoutError("bounded timeout"), "request_timed_out"),
            (self._tool_response(arguments='{"ok":'), None, "invalid_tool_call_response"),
            (self._tool_response(name="other_tool"), None, "invalid_tool_call_response"),
        ]
        for response, error, expected in cases:
            with self.subTest(expected=expected):
                result, calls = self._mocked_preflight(response, error)
                self.assertEqual(expected, result["status"])
                self.assertEqual(1, len(calls))
                self.assertEqual("auto", calls[0]["tool_choice"])

    def test_mocked_preflight_marks_unavailable_model_without_chat_call(self):
        result, calls = self._mocked_preflight(self._tool_response(), models=["other-model"])
        self.assertEqual("model_unavailable", result["status"])
        self.assertEqual([], calls)

    def test_required_tool_choice_diagnostic_is_distinct_and_only_after_complete_bad_auto(self):
        from experiment import provider_config as pc
        class ModelListing:
            status=200
            def __enter__(self): return self
            def __exit__(self,*_): return False
            def read(self,_): return b'{"data":[{"id":"fixture-model"}]}'
        calls=[]
        class Endpoint:
            last_request_bytes=100;last_response_bytes=30;last_elapsed_ms=1
            def complete(self,_messages,_tools,tool_choice="auto"):
                calls.append(tool_choice)
                if tool_choice=="required":
                    raise RuntimeError("completion endpoint HTTP 400: option unsupported")
                return {"choices":[{"finish_reason":"stop","message":{"content":"no call"}}]},1
        cfg={"endpoint_url":"http://127.0.0.1:7/v1/chat/completions","model":"fixture-model",
             "request_timeout_seconds":10,"max_output_tokens":1400,"preflight_max_output_tokens":1400,
             "temperature":0,"top_p":1,"seed":None,"think":None}
        with patch.object(pc,"urlopen",return_value=ModelListing()):
            result=run_preflight(cfg,endpoint_factory=lambda _:Endpoint(),diagnose_required=True)
        self.assertEqual(["auto","required"],calls)
        self.assertEqual("optional_tool_choice_required_unsupported",
                         result["stages"][2]["classification"])


if __name__ == "__main__":
    unittest.main()
