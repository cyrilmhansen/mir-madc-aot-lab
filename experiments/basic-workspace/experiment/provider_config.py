"""Small local configuration and bounded preflight for OpenAI-compatible models.

The provider file is intentionally local and git-ignored. Reports contain only
endpoint class/path metadata, never its URL or credentials.
"""
from __future__ import annotations

import json
import os
import re
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
        preflight_tokens = env_override("BASIC_WS_PREFLIGHT_MAX_OUTPUT_TOKENS", "preflight_max_output_tokens", int)
        temperature = env_override("BASIC_WS_TEMPERATURE", "temperature", float)
        top_p = env_override("BASIC_WS_TOP_P", "top_p", float)
        seed = env_override("BASIC_WS_SEED", "seed", int)
        think = env_override("BASIC_WS_THINK", "think", parse_bool)
    except (TypeError, ValueError):
        raise ProviderConfigError("sampling or timeout configuration has an invalid type") from None
    try:
        timeout = float(timeout) if timeout is not None else None
        max_tokens = int(max_tokens) if max_tokens is not None else None
        preflight_tokens = int(preflight_tokens) if preflight_tokens is not None else None
        temperature = float(temperature) if temperature is not None else None
        top_p = float(top_p) if top_p is not None else None
        seed = int(seed) if seed is not None else None
    except (TypeError, ValueError, OverflowError):
        raise ProviderConfigError("sampling or timeout configuration has an invalid type") from None
    timeout = 60.0 if timeout is None else timeout
    max_tokens = 1200 if max_tokens is None else max_tokens
    preflight_tokens = min(max_tokens, 1400) if preflight_tokens is None else preflight_tokens
    temperature = 0.0 if temperature is None else temperature
    top_p = 1.0 if top_p is None else top_p
    if timeout <= 0 or timeout > 600:
        raise ProviderConfigError("request_timeout_seconds must be in (0, 600]")
    if max_tokens < 1 or max_tokens > 32768:
        raise ProviderConfigError("max_output_tokens must be in [1, 32768]")
    if preflight_tokens < 1 or preflight_tokens > 32768:
        raise ProviderConfigError("preflight_max_output_tokens must be in [1, 32768]")
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
            "preflight_max_output_tokens": preflight_tokens,
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


def _usage(response: dict[str, Any]) -> dict[str, int | None]:
    usage = response.get("usage") or {}
    details = usage.get("prompt_tokens_details") or {}
    completion_details = usage.get("completion_tokens_details") or {}
    return {"prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "cached_prompt_tokens": details.get("cached_tokens"),
            "reasoning_tokens": completion_details.get("reasoning_tokens")}


def _tool_call_valid(response: dict[str, Any]) -> tuple[bool, str, str | None]:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return False, "invalid_tool_call_response", "missing_choice"
    choice = choices[0]
    message = choice.get("message")
    if not isinstance(message, dict):
        return False, "invalid_tool_call_response", choice.get("finish_reason")
    calls = message.get("tool_calls")
    if not isinstance(calls, list) or len(calls) != 1 or not isinstance(calls[0], dict):
        return False, "invalid_tool_call_response", choice.get("finish_reason")
    function = calls[0].get("function")
    if not isinstance(function, dict) or function.get("name") != "preflight_ok":
        return False, "invalid_tool_call_response", choice.get("finish_reason")
    arguments = function.get("arguments")
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            return False, "invalid_tool_call_response", choice.get("finish_reason")
    if not isinstance(arguments, dict) or set(arguments) != {"ok"} or arguments["ok"] is not True:
        return False, "invalid_tool_call_response", choice.get("finish_reason")
    return True, "verified_compatible", choice.get("finish_reason")


def _probe_tool_call(config: dict[str, Any], timeout: float, tool_choice: str,
                     endpoint_factory: Any) -> dict[str, Any]:
    from experiment.llm_runner import schema
    probe_config = dict(config)
    probe_config["request_timeout_seconds"] = timeout
    probe_config["max_output_tokens"] = config.get("preflight_max_output_tokens",
                                                    min(config.get("max_output_tokens", 1400), 1400))
    endpoint = endpoint_factory(probe_config)
    tools = [schema("preflight_ok", "Return the required boolean confirmation.",
                    {"ok": {"type": "boolean"}}, ["ok"])]
    messages = [{"role": "system", "content": "For this protocol check, call preflight_ok exactly once with ok=true."},
                {"role": "user", "content": "Use the preflight_ok tool now."}]
    started = time.monotonic()
    try:
        response, _ = endpoint.complete(messages, tools, tool_choice=tool_choice)
        valid, classification, finish_reason = _tool_call_valid(response)
        if not valid and finish_reason == "length":
            classification = "output_limit_exhausted"
        return {"ok": valid, "classification": classification,
                "tool_choice": tool_choice, "finish_reason": finish_reason,
                "usage": _usage(response),
                "request_bytes": getattr(endpoint, "last_request_bytes", None),
                "response_bytes": getattr(endpoint, "last_response_bytes", None),
                "latency_ms": getattr(endpoint, "last_elapsed_ms", round((time.monotonic()-started)*1000, 1))}
    except TimeoutError:
        classification = "request_timed_out"
    except URLError:
        classification = "provider_unavailable"
    except RuntimeError as exc:
        message = str(exc)
        match = re.search(r"HTTP (\d{3})", message)
        http_status = int(match.group(1)) if match else None
        if http_status in (400, 422):
            classification = "invalid_tool_call_response"
        elif http_status is not None and http_status >= 500 or "endpoint unavailable" in message:
            classification = "provider_unavailable"
        else:
            classification = "invalid_tool_call_response"
    except (ValueError, TypeError, KeyError, IndexError):
        classification = "invalid_tool_call_response"
    return {"ok": False, "classification": classification,
            "tool_choice": tool_choice, "finish_reason": None, "usage": None,
            "http_status": locals().get("http_status"),
            "request_bytes": getattr(locals().get("endpoint"), "last_request_bytes", None),
            "response_bytes": getattr(locals().get("endpoint"), "last_response_bytes", None),
            "latency_ms": getattr(locals().get("endpoint"), "last_elapsed_ms",
                                   round((time.monotonic()-started)*1000, 1))}


def run_preflight(config: dict[str, Any], probe_timeout: float | None = None,
                  diagnose_required: bool = False, endpoint_factory: Any = None) -> dict[str, Any]:
    """Check model listing, then match the agent runner's auto-tool request.

    A second, deliberately different ``tool_choice=required`` request is sent
    only when requested and the compatibility response was complete but invalid.
    Timeouts and output truncation never trigger a retry.
    """
    from experiment.provider_config import make_chat_endpoint
    endpoint_factory = endpoint_factory or make_chat_endpoint
    timeout = config["request_timeout_seconds"] if probe_timeout is None else float(probe_timeout)
    if timeout <= 0 or timeout > 600:
        raise ProviderConfigError("probe timeout override must be in (0, 600]")
    result: dict[str, Any] = {"schema": "basic-workspace.provider-preflight", "version": 2,
                              "provider": safe_metadata(config),
                              "configured_timeout_seconds": config["request_timeout_seconds"],
                              "probe_timeout_seconds": timeout,
                              "probe_output_token_limit": config.get("preflight_max_output_tokens",
                                  min(config.get("max_output_tokens", 1400), 1400)), "stages": []}
    started = time.monotonic()
    try:
        with urlopen(Request(_models_url(config["endpoint_url"]), method="GET"), timeout=timeout) as response:
            raw_models = response.read(2 * 1024 * 1024 + 1)
        if len(raw_models) > 2 * 1024 * 1024:
            raise ValueError("model listing exceeded response limit")
        body = json.loads(raw_models)
        available = [item.get("id") for item in body.get("data", []) if isinstance(item, dict)]
        matched = config["model"] in available
        result["stages"].append({"name": "model_listing", "ok": matched,
                                 "http_status": 200, "available_model_count": len(available),
                                 "requested_model_available": matched})
        if not matched:
            result.update(status="model_unavailable", elapsed_ms=round((time.monotonic()-started)*1000, 1))
            return result
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, TypeError, AttributeError) as exc:
        classification = "request_timed_out" if isinstance(exc, TimeoutError) else "provider_unavailable"
        result["stages"].append({"name": "model_listing", "ok": False,
                                 "classification": classification,
                                 "error_type": type(exc).__name__,
                                 "http_status": getattr(exc, "code", None)})
        result.update(status=classification, elapsed_ms=round((time.monotonic()-started)*1000, 1))
        return result

    compatibility = _probe_tool_call(config, timeout, "auto", endpoint_factory)
    result["stages"].append({"name": "compatibility_probe", **compatibility})
    result["status"] = compatibility["classification"]
    if compatibility["ok"]:
        result["status"] = "verified_compatible"
    elif (diagnose_required and compatibility["classification"] == "invalid_tool_call_response"
          and compatibility.get("finish_reason") != "length"):
        diagnostic = _probe_tool_call(config, timeout, "required", endpoint_factory)
        if diagnostic["classification"] == "invalid_tool_call_response":
            # HTTP 400/422 on only the optional diagnostic is a provider rejection
            # of that option, not a failure of the working auto-tool protocol.
            if diagnostic.get("http_status") in (400, 422):
                diagnostic["classification"] = "optional_tool_choice_required_unsupported"
        result["stages"].append({"name": "required_option_diagnostic", **diagnostic})
    result["elapsed_ms"] = round((time.monotonic()-started)*1000, 1)
    return result


def make_chat_endpoint(config: dict[str, Any]):
    # Local import avoids coupling configuration parsing to the agent runner.
    from experiment.llm_runner import ChatEndpoint
    return ChatEndpoint(config["endpoint_url"], config["model"], config.get("api_key"),
                        config["temperature"], config["max_output_tokens"],
                        config["request_timeout_seconds"], config.get("seed"),
                        config.get("think"), config["top_p"])
