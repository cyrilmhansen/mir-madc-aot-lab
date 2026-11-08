# Cycle 16 integration audit

## Repository and installed Pi

- Repository baseline at start: `480361ca88939789ad93a0891b7d2cab3be2c642`, branch `experiment/mir-aot-correctness-cycle3`.
- Installed Pi: `1.5.0` (`/usr/bin/pi`).
- The Python Workspace and its existing mission wrappers are the only owners of document state, identities, authorization, previews, commits, MIR execution, replay and normalized presentation events.
- The local `~/.sushi/pi/models.json` was read by the launcher and copied into an ignored, mode-0600 isolated Pi config containing only the requested Sushi model. Private values are not in the committed artifacts. No global Pi configuration was changed.

## Pi interface choice

Pi's extension API registers model-visible tools inside Pi, while RPC is a JSONL control interface for driving a Pi session. An extension is the smaller path for this experiment: the model sees Pi-native tools, and each extension handler forwards one bounded JSONL request to Python. Driving RPC from Python would still need a mechanism to register/inject the same custom tools and would add another agent-control loop.

Process boundary:

```text
Pi 1.5.0 + TypeScript extension
   └─ five typed tool names over loopback JSONL
       └─ Python Cycle16Gateway (one live Workspace + MissionGateway)
           ├─ candidate preview / revision-checked commit
           ├─ MIR interpreter and JIT validation
           └─ append-only semantic events → Cycle 15 live viewer
```

The gateway binds to `127.0.0.1`, bounds frames to 1 MiB, correlates request IDs, rejects unknown methods, and serializes requests against the shared Workspace. Preview state is held by the existing Python MissionGateway. The TypeScript extension makes no policy decisions. Pi tool allowlisting is an experiment-level control, not an OS sandbox: other local processes or a user with shell access are outside this boundary.

## Pi restrictions and configuration

The launcher used Pi's supported OpenAI-compatible Sushi provider config and one exact model. It disabled built-in tools, all tools by default, MCP, other extensions, skills, context files and templates, then enabled the five custom tools. The extension records Pi's actual active-tool inventory and JSON schemas before inference; that inventory contained exactly:

1. `workspace_discover_functions`
2. `workspace_inspect_program`
3. `workspace_preview_function`
4. `workspace_commit_preview`
5. `workspace_validate_mission`

Pi RPC preflight verified that the requested model appeared in Pi's configured model catalog and captured the active tools. It deliberately made no provider inference request. The bounded real mission request then verified that Sushi accepted Pi's request format and returned tool calls.

Pi's current [extension](https://pi.dev/docs/latest/extensions), [RPC](https://pi.dev/docs/latest/rpc), [JSON event stream](https://pi.dev/docs/latest/json), [model configuration](https://pi.dev/docs/latest/models), and [CLI](https://pi.dev/docs/latest/cli) documentation informed the implementation. The exact tested CLI and ExtensionAPI version was Pi 1.5.0.

## Existing components reused

Reused without replacing the semantic engine: Cycle 14B's revision-4 typed seed, `SeniorMissionGateway`, age-independent adult mission validator, Cycle 15's `basic-visual.py live/replay`, normalized presentation-event compiler, and existing construction/replay helpers. The new code is limited to a loopback adapter, Pi extension, campaign launcher and focused bridge tests.

## Cycle 16B follow-up

The mission-specific preview schema was changed from `array<{}>` to a bounded TypeBox union that Pi serializes to explicit `anyOf` branches. Preflight captured exactly five active tools; the full schema is 20,343 bytes and the constructor body schema is 7,932 bytes. The body grammar and exact captured schema are documented in [REPORT.md](REPORT.md). Deterministic tests run the known-good body and all eight original rejected bodies through the captured Pi schema and the existing Python gateway.

One corrected real Sushi/Qwen mission ran once in `results/real-pi-02/`: five turns, five calls, one accepted preview, one commit (revision 4→5), interpreter/JIT and age-boundary validation passed, and fresh-workspace replay passed with 24 remapped identities. The original failed evidence in `results/real-pi-01/` remains unchanged.

The missing Pi end-event observation was caused by the gateway idempotency key, not by Pi's extension API: both `tool_execution_start` and `tool_execution_end` used the same call ID and an empty phase. The gateway now uses the event type as its default phase. The historical extension journal remains unchanged; a separate sanitized adapter, explicitly sourced from the genuine Pi JSON session, includes the actual starts and ends. A regression test covers both distinct event types and repeated duplicates.
