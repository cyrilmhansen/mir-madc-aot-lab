import net from "node:net";
import { Type } from "typebox";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const TOOL_NAMES = ["workspace_discover_functions", "workspace_inspect_program",
  "workspace_preview_function", "workspace_commit_preview", "workspace_validate_mission"];
const MAX_RESPONSE = 1024 * 1024;

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
    description: "Preview one typed numeric function creation through the mission gateway. Calls must use a discovered function handle. This does not commit.",
    parameters: Type.Object({ expected_revision: Type.Integer(), callee_handle: Type.String(), name: Type.String(),
      parameters: Type.Array(Type.String()), body: Type.Array(Type.Any()) }, { additionalProperties: false }),
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
}
