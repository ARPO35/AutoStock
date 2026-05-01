export type RouteKey = "trade" | "view" | "edit" | "manage";
export type SessionStatus = "idle" | "running" | "queued" | "error" | "archived";
export type TimelineKind = "user" | "event" | "assistant" | "tool-call" | "tool-result" | "error";

export interface AccountView {
  id: string;
  name: string;
  providerId: string;
  providerName: string | null;
  initialCash: number;
  createdAt: string;
  updatedAt: string;
  sessionCount: number;
  runningSessions: number;
}

export interface SessionView {
  id: string;
  name: string;
  accountId: string | null;
  accountName: string | null;
  providerId: string | null;
  providerName: string | null;
  providerType: "openai_compatible" | "deepseek" | null;
  model: string | null;
  skillId: string | null;
  status: SessionStatus;
  lastRunAt: string | null;
}

export interface TimelineItem {
  id: string;
  kind: TimelineKind;
  time: string;
  title: string;
  body?: string;
  runId?: string | null;
  toolCallId?: string | null;
  toolName?: string | null;
  status?: string | null;
  argsSummary?: string;
  result?: ToolResultPayload;
  raw?: Record<string, unknown>;
}

export type ToolResultPayload =
  | { kind: "quote"; quote: Record<string, unknown> }
  | { kind: "history"; history: Record<string, unknown>; bars: Record<string, unknown>[] }
  | { kind: "fetch-history"; stats: Record<string, unknown> }
  | { kind: "json"; title: string; data: Record<string, unknown> };

export interface ProviderCard {
  id: string;
  name: string;
  type: "OpenAI-Compatible" | "DeepSeek";
  endpoint: string;
  model: string;
  status: "已连接" | "未配置";
  updatedAt: string;
  supportsTools: boolean;
  supportsStrictSchema: boolean;
  supportsReasoning: boolean;
}
