export type ProviderType = "openai_compatible" | "deepseek";

export interface Provider {
  id: string;
  provider_type: ProviderType;
  name: string;
  base_url: string;
  api_key_masked: string | null;
  has_api_key: boolean;
  model: string;
  available_models: string[];
  temperature: number;
  max_tokens: number | null;
  timeout_seconds: number;
  supports_tools: boolean;
  supports_parallel_tool_calls: boolean;
  supports_strict_schema: boolean;
  thinking_mode: string | null;
  strict_tool_schema: boolean;
  run_token_limit: number | null;
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
  llm_account_id?: string | null;
  skill_id: string | null;
  prompt_role_id: string | null;
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
  session_id?: string;
  run_id?: string;
  account_id?: string;
  clock?: ReplayClockState | null;
  tool_call_id?: string;
  tool_name?: string;
  order_id?: string;
  trade_id?: string;
  symbol?: string;
  side?: string;
  arguments_json?: string;
  ok?: boolean;
  result?: Record<string, unknown> | null;
  error?: string | null;
  status?: string;
  message?: Message;
  token?: string;
  source?: string;
  symbols?: string[];
  total_asset?: number;
  market_value?: number;
  unrealized_pnl?: number;
  generated_at?: string;
  valuation_point?: AssetPoint & { id?: string; simulator_account_id?: string };
}

export interface SessionTimelineItem {
  type: "message" | "tool_call" | "tool_result";
  id: string;
  session_id?: string | null;
  role?: "system" | "user" | "assistant" | "tool" | string | null;
  message_type?: string | null;
  content?: string | null;
  reasoning_content?: string | null;
  created_at?: string | null;
  run_id?: string | null;
  run_status?: string | null;
  run_token_usage?: string | null;
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

export interface MarketAnnouncementResponse {
  symbol: string;
  cache_hit: boolean;
  fetch_stats: Record<string, number> | null;
  announcements: Record<string, unknown>[];
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

export interface MarketWatchlistItem {
  id: string;
  symbol: string;
  name?: string | null;
  note: string;
  enabled: number | boolean;
  created_at: string;
  updated_at: string;
}

export interface MarketSyncRun {
  id: string;
  job_type: string;
  scope: string;
  symbols_json: string;
  status: string;
  fetched: number;
  inserted: number;
  skipped: number;
  conflicted: number;
  error?: string | null;
  started_at: string;
  finished_at?: string | null;
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
  llm_calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  thinking_tokens: number;
  total_tokens: number;
  latency_ms: number;
  avg_latency_ms: number;
  cap_exceeded_count: number;
}

export interface ReplayClockState {
  account_id: string;
  mode: "live" | "replay";
  replay_time: string | null;
  speed: number;
  effective_time: string;
  updated_at: string;
}

export interface UsageSummary {
  llm_calls: number;
  run_count: number;
  prompt_tokens: number;
  completion_tokens: number;
  thinking_tokens: number;
  total_tokens: number;
  latency_ms: number;
  avg_latency_ms: number;
  cap_exceeded_count: number;
}

export interface UsageGroupRow extends UsageSummary {
  id: string | null;
  name: string | null;
}

export interface UsageRunRow extends UsageSummary {
  run_id: string | null;
  session_id: string;
  session_name: string;
  account_id?: string | null;
  account_name?: string | null;
  provider_id: string | null;
  provider_name: string;
  model: string;
  created_at: string;
}

export interface UsageSummaryResponse {
  filters: Record<string, string | null>;
  summary: UsageSummary;
  by_provider: UsageGroupRow[];
  by_model: UsageGroupRow[];
  by_session: UsageGroupRow[];
  recent_runs: UsageRunRow[];
}

export interface TavilyConfig {
  configured: boolean;
  api_key_masked: string | null;
  default_search_depth: "basic" | "advanced";
  default_topic: "general" | "news" | "finance";
  default_max_results: number;
  cache_ttl_seconds: number;
  updated_at: string | null;
}

export interface TavilyUsageRecord {
  id: string;
  session_id: string | null;
  run_id: string | null;
  tool_call_id: string | null;
  operation: string;
  cache_hit: number;
  status: string;
  error: string | null;
  latency_ms: number | null;
  result_count: number;
  credits_estimated: number;
  created_at: string;
}

export interface TavilyUsageResponse {
  total_calls: number;
  cache_hits: number;
  credits_estimated: number;
  recent: TavilyUsageRecord[];
}

export interface TavilyTestResponse {
  ok: boolean;
  result_count: number;
  credits_estimated: number;
  latency_ms: number | null;
  error: string | null;
}

export interface StopRunResponse {
  status: "cancelled" | "not_running";
  run_id: string | null;
}

export interface PromptEntry {
  id: string;
  role_id: string;
  name: string;
  ref_name: string;
  content: string;
  enabled: boolean;
  builtin: boolean;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export interface PromptRole {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
  entries: PromptEntry[];
}

export type ViewTimeScope = "current_clock" | "all";

export interface ViewFilters {
  account_id?: string;
  session_id?: string;
  model?: string;
  start?: string;
  end?: string;
  symbol?: string;
  side?: string;
  status?: string;
  time_scope?: ViewTimeScope;
}

export interface AccountMetrics {
  initial_cash: number;
  cash: number;
  frozen_cash: number;
  total_asset: number;
  market_value: number;
  floating_pnl: number;
  total_pnl: number;
  total_return_pct: number;
  position_ratio: number;
  position_count: number;
  session_count: number;
  running_sessions: number;
}

export interface PositionRow {
  id: string;
  simulator_account_id: string;
  symbol: string;
  name: string;
  quantity: number;
  available_quantity: number;
  avg_cost: number;
  market_value: number;
  unrealized_pnl: number;
  updated_at: string;
}

export interface OrderRow {
  id: string;
  session_id: string | null;
  simulator_account_id: string;
  account_name?: string | null;
  session_name?: string | null;
  symbol: string;
  name: string;
  side: string;
  order_type: string;
  price: number;
  quantity: number;
  filled_quantity: number;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface TradeRow {
  id: string;
  order_id: string;
  session_id: string | null;
  simulator_account_id: string;
  account_name?: string | null;
  session_name?: string | null;
  symbol: string;
  name?: string | null;
  side: string;
  price: number;
  quantity: number;
  fee: number;
  tax: number;
  total_fee?: number;
  turnover?: number;
  run_id?: string | null;
  tool_call_id?: string | null;
  run_total_tokens?: number | null;
  run_prompt_tokens?: number | null;
  run_completion_tokens?: number | null;
  run_thinking_tokens?: number | null;
  run_llm_calls?: number | null;
  run_cap_exceeded_count?: number | null;
  run_latency_ms?: number | null;
  run_trade_count?: number | null;
  attributed_prompt_tokens?: number | null;
  attributed_completion_tokens?: number | null;
  attributed_thinking_tokens?: number | null;
  attributed_total_tokens?: number | null;
  attributed_latency_ms?: number | null;
  traded_at: string;
}

export interface AssetPointTrade {
  id: string;
  side: "buy" | "sell" | string;
  symbol: string;
  name?: string | null;
  price: number;
  quantity: number;
  turnover: number;
  fee: number;
  session_id?: string | null;
  session_name?: string | null;
  model?: string | null;
  provider_name?: string | null;
  run_id?: string | null;
  tool_call_id?: string | null;
}

export interface AssetPointPosition {
  symbol: string;
  name?: string | null;
  quantity: number;
  avg_cost: number;
  price?: number;
  market_value: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
}

export interface SessionContributionRow {
  session_id: string;
  session_name: string;
  provider_id?: string | null;
  provider_name?: string | null;
  provider_type?: string | null;
  model?: string | null;
  trade_count: number;
  buy_count: number;
  sell_count: number;
  turnover: number;
  fees: number;
  attributed_total_tokens?: number | null;
  attributed_latency_ms?: number | null;
}

export interface AssetPoint {
  time: string;
  cash: number;
  market_value: number;
  total_asset: number;
  pnl?: number;
  pnl_pct?: number;
  source: "initial" | "trade" | "current" | "valuation" | string;
  trade_id?: string;
  trade?: AssetPointTrade | null;
  unrealized_pnl?: number;
  symbols?: string[];
  positions?: AssetPointPosition[] | null;
  positions_recorded?: boolean;
}

export interface AccountSnapshot {
  account: Account;
  metrics: AccountMetrics;
  positions: PositionRow[];
  recent_orders: OrderRow[];
  recent_trades: TradeRow[];
  asset_points: AssetPoint[];
  sessions: Array<Session & { provider_name?: string | null; provider_type?: string | null }>;
  session_contributions?: SessionContributionRow[];
}

export interface AccountValuationRefreshResponse {
  generated_at: string;
  account: Account;
  metrics: AccountMetrics;
  valuation_point: (AssetPoint & { id?: string; simulator_account_id?: string }) | null;
  clock: ReplayClockState;
  symbols: string[];
  source: string;
}

export interface ViewLogRow {
  id: string;
  run_id?: string | null;
  session_id: string;
  session_name?: string | null;
  account_id?: string | null;
  account_name?: string | null;
  provider_id?: string | null;
  provider_name?: string | null;
  provider_type?: string | null;
  model?: string | null;
  tool_name: "order_buy" | "order_sell" | string;
  side: "buy" | "sell" | string;
  symbol?: string | null;
  quantity?: number | string | null;
  price?: number | string | null;
  status?: string | null;
  trade_reason: string;
  created_at: string;
  finished_at?: string | null;
  error?: string | null;
  result?: Record<string, unknown>;
}

export interface ViewTimelineRow {
  id: string;
  type: string;
  time: string;
  account_id?: string | null;
  account_name?: string | null;
  session_id?: string | null;
  session_name?: string | null;
  provider_id?: string | null;
  provider_name?: string | null;
  provider_type?: string | null;
  model?: string | null;
  run_id?: string | null;
  tool_call_id?: string | null;
  symbol?: string | null;
  title: string;
  summary: string;
  payload: Record<string, unknown>;
}

export interface ViewOverviewResponse {
  generated_at: string;
  filters: ViewFilters;
  summary: Record<string, number>;
  accounts: AccountSnapshot[];
  recent_trades: TradeRow[];
  recent_logs: ViewLogRow[];
  recent_tools?: ViewTimelineRow[];
  recent_errors?: ViewTimelineRow[];
}

export interface ViewAccountsResponse {
  generated_at: string;
  filters: ViewFilters;
  accounts: AccountSnapshot[];
}

export interface ViewTradesResponse {
  generated_at: string;
  filters: ViewFilters;
  summary: Record<string, number>;
  trades: TradeRow[];
}

export interface ViewAssetsResponse {
  generated_at: string;
  filters: ViewFilters;
  summary: Record<string, number>;
  series: Array<{ account_id: string; account_name: string; points: AssetPoint[] }>;
}

export interface ViewLogsResponse {
  generated_at: string;
  filters: ViewFilters;
  summary: Record<string, number>;
  logs: ViewLogRow[];
}

export interface ViewTimelineResponse {
  generated_at: string;
  filters: ViewFilters;
  summary: Record<string, number>;
  items: ViewTimelineRow[];
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

function viewQuery(filters?: ViewFilters & { limit?: number }): string {
  const query = new URLSearchParams();
  if (filters?.account_id) query.set("account_id", filters.account_id);
  if (filters?.session_id) query.set("session_id", filters.session_id);
  if (filters?.model) query.set("model", filters.model);
  if (filters?.start) query.set("start", filters.start);
  if (filters?.end) query.set("end", filters.end);
  if (filters?.symbol) query.set("symbol", filters.symbol);
  if (filters?.side) query.set("side", filters.side);
  if (filters?.status) query.set("status", filters.status);
  if (filters?.time_scope) query.set("time_scope", filters.time_scope);
  if (filters?.limit) query.set("limit", String(filters.limit));
  const suffix = query.toString();
  return suffix ? `?${suffix}` : "";
}

export const api = {
  providers: () => request<Provider[]>("/api/providers"),
  createProvider: (payload: Record<string, unknown>) =>
    request<Provider>("/api/providers", { method: "POST", body: JSON.stringify(payload) }),
  accounts: () => request<Account[]>("/api/simulator/accounts"),
  createAccount: (payload: Record<string, unknown>) =>
    request<Account>("/api/simulator/accounts", { method: "POST", body: JSON.stringify(payload) }),
  replayClock: (accountId: string) =>
    request<ReplayClockState>(`/api/simulator/accounts/${accountId}/replay-clock`),
  updateReplayClock: (accountId: string, payload: Record<string, unknown>) =>
    request<ReplayClockState>(`/api/simulator/accounts/${accountId}/replay-clock`, {
      method: "PUT",
      body: JSON.stringify(payload)
    }),
  restoreReplayClockLive: (accountId: string) =>
    request<ReplayClockState>(`/api/simulator/accounts/${accountId}/replay-clock/live`, {
      method: "POST"
    }),
  sessions: () => request<Session[]>("/api/sessions"),
  createSession: (payload: Record<string, unknown>) =>
    request<Session>("/api/sessions", { method: "POST", body: JSON.stringify(payload) }),
  updateSession: (sessionId: string, payload: Record<string, unknown>) =>
    request<Session>(`/api/sessions/${sessionId}`, { method: "PUT", body: JSON.stringify(payload) }),
  promptRoles: () => request<PromptRole[]>("/api/prompt-roles"),
  createPromptRole: (payload: Record<string, unknown>) =>
    request<PromptRole>("/api/prompt-roles", { method: "POST", body: JSON.stringify(payload) }),
  updatePromptRole: (roleId: string, payload: Record<string, unknown>) =>
    request<PromptRole>(`/api/prompt-roles/${roleId}`, { method: "PUT", body: JSON.stringify(payload) }),
  deletePromptRole: (roleId: string) =>
    request<void>(`/api/prompt-roles/${roleId}`, { method: "DELETE" }),
  importPromptRole: (payload: Record<string, unknown>) =>
    request<PromptRole>("/api/prompt-roles/import", { method: "POST", body: JSON.stringify(payload) }),
  exportPromptRole: (roleId: string) => request<PromptRole>(`/api/prompt-roles/${roleId}/export`),
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
  stopSession: (sessionId: string) =>
    request<StopRunResponse>(`/api/sessions/${sessionId}/stop`, {
      method: "POST"
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
  minute: (params: { symbol: string; start: string; end: string; period?: string; allowFetchMissing?: boolean }) => {
    const query = new URLSearchParams();
    query.set("symbol", params.symbol);
    query.set("start", params.start);
    query.set("end", params.end);
    if (params.period) query.set("period", params.period);
    if (params.allowFetchMissing) query.set("allow_fetch_missing", "true");
    return request<MarketHistoryResponse>(`/api/market/minute?${query.toString()}`);
  },
  announcement: (params: { symbol: string; start?: string; end?: string; allowFetchMissing?: boolean }) => {
    const query = new URLSearchParams();
    query.set("symbol", params.symbol);
    if (params.start) query.set("start", params.start);
    if (params.end) query.set("end", params.end);
    if (params.allowFetchMissing) query.set("allow_fetch_missing", "true");
    return request<MarketAnnouncementResponse>(`/api/market/announcement?${query.toString()}`);
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
  watchlist: () => request<MarketWatchlistItem[]>("/api/data/watchlist"),
  addWatchlistSymbol: (payload: { symbol: string; name?: string; note?: string; enabled?: boolean }) =>
    request<MarketWatchlistItem>("/api/data/watchlist", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  updateWatchlistSymbol: (itemId: string, payload: { name?: string; note?: string; enabled?: boolean }) =>
    request<MarketWatchlistItem>(`/api/data/watchlist/${itemId}`, {
      method: "PUT",
      body: JSON.stringify(payload)
    }),
  deleteWatchlistSymbol: (itemId: string) =>
    request<void>(`/api/data/watchlist/${itemId}`, { method: "DELETE" }),
  syncRuns: (limit = 30) => request<MarketSyncRun[]>(`/api/data/sync-runs?limit=${limit}`),
  runMarketSync: (payload: { job_type: string; scope?: string; period?: string }) =>
    request<MarketSyncRun>("/api/data/sync/run", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  viewOverview: (filters?: ViewFilters) =>
    request<ViewOverviewResponse>(`/api/view/overview${viewQuery(filters)}`),
  viewAccounts: (filters?: ViewFilters) =>
    request<ViewAccountsResponse>(`/api/view/accounts${viewQuery(filters)}`),
  accountSnapshot: (accountId: string, filters?: Omit<ViewFilters, "account_id">) =>
    request<AccountSnapshot>(`/api/view/accounts/${accountId}/snapshot${viewQuery(filters)}`),
  accountValuationRefresh: (accountId: string) =>
    request<AccountValuationRefreshResponse>(`/api/view/accounts/${accountId}/valuation/refresh`, {
      method: "POST"
    }),
  viewTrades: (filters?: ViewFilters & { limit?: number }) =>
    request<ViewTradesResponse>(`/api/view/trades${viewQuery(filters)}`),
  viewAssets: (filters?: ViewFilters) =>
    request<ViewAssetsResponse>(`/api/view/assets${viewQuery(filters)}`),
  viewLogs: (filters?: ViewFilters & { limit?: number }) =>
    request<ViewLogsResponse>(`/api/view/logs${viewQuery(filters)}`),
  viewTimeline: (filters?: ViewFilters & { limit?: number }) =>
    request<ViewTimelineResponse>(`/api/view/timeline${viewQuery(filters)}`),
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
  tavilyConfig: () => request<TavilyConfig>("/api/tavily/config"),
  updateTavilyConfig: (payload: Record<string, unknown>) =>
    request<TavilyConfig>("/api/tavily/config", {
      method: "PUT",
      body: JSON.stringify(payload)
    }),
  tavilyUsage: () => request<TavilyUsageResponse>("/api/tavily/usage"),
  usageSummary: () => request<UsageSummaryResponse>("/api/usage/summary"),
  testTavily: () =>
    request<TavilyTestResponse>("/api/tavily/test", {
      method: "POST"
    }),
  // --- Session 管理 ---
  deleteSession: (sessionId: string) =>
    request<void>(`/api/sessions/${sessionId}`, { method: "DELETE" })
};
