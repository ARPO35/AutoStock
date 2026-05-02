export type ProviderType = "openai_compatible" | "deepseek";

export interface Provider {
  id: string;
  provider_type: ProviderType;
  name: string;
  base_url: string;
  api_key_masked: string | null;
  has_api_key: boolean;
  model: string;
  temperature: number;
  max_tokens: number | null;
  timeout_seconds: number;
  supports_tools: boolean;
  supports_parallel_tool_calls: boolean;
  supports_strict_schema: boolean;
  thinking_mode: string | null;
  strict_tool_schema: boolean;
  created_at: string;
  updated_at: string;
}

export interface Account {
  id: string;
  name: string;
  initial_cash: number;
  created_at: string;
  updated_at: string;
}

export interface Session {
  id: string;
  name: string;
  llm_account_id: string | null;
  skill_id: string | null;
  simulator_account_id: string | null;
  provider_id: string | null;
  model: string | null;
  status: string;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
}

export interface Message {
  id: string;
  session_id: string;
  role: "system" | "user" | "assistant" | "tool";
  content: string;
  message_type: string;
  trigger_id: string | null;
  parent_message_id: string | null;
  created_at: string;
}

export interface Run {
  id: string;
  session_id: string;
  provider_id: string | null;
  model: string | null;
  status: string;
  event_message_id: string | null;
  max_tool_rounds: number;
  started_at: string;
  finished_at: string | null;
  final_message_id: string | null;
  error: string | null;
}

export interface ToolSchema {
  name: string;
  display_name: string;
  description: string;
  parameters: Record<string, unknown>;
  strict: boolean;
}

export interface RuntimeEvent {
  type: string;
  session_id: string;
  run_id?: string;
  tool_call_id?: string;
  tool_name?: string;
  arguments_json?: string;
  ok?: boolean;
  result?: Record<string, unknown> | null;
  error?: string | null;
  status?: string;
  message?: Message;
}

export interface SessionTimelineItem {
  type: "message" | "tool_call" | "tool_result";
  id: string;
  session_id?: string | null;
  role?: "system" | "user" | "assistant" | "tool" | string | null;
  message_type?: string | null;
  content?: string | null;
  created_at?: string | null;
  run_id?: string | null;
  tool_call_id?: string | null;
  tool_name?: string | null;
  arguments_json?: string | null;
  result_json?: string | null;
  status?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  error?: string | null;
}

export interface MarketQuote {
  symbol: string;
  name?: string;
  price?: number;
  change?: number;
  pct_change?: number;
  open?: number;
  high?: number;
  low?: number;
  amount?: number;
  [key: string]: unknown;
}

export interface MarketHistoryResponse {
  symbol: string;
  interval: string;
  adjust: string;
  cache_hit: boolean;
  fetch_stats: Record<string, number> | null;
  bars: Record<string, unknown>[];
}

export interface FetchHistoryResponse {
  symbol: string;
  interval: string;
  adjust: string;
  fetched: number;
  inserted: number;
  skipped: number;
  conflicted: number;
}

export interface CacheStatusRow {
  symbol: string;
  name?: string | null;
  interval: string;
  adjust: string;
  start_datetime: string;
  end_datetime: string;
  bar_count: number;
  updated_at: string;
}

export interface DataConflict {
  id: string;
  symbol: string;
  interval: string;
  datetime: string;
  adjust: string;
  existing_value_json: string;
  new_value_json: string;
  source: string;
  fetch_time: string;
  status: string;
}

export interface ProviderModelsResponse {
  provider_id: string;
  models: string[];
}

export interface ProviderChatTestResponse {
  ok: boolean;
  content: string | null;
  model: string | null;
  latency_ms: number | null;
  error: string | null;
}

export interface ProviderUsageResponse {
  provider_id: string;
  total_runs: number;
  active_sessions: number;
  model: string;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    }
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail ?? detail;
    } catch {
      // Keep the HTTP status text when the server did not return JSON.
    }
    throw new Error(detail);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  providers: () => request<Provider[]>("/api/providers"),
  createProvider: (payload: Record<string, unknown>) =>
    request<Provider>("/api/providers", { method: "POST", body: JSON.stringify(payload) }),
  accounts: () => request<Account[]>("/api/accounts"),
  createAccount: (payload: Record<string, unknown>) =>
    request<Account>("/api/accounts", { method: "POST", body: JSON.stringify(payload) }),
  sessions: () => request<Session[]>("/api/sessions"),
  createSession: (payload: Record<string, unknown>) =>
    request<Session>("/api/sessions", { method: "POST", body: JSON.stringify(payload) }),
  updateSession: (sessionId: string, payload: Record<string, unknown>) =>
    request<Session>(`/api/sessions/${sessionId}`, { method: "PUT", body: JSON.stringify(payload) }),
  messages: (sessionId: string) => request<Message[]>(`/api/sessions/${sessionId}/messages`),
  createMessage: (sessionId: string, payload: Record<string, unknown>) =>
    request<Message>(`/api/sessions/${sessionId}/messages`, {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  sessionTimeline: (sessionId: string) => request<SessionTimelineItem[]>(`/api/sessions/${sessionId}/timeline`),
  runs: (sessionId: string) => request<Run[]>(`/api/sessions/${sessionId}/runs`),
  runSession: (sessionId: string, payload: Record<string, unknown>) =>
    request<Record<string, unknown>>(`/api/sessions/${sessionId}/run`, {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  tools: () => request<ToolSchema[]>("/api/tools"),
  testTool: (toolName: string, args: Record<string, unknown>) =>
    request<Record<string, unknown>>(`/api/tools/${toolName}/test`, {
      method: "POST",
      body: JSON.stringify({ arguments: args })
    }),
  quote: (symbol: string) => request<MarketQuote>(`/api/market/quote?symbol=${encodeURIComponent(symbol)}`),
  history: (params: { symbol: string; start?: string; end?: string; interval?: string; adjust?: string; allowFetchMissing?: boolean }) => {
    const query = new URLSearchParams();
    query.set("symbol", params.symbol);
    if (params.start) query.set("start", params.start);
    if (params.end) query.set("end", params.end);
    if (params.interval) query.set("interval", params.interval);
    if (params.adjust) query.set("adjust", params.adjust);
    if (params.allowFetchMissing) query.set("allow_fetch_missing", "true");
    return request<MarketHistoryResponse>(`/api/market/history?${query.toString()}`);
  },
  fetchHistory: (payload: { symbol: string; start: string; end: string; interval?: string; adjust?: string }) =>
    request<FetchHistoryResponse>("/api/data/fetch-history", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  cacheStatus: (params?: { symbol?: string; interval?: string }) => {
    const query = new URLSearchParams();
    if (params?.symbol) query.set("symbol", params.symbol);
    if (params?.interval) query.set("interval", params.interval);
    const suffix = query.toString();
    return request<CacheStatusRow[]>(`/api/data/cache-status${suffix ? `?${suffix}` : ""}`);
  },
  dataConflicts: (statusFilter?: string) => {
    const query = new URLSearchParams();
    if (statusFilter) query.set("status_filter", statusFilter);
    const suffix = query.toString();
    return request<DataConflict[]>(`/api/data/conflicts${suffix ? `?${suffix}` : ""}`);
  },
  resolveConflict: (conflictId: string, status: "resolved" | "ignored") =>
    request<DataConflict>(`/api/data/conflicts/${conflictId}/resolve`, {
      method: "POST",
      body: JSON.stringify({ status })
    }),
  // --- Provider 管理 ---
  updateProvider: (providerId: string, payload: Record<string, unknown>) =>
    request<Provider>(`/api/providers/${providerId}`, {
      method: "PUT",
      body: JSON.stringify(payload)
    }),
  deleteProvider: (providerId: string) =>
    request<void>(`/api/providers/${providerId}`, { method: "DELETE" }),
  providerModels: (providerId: string) =>
    request<ProviderModelsResponse>(`/api/providers/${providerId}/models`, {
      method: "POST"
    }),
  providerChatTest: (providerId: string, message?: string) =>
    request<ProviderChatTestResponse>(`/api/providers/${providerId}/chat-test`, {
      method: "POST",
      body: JSON.stringify({ message: message ?? "这是一个连接测试，你只需要回答\"1\"即可" })
    }),
  providerUsage: (providerId: string) =>
    request<ProviderUsageResponse>(`/api/providers/${providerId}/usage`),
  // --- Session 管理 ---
  deleteSession: (sessionId: string) =>
    request<void>(`/api/sessions/${sessionId}`, { method: "DELETE" })
};
