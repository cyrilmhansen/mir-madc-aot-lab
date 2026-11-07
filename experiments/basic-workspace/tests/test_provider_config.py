import json
import pathlib
import sys
import threading
import unittest
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
                  "request_timeout_seconds": 2, "temperature": 0.0}
        try:
            result = run_preflight(config, 2)
            self.assertEqual("ok", result["status"])
            self.assertTrue(all(row["ok"] for row in result["stages"]))
            self.assertEqual("required", server.seen_payload["tool_choice"])
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
