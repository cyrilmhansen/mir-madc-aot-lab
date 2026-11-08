import net from "node:net";
import { Type } from "typebox";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const COMMON_TOOLS = ["workspace_discover_functions", "workspace_inspect_program",
  "workspace_commit_preview", "workspace_validate_mission"];
const ATOMIC_TOOLS = [...COMMON_TOOLS, "workspace_preview_function"];
const DRAFT_TOOLS = [...COMMON_TOOLS, "workspace_begin_function_draft", "workspace_apply_draft_operations",
  "workspace_inspect_function_draft", "workspace_preview_function_draft"];
const TOOL_NAMES = process.env.BASIC_WS_AUTHORING_MODE === "incremental" ? DRAFT_TOOLS : ATOMIC_TOOLS;
const MAX_RESPONSE = 1024 * 1024;

const OPERATORS = ["+", "-", "*", "/", "=", "<>", "<", "<=", ">", ">="] as const;
const OPERATOR_SCHEMA = Type.Unsafe({ type: "string", enum: [...OPERATORS] });
const NUMBER_EXPR = Type.Object({ kind: Type.Literal("number"), value: Type.Number() }, { additionalProperties: false });
const ID_EXPR = Type.Object({ kind: Type.Literal("local_ref"), name: Type.String() }, { additionalProperties: false });
const ATOM_EXPR = Type.Union([NUMBER_EXPR, ID_EXPR]);
const CALL_EXPR = Type.Object({ kind: Type.Literal("call"), function_handle: Type.String(),
  arguments: Type.Array(ATOM_EXPR, { minItems: 1, maxItems: 8 }) }, { additionalProperties: false });
const CALL_OR_ATOM_EXPR = Type.Union([ATOM_EXPR, CALL_EXPR]);
// Mission-bounded expression grammar: atoms and bound calls, optionally
// combined by one binary layer. This admits AGE_BY_ID(ID) >= 18 without an
// exponential recursive schema or provider-facing $ref/$defs.
const RESULT_TARGET = Type.Object({ kind: Type.Literal("result") }, { additionalProperties: false });
const RESULT_ASSIGN = Type.Object({ kind: Type.Literal("assign"), target: RESULT_TARGET,
  expression: ATOM_EXPR }, { additionalProperties: false });
const IF_CONDITION = Type.Object({ kind: Type.Literal("binary"), operator: OPERATOR_SCHEMA,
  left: CALL_OR_ATOM_EXPR, right: CALL_OR_ATOM_EXPR }, { additionalProperties: false });
const IF_STATEMENT = Type.Object({ kind: Type.Literal("if"), condition: IF_CONDITION,
  then: Type.Array(RESULT_ASSIGN, { maxItems: 64 }), else: Type.Optional(Type.Array(RESULT_ASSIGN, { maxItems: 64 })) },
  { additionalProperties: false });
const FUNCTION_STATEMENT = Type.Union([RESULT_ASSIGN, IF_STATEMENT]);

// Flat discriminated operations reference draft-local handles. Expression trees
// are assembled from nodes rather than recursively repeated in every request.
const DRAFT_OPERATION = Type.Union([
  Type.Object({ op_id: Type.String(), kind: Type.Literal("define_number"), handle: Type.String(), value: Type.Number() }, { additionalProperties: false }),
  Type.Object({ op_id: Type.String(), kind: Type.Literal("define_parameter_ref"), handle: Type.String(), name: Type.String() }, { additionalProperties: false }),
  Type.Object({ op_id: Type.String(), kind: Type.Literal("define_function_call"), handle: Type.String(),
    function_handle: Type.String(), arguments: Type.Array(Type.String(), { minItems: 1, maxItems: 8 }) }, { additionalProperties: false }),
  Type.Object({ op_id: Type.String(), kind: Type.Literal("define_unary_expression"), handle: Type.String(),
    operator: Type.Unsafe({ type: "string", enum: ["+", "-"] }), operand: Type.String() }, { additionalProperties: false }),
  Type.Object({ op_id: Type.String(), kind: Type.Literal("define_binary_expression"), handle: Type.String(),
    operator: OPERATOR_SCHEMA, left: Type.String(), right: Type.String() }, { additionalProperties: false }),
  Type.Object({ op_id: Type.String(), kind: Type.Literal("append_result_assignment"), handle: Type.String(),
    block: Type.String(), expression: Type.String() }, { additionalProperties: false }),
  Type.Object({ op_id: Type.String(), kind: Type.Literal("append_if_block"), handle: Type.String(),
    block: Type.String(), condition: Type.String(), then_block: Type.String(), else_block: Type.String() }, { additionalProperties: false }),
]);

class GatewayBridge {
  private socket?: net.Socket;
  private buffer = "";
  private pending = new Map<string, { resolve: (v: any) => void; reject: (e: Error) => void; timer: NodeJS.Timeout }>();
  private serial = 0;

  async connect(): Promise<void> {
    if (this.socket && !this.socket.destroyed) return;
    const address = process.env.BASIC_WS_PI_GATEWAY;
    if (!address) throw new Error("BASIC_WS_PI_GATEWAY is missing");
    const [host, portText] = address.split(":");
    if (host !== "127.0.0.1" || !/^\d+$/.test(portText || "")) throw new Error("gateway must be on loopback");
    const sock = net.createConnection({ host, port: Number(portText) });
    this.socket = sock; sock.setEncoding("utf8");
    sock.on("data", chunk => {
      this.buffer += chunk;
      if (Buffer.byteLength(this.buffer, "utf8") > MAX_RESPONSE) { sock.destroy(new Error("gateway response too large")); return; }
      for (;;) {
        const at = this.buffer.indexOf("\n"); if (at < 0) break;
        const line = this.buffer.slice(0, at); this.buffer = this.buffer.slice(at + 1);
        try {
          const row = JSON.parse(line); const waiter = this.pending.get(row.request_id);
          if (!waiter) continue;
          clearTimeout(waiter.timer); this.pending.delete(row.request_id);
          row.ok ? waiter.resolve(row.result) : waiter.reject(new Error(`${row.error?.code || "GATEWAY_ERROR"}: ${row.error?.message || "gateway rejected request"}`));
        } catch (error) { sock.destroy(error as Error); }
      }
    });
    sock.on("error", error => { for (const waiter of this.pending.values()) { clearTimeout(waiter.timer); waiter.reject(error); } this.pending.clear(); });
    await new Promise<void>((resolve, reject) => { sock.once("connect", resolve); sock.once("error", reject); });
  }

  async call(method: string, params: Record<string, unknown> = {}, timeoutMs = 30000): Promise<any> {
    await this.connect(); const request_id = `pi-${Date.now()}-${++this.serial}`;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { this.pending.delete(request_id); reject(new Error("gateway request timed out")); }, timeoutMs);
      this.pending.set(request_id, { resolve, reject, timer });
      this.socket!.write(JSON.stringify({ request_id, method, params }) + "\n", error => {
        if (error) { clearTimeout(timer); this.pending.delete(request_id); reject(error); }
      });
    });
  }

  close(): void { this.socket?.end(); this.socket?.destroy(); this.socket = undefined; }
}

function toolResult(value: unknown) {
  const text = JSON.stringify(value, null, 2);
  return { content: [{ type: "text" as const, text }], details: value };
}

export default function (pi: ExtensionAPI) {
  const gateway = new GatewayBridge();
  pi.on("session_start", async (_event, ctx) => {
    pi.setActiveTools(TOOL_NAMES);
    const inventory = pi.getActiveTools();
    const schemas = pi.getAllTools().filter(tool => TOOL_NAMES.includes(tool.name)).map(tool => ({ name: tool.name, parameters: tool.parameters }));
    await gateway.call("record_pi_event", { type: "tool_inventory", tools: inventory, schemas, source: "Pi ExtensionAPI.getActiveTools/getAllTools" });
    if (ctx.hasUI) ctx.ui.setStatus("basic-workspace", "Semantic tools only · Python gateway");
  });
  pi.on("tool_execution_start", async event => {
    await gateway.call("record_pi_event", { type: "tool_execution_start", toolCallId: event.toolCallId,
      toolName: event.toolName, args: event.args, source: "Pi event stream" });
  });
  pi.on("tool_execution_end", async event => {
    await gateway.call("record_pi_event", { type: "tool_execution_end", toolCallId: event.toolCallId,
      toolName: event.toolName, isError: event.isError, durationMs: event.durationMs,
      result: event.result, source: "Pi event stream" });
  });
  pi.on("session_shutdown", async () => { gateway.close(); });

  pi.registerTool({ name: "workspace_discover_functions", label: "Discover BASIC functions",
    description: "Discover callable functions and signatures in the current revision. Use this before constructing a call.",
    parameters: Type.Object({}), async execute(toolCallId) {
      return toolResult(await gateway.call("discover_functions", { toolCallId }));
    }});
  pi.registerTool({ name: "workspace_inspect_program", label: "Inspect BASIC structure",
    description: "Inspect the current revision's semantic functions, parameters, arrays and call dependencies.",
    parameters: Type.Object({}), async execute(toolCallId) {
      return toolResult(await gateway.call("inspect_program", { toolCallId }));
    }});
  pi.registerTool({ name: "workspace_preview_function", label: "Preview semantic function",
    description: 'Preview one typed numeric function through the mission gateway; preview never commits. Discover the permitted function and use its returned portable handle. A result assignment looks like {"kind":"assign","target":{"kind":"result"},"expression":{"kind":"number","value":0}}. A bound call expression looks like {"kind":"call","function_handle":"<discovered-handle>","arguments":[{"kind":"local_ref","name":"<parameter>"}]}. Compose comparisons and structured IF blocks yourself. This bounded typed grammar accepts numeric expressions and result-assignment THEN/ELSE blocks; the gateway separately enforces the mission-specific function and signature. No source text is accepted.',
    parameters: Type.Object({ expected_revision: Type.Integer(), callee_handle: Type.String(), name: Type.String(),
      parameters: Type.Array(Type.String(), { minItems: 1, maxItems: 8 }),
      body: Type.Array(FUNCTION_STATEMENT, { minItems: 1, maxItems: 64 }) }, { additionalProperties: false }),
    async execute(toolCallId, params) {
      return toolResult(await gateway.call("preview_create_function", { ...params, toolCallId }));
    }});
  pi.registerTool({ name: "workspace_commit_preview", label: "Commit semantic preview",
    description: "Commit an accepted gateway preview by its transaction ID. Commit rechecks the mission and revision atomically.",
    parameters: Type.Object({ transaction_id: Type.String() }, { additionalProperties: false }),
    async execute(toolCallId, params) {
      return toolResult(await gateway.call("commit_preview", { ...params, toolCallId }));
    }});
  pi.registerTool({ name: "workspace_validate_mission", label: "Validate BASIC mission",
    description: "Run the independent MIR interpreter/JIT oracle and fresh-workspace replay checks at an explicit revision.",
    parameters: Type.Object({ expected_revision: Type.Integer() }, { additionalProperties: false }),
    async execute(toolCallId, params) {
      return toolResult(await gateway.call("validate_mission", { ...params, toolCallId }, 120000));
    }});
  pi.registerTool({ name: "workspace_begin_function_draft", label: "Begin typed function draft",
    description: "Open a temporary revision-bound numeric function draft. This does not change committed BASIC. Discover the permitted call target first.",
    parameters: Type.Object({ expected_revision: Type.Integer(), name: Type.String(),
      parameters: Type.Array(Type.String(), { minItems: 1, maxItems: 8 }),
      callee_handle: Type.String() }, { additionalProperties: false }),
    async execute(toolCallId, params) { return toolResult(await gateway.call("begin_function_draft", { ...params, toolCallId })); }});
  pi.registerTool({ name: "workspace_apply_draft_operations", label: "Apply typed draft operations",
    description: "Apply an ordered atomic batch of flat typed draft operations. Earlier draft-local handles may be referenced by later operations. A failed batch changes neither draft nor Workspace.",
    parameters: Type.Object({ draft_id: Type.String(), expected_draft_revision: Type.Integer(),
      operations: Type.Array(DRAFT_OPERATION, { minItems: 1, maxItems: 32 }) }, { additionalProperties: false }),
    async execute(toolCallId, params) { return toolResult(await gateway.call("apply_draft_operations", { ...params, toolCallId })); }});
  pi.registerTool({ name: "workspace_inspect_function_draft", label: "Inspect function draft",
    description: "Inspect the typed draft's revision, handles, ordered statements and pending preview without changing committed BASIC.",
    parameters: Type.Object({ draft_id: Type.String() }, { additionalProperties: false }),
    async execute(toolCallId, params) { return toolResult(await gateway.call("inspect_function_draft", { ...params, toolCallId })); }});
  pi.registerTool({ name: "workspace_preview_function_draft", label: "Preview complete function draft",
    description: "Resolve the complete draft and ask the existing MissionGateway to validate the whole candidate at the current Workspace and draft revisions. Preview never commits.",
    parameters: Type.Object({ draft_id: Type.String(), expected_revision: Type.Integer(), expected_draft_revision: Type.Integer() }, { additionalProperties: false }),
    async execute(toolCallId, params) { return toolResult(await gateway.call("preview_function_draft", { ...params, toolCallId })); }});
}
