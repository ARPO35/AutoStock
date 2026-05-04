import type { SessionStatus, TimelineKind, TimelineItem, ToolResultPayload } from "@/types";
import type { SessionTimelineItem, DataConflict } from "@/api";

export const moneyFormatter = new Intl.NumberFormat("zh-CN", {
  style: "currency",
  currency: "CNY",
  maximumFractionDigits: 2
});

export function formatMoney(value: number | null | undefined): string {
  return value == null ? "--" : moneyFormatter.format(value);
}

export function normalizeStatus(status: string | null | undefined): SessionStatus {
  const value = (status ?? "idle").toLowerCase();
  if (value.includes("run")) return "running";
  if (value.includes("queue")) return "queued";
  if (value.includes("error") || value.includes("fail")) return "error";
  if (value.includes("archive")) return "archived";
  return "idle";
}

export function statusLabel(status: SessionStatus): string {
  return {
    idle: "空闲",
    running: "运行中",
    queued: "排队",
    error: "报错",
    archived: "归档"
  }[status];
}

export function humanTime(value: string | null | undefined): string {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", {
    hour12: false,
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  });
}

export function parseJsonObject(value: string | null | undefined): Record<string, unknown> {
  if (!value) return {};
  try {
    const parsed = JSON.parse(value) as unknown;
    return parsed && typeof parsed === "object" && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : { value: parsed };
  } catch {
    return { content: value };
  }
}

export function parseInputObject(value: string): Record<string, unknown> | null {
  try {
    const parsed = JSON.parse(value || "{}") as unknown;
    return parsed && typeof parsed === "object" && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : null;
  } catch {
    return null;
  }
}

export function formatValue(value: unknown): string {
  if (value == null || value === "") return "--";
  if (typeof value === "number") return Number.isFinite(value) ? String(value) : "--";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export function summarizeArgs(value: string | null | undefined): string {
  const parsed = parseJsonObject(value);
  const entries = Object.entries(parsed).slice(0, 3);
  if (entries.length === 0) return "无参数";
  return entries.map(([key, item]) => `${key}: ${formatValue(item)}`).join(" / ");
}

const TOOL_DISPLAY_NAMES: Record<string, string> = {
  "system.echo": "系统回显",
  "market.quote": "行情报价",
  "market.history": "历史行情",
  "data.fetch_history": "数据拉取",
  "order.buy": "模拟买入",
  "order.sell": "模拟卖出",
  "order.cancel": "撤单",
  "portfolio.get_state": "账户概览",
  "portfolio.get_positions": "持仓查询",
  "portfolio.get_orders": "订单查询",
  "portfolio.get_trades": "成交查询",
};

export function toolDisplayName(name: string | null | undefined): string {
  if (!name) return "未知工具";
  return TOOL_DISPLAY_NAMES[name] ?? name;
}

const ARG_NAME_CN: Record<string, string> = {
  symbol: "代码",
  location: "地点",
  date: "日期",
  start: "起始",
  end: "截止",
  interval: "周期",
  adjust: "复权",
  query: "查询",
  message: "消息",
};

function argNameCN(key: string): string {
  return ARG_NAME_CN[key] ?? key;
}

export function summarizeArgsChinese(value: string | null | undefined): string {
  const parsed = parseJsonObject(value);
  const entries = Object.entries(parsed).slice(0, 4);
  if (entries.length === 0) return "无参数";
  return entries.map(([k, v]) => `${argNameCN(k)}=${formatValue(v)}`).join(", ");
}

export function objectEntries(data: Record<string, unknown>): Array<[string, string]> {
  return Object.entries(data).map(([key, value]) => [key, formatValue(value)]);
}

export function providerTypeLabel(type: string | null | undefined): "OpenAI-Compatible" | "DeepSeek" {
  return type === "deepseek" ? "DeepSeek" : "OpenAI-Compatible";
}

export function barClose(bar: Record<string, unknown>): number | null {
  const value = Number(bar.close ?? bar.Close ?? bar.price ?? bar["收盘"]);
  return Number.isFinite(value) ? value : null;
}

export function barTime(bar: Record<string, unknown>): string {
  return formatValue(bar.datetime ?? bar.date ?? bar.time ?? bar["日期"]);
}

export function conflictSummary(conflict: DataConflict): string {
  return `${Object.keys(parseJsonObject(conflict.existing_value_json)).length} old / ${Object.keys(parseJsonObject(conflict.new_value_json)).length} new`;
}

export function maskApiKey(value: string | null | undefined): string {
  if (!value || value.length <= 12) return value ? "*".repeat(value.length) : "未配置";
  return `${value.slice(0, 6)}${"*".repeat(Math.max(4, value.length - 12))}${value.slice(-6)}`;
}

export function extractDomain(url: string): string {
  try {
    const host = new URL(url).hostname;
    const parts = host.split(".");
    if (parts.length <= 2) return host;
    return parts.slice(-3).join(".");
  } catch {
    return url;
  }
}

export function buildTimeline(source: SessionTimelineItem[], model?: string | null): TimelineItem[] {
  const callsById = new Map(
    source.filter((item) => item.type === "tool_call").map((item) => [item.id, item])
  );

  const flatItems = source.map((item): TimelineItem => {
    if (item.type === "message") return messageTimelineItem(item, model);

    if (item.type === "tool_call") {
      return {
        id: item.id,
        kind: "tool-call",
        role: "tool-call",
        time: humanTime(item.started_at),
        title: "Tool Call",
        runId: item.run_id,
        toolCallId: item.tool_call_id ?? item.id,
        toolName: item.tool_name,
        status: item.status,
        argsSummary: summarizeArgs(item.arguments_json),
        raw: { ...item, arguments: parseJsonObject(item.arguments_json), arguments_json: item.arguments_json },
        model: model ?? null
      };
    }

    const call = item.tool_call_id ? callsById.get(item.tool_call_id) : undefined;
    const parsed = parseJsonObject(item.result_json);

    return {
      id: item.id,
      kind: parsed.error ? "error" : "tool-result",
      role: parsed.error ? "error" : "tool-result",
      time: humanTime(item.created_at),
      title: parsed.error ? "工具错误" : "工具结果",
      runId: item.run_id,
      toolCallId: item.tool_call_id,
      toolName: call?.tool_name ?? null,
      body: typeof parsed.error === "string" ? parsed.error : undefined,
      result: classifyToolResult(call?.tool_name, parsed),
      raw: parsed,
      model: model ?? null
    };
  });

  const resultByCallId = new Map<string, TimelineItem>();
  for (const item of flatItems) {
    if (item.role === "tool-result" && item.toolCallId) {
      resultByCallId.set(item.toolCallId, item);
    }
  }

  return flatItems
    .filter((item) => item.role !== "tool-result")
    .map((item) => {
      if (item.role === "tool-call" && item.toolCallId) {
        const result = resultByCallId.get(item.toolCallId);
        if (result) {
          return { ...item, result: result.result, status: item.status };
        }
      }
      return item;
    });
}

function messageTimelineItem(item: SessionTimelineItem, model?: string | null): TimelineItem {
  const role = item.role ?? "user";
  const kind: TimelineKind =
    role === "assistant"
      ? "assistant"
      : item.message_type === "event"
        ? "event"
        : role === "user"
          ? "user"
          : "tool-result";

  return {
    id: item.id,
    kind,
    role: kind,
    time: humanTime(item.created_at),
    title:
      role === "assistant"
        ? "助手"
        : item.message_type === "event"
          ? "事件"
          : "用户",
    body: item.content || "",
    raw: { role: item.role, message_type: item.message_type },
    model: model ?? null,
    reasoning: item.reasoning_content ?? null
  };
}

function classifyToolResult(
  toolName: string | null | undefined,
  envelope: Record<string, unknown>
): ToolResultPayload {
  const result =
    envelope.result && typeof envelope.result === "object" && !Array.isArray(envelope.result)
      ? (envelope.result as Record<string, unknown>)
      : envelope;
  const name = toolName ?? "";
  const kind = typeof result.kind === "string" ? result.kind : "";

  if (toolName === "market_quote") return { kind: "quote", quote: result };
  if (toolName === "market_history")
    return {
      kind: "history",
      history: result,
      bars: Array.isArray(result.bars) ? (result.bars as Record<string, unknown>[]) : []
    };
  if (toolName === "data_fetch_history") return { kind: "fetch-history", stats: result };
  if (name.startsWith("order_") || kind === "order_result") {
    return { kind: "order-result", data: result };
  }
  if (name === "portfolio_get_state" || kind === "portfolio_state") {
    return { kind: "portfolio-state", data: result };
  }
  if (name === "portfolio_get_positions" || kind === "portfolio_positions") {
    return { kind: "portfolio-positions", data: result };
  }
  if (name === "portfolio_get_orders" || kind === "portfolio_orders") {
    return { kind: "portfolio-orders", data: result };
  }
  if (name === "portfolio_get_trades" || kind === "portfolio_trades") {
    return { kind: "portfolio-trades", data: result };
  }
  return { kind: "json", title: toolName ? `${toolName} 结果` : "工具结果", data: envelope };
}

export function linePoints(
  values: number[],
  width: number,
  height: number,
  offsetX = 0,
  offsetY = 0
): string {
  if (values.length === 0) return "";
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  return values
    .map((value, index) => {
      const x = offsetX + (index / Math.max(values.length - 1, 1)) * width;
      const y = offsetY + height - ((value - min) / span) * height;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
}

export interface StreamingToolCallLike {
  toolCallId: string;
  toolName: string;
  arguments_json: string;
  status: string;
  error?: string | null;
  rawResult: Record<string, unknown> | null;
}

export function syntheticToolCallItem(tc: StreamingToolCallLike): TimelineItem {
  let result: ToolResultPayload | undefined;
  if (tc.rawResult) {
    const envelope: Record<string, unknown> = tc.status === "error"
      ? { ok: false, error: tc.error ?? null, result: tc.rawResult }
      : { ok: true, result: tc.rawResult };
    result = classifyToolResult(tc.toolName, envelope);
  }

  return {
    id: `ws-tc-${tc.toolCallId}`,
    kind: "tool-call",
    role: "tool-call",
    time: "",
    title: "Tool Call",
    toolCallId: tc.toolCallId,
    toolName: tc.toolName,
    status: tc.status,
    argsSummary: summarizeArgsChinese(tc.arguments_json),
    raw: { arguments_json: tc.arguments_json },
    result,
    body: tc.status === "error" ? (tc.error || "工具执行失败") : undefined,
  };
}
