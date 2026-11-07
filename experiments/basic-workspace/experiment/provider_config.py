"""Small local configuration and bounded preflight for OpenAI-compatible models.

The provider file is intentionally local and git-ignored. Reports contain only
endpoint class/path metadata, never its URL or credentials.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen


DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / ".agent-provider.json"
ENDPOINT_ALIASES = ("BASIC_WS_CHAT_COMPLETIONS_URL", "BASIC_WORKSPACE_LLM_ENDPOINT")
MODEL_ALIASES = ("BASIC_WS_MODEL", "BASIC_WORKSPACE_LLM_MODEL")


class ProviderConfigError(ValueError):
    pass


def _alias_value(env: dict[str, str], aliases: tuple[str, ...], label: str) -> str | None:
    values = {env[key].strip() for key in aliases if env.get(key, "").strip()}
    if len(values) > 1:
        raise ProviderConfigError(f"conflicting environment overrides for {label}: {', '.join(aliases)}")
    return next(iter(values), None)


def resolve_config(path: Path = DEFAULT_CONFIG, env: dict[str, str] | None = None) -> dict[str, Any]:
    env = dict(os.environ if env is None else env)
    config_path_override = env.get("BASIC_WS_PROVIDER_CONFIG")
    path = Path(config_path_override).expanduser() if config_path_override else path
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ProviderConfigError(f"cannot read provider configuration ({type(exc).__name__})") from None
        if not isinstance(raw, dict):
            raise ProviderConfigError("provider configuration must be a JSON object")
    else:
        raw = {}

    endpoint = _alias_value(env, ENDPOINT_ALIASES, "endpoint") or raw.get("endpoint_url")
    model = _alias_value(env, MODEL_ALIASES, "model") or raw.get("model")
    if not isinstance(endpoint, str) or not endpoint.strip():
        raise ProviderConfigError("chat-completions endpoint is missing")
    if not isinstance(model, str) or not model.strip():
        raise ProviderConfigError("model identifier is missing")
    parsed = urlsplit(endpoint)
    if (parsed.scheme not in ("http", "https") or not parsed.netloc
            or not parsed.path.endswith("/chat/completions") or parsed.username or parsed.password
            or parsed.query or parsed.fragment):
        raise ProviderConfigError("endpoint_url must be an HTTP(S) chat-completions URL")

    def env_override(name: str, key: str, cast: Any) -> Any:
        return cast(env[name]) if name in env and env[name] != "" else raw.get(key)

    def parse_bool(value: str) -> bool:
        normalized = value.strip().lower()
        if normalized in ("1", "true", "yes"):
            return True
        if normalized in ("0", "false", "no"):
            return False
        raise ValueError("invalid boolean")

    try:
        timeout = env_override("BASIC_WS_TIMEOUT_SECONDS", "request_timeout_seconds", float)
        max_tokens = env_override("BASIC_WS_MAX_OUTPUT_TOKENS", "max_output_tokens", int)
        temperature = env_override("BASIC_WS_TEMPERATURE", "temperature", float)
        top_p = env_override("BASIC_WS_TOP_P", "top_p", float)
        seed = env_override("BASIC_WS_SEED", "seed", int)
        think = env_override("BASIC_WS_THINK", "think", parse_bool)
    except (TypeError, ValueError):
        raise ProviderConfigError("sampling or timeout configuration has an invalid type") from None
    try:
        timeout = float(timeout) if timeout is not None else None
        max_tokens = int(max_tokens) if max_tokens is not None else None
        temperature = float(temperature) if temperature is not None else None
        top_p = float(top_p) if top_p is not None else None
        seed = int(seed) if seed is not None else None
    except (TypeError, ValueError, OverflowError):
        raise ProviderConfigError("sampling or timeout configuration has an invalid type") from None
    timeout = 60.0 if timeout is None else timeout
    max_tokens = 1200 if max_tokens is None else max_tokens
    temperature = 0.0 if temperature is None else temperature
    top_p = 1.0 if top_p is None else top_p
    if timeout <= 0 or timeout > 600:
        raise ProviderConfigError("request_timeout_seconds must be in (0, 600]")
    if max_tokens < 1 or max_tokens > 32768:
        raise ProviderConfigError("max_output_tokens must be in [1, 32768]")
    if not 0 <= temperature <= 2 or not 0 < top_p <= 1:
        raise ProviderConfigError("temperature or top_p is outside its supported range")
    if think is not None and not isinstance(think, bool):
        raise ProviderConfigError("think must be a JSON boolean")
    key_env = env.get("BASIC_WS_API_KEY_ENV", raw.get("api_key_env"))
    if key_env is not None and (not isinstance(key_env, str) or not key_env.isidentifier()):
        raise ProviderConfigError("api_key_env must name an environment variable")
    direct_keys = [env[name] for name in ("BASIC_WS_API_KEY", "BASIC_WORKSPACE_LLM_API_KEY") if env.get(name)]
    if len(set(direct_keys)) > 1:
        raise ProviderConfigError("conflicting direct API-key environment overrides")
    api_key = (direct_keys[0] if direct_keys else env.get(key_env, "")) if key_env or direct_keys else ""
    return {"endpoint_url": endpoint, "model": model, "api_key": api_key or None,
            "api_key_configured": bool(api_key), "api_key_env": key_env,
            "request_timeout_seconds": timeout, "max_output_tokens": max_tokens,
            "temperature": temperature, "top_p": top_p, "seed": seed,
            "think": think,
            "config_path": str(path)}


def safe_metadata(config: dict[str, Any]) -> dict[str, str]:
    parts = urlsplit(config["endpoint_url"])
    host = parts.hostname or ""
    import ipaddress
    try:
        address = ipaddress.ip_address(host)
        host_class = "loopback" if address.is_loopback else "private" if address.is_private else "public"
    except ValueError:
        host_class = "named-host"
    return {"scheme": parts.scheme, "host_class": host_class,
            "api_path": "chat/completions", "model": config["model"]}


def _models_url(endpoint: str) -> str:
    parts = urlsplit(endpoint)
    path = parts.path[: -len("chat/completions")].rstrip("/") + "/models"
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def run_preflight(config: dict[str, Any], probe_timeout: float = 45.0) -> dict[str, Any]:
    """Check model listing and one bounded required tool call; never retry."""
    result: dict[str, Any] = {"schema": "basic-workspace.provider-preflight", "version": 1,
                              "provider": safe_metadata(config), "configured_timeout_seconds": config["request_timeout_seconds"],
                              "probe_output_token_limit": 128, "stages": []}
    started = time.monotonic()
    try:
        with urlopen(Request(_models_url(config["endpoint_url"]), method="GET"),
                     timeout=min(probe_timeout, config["request_timeout_seconds"])) as response:
            body = json.loads(response.read(2 * 1024 * 1024 + 1))
        available = [item.get("id") for item in body.get("data", []) if isinstance(item, dict)]
        matched = config["model"] in available
        result["stages"].append({"name": "model_listing", "ok": matched,
                                 "http_status": 200, "available_model_count": len(available),
                                 "requested_model_available": matched})
        if not matched:
            result.update(status="failed", failure_stage="model_listing", elapsed_ms=round((time.monotonic()-started)*1000, 1))
            return result
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        result["stages"].append({"name": "model_listing", "ok": False,
                                 "error_type": type(exc).__name__,
                                 "http_status": getattr(exc, "code", None)})
        result.update(status="failed", failure_stage="model_listing", elapsed_ms=round((time.monotonic()-started)*1000, 1))
        return result

    payload = {"model": config["model"], "messages": [
        {"role": "system", "content": "Call the required tool. Do not explain."},
        {"role": "user", "content": "Call preflight_ok with ok=true."}],
        "tools": [{"type": "function", "function": {"name": "preflight_ok",
            "description": "Confirms tool calling is available", "parameters": {
                "type": "object", "properties": {"ok": {"type": "boolean"}},
                "required": ["ok"], "additionalProperties": False}}}],
        "tool_choice": "required", "temperature": 0, "max_tokens": 128}
    headers = {"Content-Type": "application/json"}
    if config.get("api_key"):
        headers["Authorization"] = "Bearer " + config["api_key"]
    request_bytes = len(json.dumps(payload, separators=(",", ":")).encode())
    probe_started = time.monotonic()
    try:
        request = Request(config["endpoint_url"], data=json.dumps(payload).encode(), headers=headers, method="POST")
        with urlopen(request, timeout=min(probe_timeout, config["request_timeout_seconds"])) as response:
            raw = response.read(1024 * 1024 + 1)
            data = json.loads(raw)
            choice = data.get("choices", [{}])[0]
            calls = choice.get("message", {}).get("tool_calls", [])
        valid = bool(calls) and calls[0].get("function", {}).get("name") == "preflight_ok"
        result["stages"].append({"name": "tool_call", "ok": valid, "http_status": response.status,
            "tool_call_received": bool(calls), "finish_reason": choice.get("finish_reason"),
            "request_bytes": request_bytes, "response_bytes": len(raw),
            "elapsed_ms": round((time.monotonic()-probe_started)*1000, 1), "usage": data.get("usage")})
        result["status"] = "ok" if valid else "failed"
        if not valid:
            result["failure_stage"] = "tool_call"
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, IndexError, KeyError) as exc:
        result["stages"].append({"name": "tool_call", "ok": False,
            "error_type": type(exc).__name__, "http_status": getattr(exc, "code", None),
            "elapsed_ms": round((time.monotonic()-probe_started)*1000, 1), "request_bytes": request_bytes})
        result.update(status="failed", failure_stage="tool_call")
    result["elapsed_ms"] = round((time.monotonic()-started)*1000, 1)
    return result


def make_chat_endpoint(config: dict[str, Any]):
    # Local import avoids coupling configuration parsing to the agent runner.
    from experiment.llm_runner import ChatEndpoint
    return ChatEndpoint(config["endpoint_url"], config["model"], config.get("api_key"),
                        config["temperature"], config["max_output_tokens"],
                        config["request_timeout_seconds"], config.get("seed"),
                        config.get("think"), config["top_p"])
