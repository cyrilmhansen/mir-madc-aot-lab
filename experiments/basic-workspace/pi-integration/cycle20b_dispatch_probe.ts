// Deterministic harness around the real extension's registered TypeScript
// tool handlers. It does not call a model; each handler still uses the actual
// GatewayBridge and Python JSONL server.
import { Value } from "typebox/value";

type Tool = { name: string; parameters: any; execute: (...args: any[]) => Promise<any> };
const tools = new Map<string, Tool>();
const listeners = new Map<string, Array<(...args: any[]) => any>>();
let active: string[] = [];
const pi: any = {
  registerTool(tool: Tool) { tools.set(tool.name, tool); },
  on(name: string, callback: (...args: any[]) => any) {
    listeners.set(name, [...(listeners.get(name) || []), callback]);
  },
  setActiveTools(names: string[]) { active = [...names]; },
  getActiveTools() { return [...active]; },
  getAllTools() { return [...tools.values()].map(({ name, parameters }) => ({ name, parameters })); },
};

async function emit(name: string, ...args: any[]) {
  for (const listener of listeners.get(name) || []) await listener(...args);
}

async function run() {
  const inPath = process.env.BASIC_WS_DISPATCH_PROBE_INPUT;
  const outPath = process.env.BASIC_WS_DISPATCH_PROBE_OUTPUT;
  if (!inPath || !outPath) throw new Error("probe input/output paths are required");
  const request = JSON.parse(await Bun.file(inPath).text());
  const authoringMode = request.authoring_mode || "semantic_edit";
  if (!["semantic_edit", "atomic_create", "structural_edit"].includes(authoringMode)) throw new Error("unsupported authoring_mode");
  process.env.BASIC_WS_AUTHORING_MODE = authoringMode;
  const { default: workspaceExtension } = await import("./extension.ts");
  workspaceExtension(pi);
  const ctx = { hasUI: false };
  await emit("session_start", {}, ctx);
  const schemas = [...tools.values()].filter(tool => active.includes(tool.name))
    .map(tool => ({ name: tool.name, parameters: tool.parameters }));
  const previewToolName = authoringMode === "atomic_create" ? "workspace_preview_function" :
    authoringMode === "structural_edit" ? "workspace_preview_structural_edit" : "workspace_preview_semantic_edit";
  const previewTool = tools.get(previewToolName);
  if (!previewTool) throw new Error("semantic edit tool was not registered");
  const schemaOk = Value.Check(previewTool.parameters, request.preview_args);
  if (!schemaOk) {
    const errors = [...Value.Errors(previewTool.parameters, request.preview_args)].map(error => ({
      path: error.path, message: error.message,
    }));
    await Bun.write(outPath, JSON.stringify({ ok: false, stage: "pi_typescript_schema",
      active_tools: active, schemas, schema_ok: false, schema_errors: errors }, null, 2) + "\n");
    await emit("session_shutdown", {});
    return;
  }
  const ctxForTool = {};
  const call = async (toolName: string, toolCallId: string, args: any) => {
    const tool = tools.get(toolName);
    if (!tool) throw new Error(`missing registered tool ${toolName}`);
    await emit("tool_execution_start", { toolCallId, toolName, args });
    const started = performance.now();
    const result = await tool.execute(toolCallId, args, undefined, undefined, ctxForTool);
    await emit("tool_execution_end", { toolCallId, toolName, isError: false,
      durationMs: performance.now() - started, result });
    return result.details;
  };
  const discovery = await call("workspace_discover_functions", `${request.correlation_id}-discover`, {});
  const inspection = await call("workspace_inspect_program", `${request.correlation_id}-inspect`, {});
  const controls: any[] = [];
  for (const [index, args] of (request.controls || []).entries()) {
    if (!Value.Check(previewTool.parameters, args)) throw new Error(`control ${index} fails the advertised schema`);
    controls.push(await call(previewToolName, `${request.correlation_id}-control-${index}`, args));
  }
  const preview = await call(previewToolName, request.correlation_id, request.preview_args);
  let committed: any = null;
  let validation: any = null;
  let duplicateCommit: any = null;
  if (request.commit) {
    committed = await call("workspace_commit_preview", `${request.correlation_id}-commit`, {
      transaction_id: preview.transaction_id,
    });
    validation = await call("workspace_validate_mission", `${request.correlation_id}-validate`, {
      expected_revision: committed.revision,
    });
    if (request.duplicate_commit) duplicateCommit = await call("workspace_commit_preview",
      `${request.correlation_id}-duplicate-commit`, { transaction_id: preview.transaction_id });
  }
  await Bun.write(outPath, JSON.stringify({ ok: true, stage: "extension_to_gateway",
    active_tools: active, schemas, schema_ok: true, discovery, inspection, controls, preview,
    committed, duplicate_commit: duplicateCommit, validation }, null, 2) + "\n");
  await emit("session_shutdown", {});
}

run().catch(async error => {
  const outPath = process.env.BASIC_WS_DISPATCH_PROBE_OUTPUT;
  if (outPath) await Bun.write(outPath, JSON.stringify({ ok: false, error: String(error) }, null, 2) + "\n");
  console.error(error);
  process.exitCode = 1;
});
