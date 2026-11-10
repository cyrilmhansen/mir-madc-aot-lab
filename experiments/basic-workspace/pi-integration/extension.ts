import net from "node:net";
import { Type } from "typebox";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const COMMON_TOOLS = ["workspace_discover_functions", "workspace_inspect_program",
  "workspace_commit_preview", "workspace_validate_mission"];
const ATOMIC_TOOLS = [...COMMON_TOOLS, "workspace_preview_function"];
const SEMANTIC_EDIT_TOOLS = [...COMMON_TOOLS, "workspace_preview_semantic_edit"];
const STRUCTURAL_EDIT_TOOLS = [...COMMON_TOOLS, "workspace_preview_structural_edit"];
const RENAME_TOOLS = [...COMMON_TOOLS, "workspace_preview_rename"];
const CONDITIONAL_EDIT_TOOLS = [...COMMON_TOOLS, "workspace_preview_conditional_edit"];
const BLOCK_REPLACE_TOOLS = [...COMMON_TOOLS, "workspace_preview_block_replacement"];
const DRAFT_TOOLS = [...COMMON_TOOLS, "workspace_begin_function_draft", "workspace_apply_draft_operations",
  "workspace_inspect_function_draft", "workspace_preview_function_draft"];
const TOOL_NAMES = process.env.BASIC_WS_AUTHORING_MODE === "incremental" ? DRAFT_TOOLS :
  process.env.BASIC_WS_AUTHORING_MODE === "semantic_edit" ? SEMANTIC_EDIT_TOOLS :
  process.env.BASIC_WS_AUTHORING_MODE === "semantic_edit_multi" ? SEMANTIC_EDIT_TOOLS :
  process.env.BASIC_WS_AUTHORING_MODE === "structural_edit" ? STRUCTURAL_EDIT_TOOLS :
  process.env.BASIC_WS_AUTHORING_MODE === "rename" ? RENAME_TOOLS :
  process.env.BASIC_WS_AUTHORING_MODE === "conditional_edit" ? CONDITIONAL_EDIT_TOOLS :
  process.env.BASIC_WS_AUTHORING_MODE === "block_replace" ? BLOCK_REPLACE_TOOLS : ATOMIC_TOOLS;
const MULTI_EDIT_MODE = process.env.BASIC_WS_AUTHORING_MODE === "semantic_edit_multi";
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
const BLOCK_RESULT_ASSIGN = Type.Object({ kind: Type.Literal("assign"), target: RESULT_TARGET,
  expression: CALL_OR_ATOM_EXPR }, { additionalProperties: false });
const IF_CONDITION = Type.Object({ kind: Type.Literal("binary"), operator: OPERATOR_SCHEMA,
  left: CALL_OR_ATOM_EXPR, right: CALL_OR_ATOM_EXPR }, { additionalProperties: false });
const IF_STATEMENT = Type.Object({ kind: Type.Literal("if"), condition: IF_CONDITION,
  then: Type.Array(RESULT_ASSIGN, { maxItems: 64 }), else: Type.Optional(Type.Array(RESULT_ASSIGN, { maxItems: 64 })) },
  { additionalProperties: false });
const FUNCTION_STATEMENT = Type.Union([RESULT_ASSIGN, IF_STATEMENT]);
const CONTROL_STEP = Type.Object({ block: Type.Union([Type.Literal("body"), Type.Literal("then"), Type.Literal("else")]),
  index: Type.Integer() }, { additionalProperties: false });
const CONTROL_PATH = Type.Array(CONTROL_STEP, { minItems: 1, maxItems: 8 });
const IF_CONDITION_TARGET = Type.Object({ function_handle: Type.String(),
  control_path: Type.Array(CONTROL_STEP, { minItems: 1, maxItems: 8 }),
  expression_path: Type.Array(Type.Integer(), { minItems: 1, maxItems: 1 }) }, { additionalProperties: false });
const ASSIGNMENT_TARGET = Type.Object({ function_handle: Type.String(), statement_handle: Type.String(),
  expression_path: Type.Array(Type.Integer(), { maxItems: 0 }) }, { additionalProperties: false });
const SEMANTIC_EDIT = Type.Object({ target: Type.Union([IF_CONDITION_TARGET, ASSIGNMENT_TARGET]),
  expected_value: Type.Number(), replacement_value: Type.Number() }, { additionalProperties: false });

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

  async call(method: string, params: Record<string, unknown> = {}, timeoutMs = 30000,
    toolCallId?: string): Promise<any> {
    await this.connect(); const request_id = `pi-${Date.now()}-${++this.serial}`;
    const transport = toolCallId === undefined ? undefined : { tool_call_id: toolCallId };
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { this.pending.delete(request_id); reject(new Error("gateway request timed out")); }, timeoutMs);
      this.pending.set(request_id, { resolve, reject, timer });
      this.socket!.write(JSON.stringify({ request_id, method, params,
        ...(transport === undefined ? {} : { transport }) }) + "\n", error => {
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
      return toolResult(await gateway.call("discover_functions", {}, 30000, toolCallId));
    }});
  pi.registerTool({ name: "workspace_inspect_program", label: "Inspect BASIC structure",
    description: "Inspect the current revision's semantic functions, parameters, arrays and call dependencies.",
    parameters: Type.Object({}), async execute(toolCallId) {
      return toolResult(await gateway.call("inspect_program", {}, 30000, toolCallId));
    }});
  pi.registerTool({ name: "workspace_preview_function", label: "Preview semantic function",
    description: 'Preview one typed numeric function through the mission gateway; preview never commits. Discover functions first. Calls carry their discovered portable handle inside the call expression; the optional top-level callee_handle is retained for compatibility and normally omitted. A result assignment looks like {"kind":"assign","target":{"kind":"result"},"expression":{"kind":"number","value":0}}. A bound call expression looks like {"kind":"call","function_handle":"<discovered-handle>","arguments":[{"kind":"local_ref","name":"<parameter>"}]}. Expressions are numeric literals, local parameter references, or bound calls; IF conditions compare two such expressions. IF branches contain result assignments (no nested IF). Use sequential IF statements where needed. The gateway separately enforces mission-specific scope, signature, and dependency. No source text is accepted.',
    parameters: Type.Object({ expected_revision: Type.Integer(), callee_handle: Type.Optional(Type.String()), name: Type.String(),
      parameters: Type.Array(Type.String(), { minItems: 1, maxItems: 8 }),
      body: Type.Array(FUNCTION_STATEMENT, { minItems: 1, maxItems: 64 }) }, { additionalProperties: false }),
    async execute(toolCallId, params) {
      return toolResult(await gateway.call("preview_create_function", params, 30000, toolCallId));
    }});
  pi.registerTool({ name: "workspace_preview_semantic_edit", label: "Preview semantic literal edit",
    description: MULTI_EDIT_MODE
      ? "Preview one atomic numeric-literal edit batch across discovered functions. Each edit carries its own authorized function_handle and inspected typed target path. Use scope_mode per_target; there is deliberately no global function handle. Include exact expected_value preconditions. The host contract authorizes the complete target set and the transaction commits as one revision."
      : "Preview one bounded atomic group of authorized numeric literal edits. First discover functions and inspect the gateway-provided typed target paths. A target uses its discovered function_handle plus either a control_path and expression_path for an IF comparison operand, or a discovered statement_handle and explicit expression_path (use [] for the assignment RHS root). Include expected_value preconditions. Preview never changes committed BASIC; commit only an accepted transaction. The host-owned mission contract enforces edit count, scope, values and invariants.",
    parameters: MULTI_EDIT_MODE
      ? Type.Object({ expected_revision: Type.Integer(), scope_mode: Type.Literal("per_target"),
          edits: Type.Array(SEMANTIC_EDIT, { minItems: 1, maxItems: 8 }) }, { additionalProperties: false })
      : Type.Object({ expected_revision: Type.Integer(), function_handle: Type.String(),
          edits: Type.Array(SEMANTIC_EDIT, { minItems: 1, maxItems: 8 }) }, { additionalProperties: false }),
    async execute(toolCallId, params) {
      return toolResult(await gateway.call("preview_semantic_edit", params, 30000, toolCallId));
    }});
  pi.registerTool({ name: "workspace_preview_structural_edit", label: "Preview typed structural edit",
    description: 'Insert one typed IF block into the discovered function before its verified result epilogue. The insertion anchor is a discovered result-assignment statement handle at the function-body boundary. The condition is a typed numeric comparison; branches contain result assignments. A bound call uses {"kind":"call","function_handle":"<discovered-handle>","arguments":[{"kind":"local_ref","name":"X"}]}. For example, {"kind":"if","condition":{"kind":"binary","operator":"=","left":{"kind":"call","function_handle":"<discovered-handle>","arguments":[{"kind":"local_ref","name":"X"}]},"right":{"kind":"number","value":50}},"then":[{"kind":"assign","target":{"kind":"result"},"expression":{"kind":"number","value":3}}]}. Preview leaves committed BASIC unchanged; the gateway checks the complete candidate and authorization before commit.',
    parameters: Type.Object({ expected_revision: Type.Integer(), function_handle: Type.String(),
      before_statement_handle: Type.String(), statement: IF_STATEMENT }, { additionalProperties: false }),
    async execute(toolCallId, params) {
      return toolResult(await gateway.call("preview_structural_edit", params, 30000, toolCallId));
    }});
  pi.registerTool({ name: "workspace_preview_conditional_edit", label: "Preview typed IF condition edit",
    description: 'Replace only one existing IF condition in a discovered numeric function. Select it with the inspected control_path and a discovered result-assignment anchor_statement_handle directly inside that IF. Include the exact inspected expected_condition and one typed numeric comparison as condition. A bound call has shape {"kind":"call","function_handle":"<discovered-handle>","arguments":[{"kind":"local_ref","name":"<parameter>"}]}; comparisons use {"kind":"binary","operator":"=","left":<typed expression>,"right":<typed expression>}. The preview preserves branches and committed BASIC; the host contract authorizes the target and dependency.',
    parameters: Type.Object({ expected_revision: Type.Integer(), function_handle: Type.String(),
      control_path: CONTROL_PATH, anchor_statement_handle: Type.String(),
      expected_condition: IF_CONDITION, condition: IF_CONDITION }, { additionalProperties: false }),
    async execute(toolCallId, params) {
      return toolResult(await gateway.call("preview_conditional_edit", params, 30000, toolCallId));
    }});
  pi.registerTool({ name: "workspace_preview_block_replacement", label: "Preview typed IF block replacement",
    description: 'Replace one discovered IF block with typed result assignment(s), without replacing its containing function. Select the IF with its inspected control_path, semantic fingerprint, and stable child assignment anchors. List every removed statement handle explicitly. A replacement assignment has shape {"kind":"assign","target":{"kind":"result"},"expression":<number, parameter reference, or bound function call>}; bound calls use {"kind":"call","function_handle":"<discovered-handle>","arguments":[{"kind":"local_ref","name":"<parameter>"}]}. Preview is temporary; commit only if the host accepts it. Removed statement identities are retired and replacement statements get fresh identities.',
    parameters: Type.Object({ expected_revision: Type.Integer(), function_handle: Type.String(),
      control_path: CONTROL_PATH, anchor_statement_handle: Type.String(),
      expected_block_fingerprint: Type.String(), expected_removed_statement_handles: Type.Array(Type.String(), { minItems: 1, maxItems: 64 }),
      replacement_statements: Type.Array(BLOCK_RESULT_ASSIGN, { minItems: 1, maxItems: 16 }) }, { additionalProperties: false }),
    async execute(toolCallId, params) {
      return toolResult(await gateway.call("preview_block_replacement", params, 30000, toolCallId));
    }});
  pi.registerTool({ name: "workspace_preview_rename", label: "Preview semantic rename",
    description: "Preview a revision-checked rename of a discovered function identity. Supply its stable function_handle, expected current source name, and proposed new source name. The gateway resolves all declaration and bound-reference tokens by identity, authorizes the mission, and previews atomically; source text is never searched or replaced. Commit only an accepted preview.",
    parameters: Type.Object({ expected_revision: Type.Integer(), function_handle: Type.String(),
      expected_name: Type.String(), new_name: Type.String() }, { additionalProperties: false }),
    async execute(toolCallId, params) {
      return toolResult(await gateway.call("preview_rename", params, 30000, toolCallId));
    }});
  pi.registerTool({ name: "workspace_commit_preview", label: "Commit semantic preview",
    description: "Commit an accepted gateway preview by its transaction ID. Commit rechecks the mission and revision atomically.",
    parameters: Type.Object({ transaction_id: Type.String() }, { additionalProperties: false }),
    async execute(toolCallId, params) {
      return toolResult(await gateway.call("commit_preview", params, 30000, toolCallId));
    }});
  pi.registerTool({ name: "workspace_validate_mission", label: "Validate BASIC mission",
    description: "Run the independent MIR interpreter/JIT oracle and fresh-workspace replay checks at an explicit revision.",
    parameters: Type.Object({ expected_revision: Type.Integer() }, { additionalProperties: false }),
    async execute(toolCallId, params) {
      return toolResult(await gateway.call("validate_mission", params, 120000, toolCallId));
    }});
  pi.registerTool({ name: "workspace_begin_function_draft", label: "Begin typed function draft",
    description: "Open a temporary revision-bound numeric function draft. This does not change committed BASIC. Discover the permitted call target first.",
    parameters: Type.Object({ expected_revision: Type.Integer(), name: Type.String(),
      parameters: Type.Array(Type.String(), { minItems: 1, maxItems: 8 }),
      callee_handle: Type.String() }, { additionalProperties: false }),
    async execute(toolCallId, params) { return toolResult(await gateway.call("begin_function_draft", params, 30000, toolCallId)); }});
  pi.registerTool({ name: "workspace_apply_draft_operations", label: "Apply typed draft operations",
    description: "Apply an ordered atomic batch of flat typed draft operations. Earlier draft-local handles may be referenced by later operations. A failed batch changes neither draft nor Workspace.",
    parameters: Type.Object({ draft_id: Type.String(), expected_draft_revision: Type.Integer(),
      operations: Type.Array(DRAFT_OPERATION, { minItems: 1, maxItems: 32 }) }, { additionalProperties: false }),
    async execute(toolCallId, params) { return toolResult(await gateway.call("apply_draft_operations", params, 30000, toolCallId)); }});
  pi.registerTool({ name: "workspace_inspect_function_draft", label: "Inspect function draft",
    description: "Inspect the typed draft's revision, handles, ordered statements and pending preview without changing committed BASIC.",
    parameters: Type.Object({ draft_id: Type.String() }, { additionalProperties: false }),
    async execute(toolCallId, params) { return toolResult(await gateway.call("inspect_function_draft", params, 30000, toolCallId)); }});
  pi.registerTool({ name: "workspace_preview_function_draft", label: "Preview complete function draft",
    description: "Resolve the complete draft and ask the existing MissionGateway to validate the whole candidate at the current Workspace and draft revisions. Preview never commits.",
    parameters: Type.Object({ draft_id: Type.String(), expected_revision: Type.Integer(), expected_draft_revision: Type.Integer() }, { additionalProperties: false }),
    async execute(toolCallId, params) { return toolResult(await gateway.call("preview_function_draft", params, 30000, toolCallId)); }});
}
