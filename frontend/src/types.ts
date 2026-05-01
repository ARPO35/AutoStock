export type RouteKey = "trade" | "view" | "edit" | "manage";
export type SessionStatus = "idle" | "running" | "queued" | "error" | "archived";
export type TimelineKind =
  | "user"
  | "event"
  | "assistant"
  | "reasoning"
  | "tool-call"
  | "tool-result"
  | "order"
  | "error";

export interface UIAccount {
  id: string;
  name: string;
  broker: string;
  initialCash: number;
  cash: number;
  availableCash: number;
  frozenCash: number;
  marketValue: number;
  totalAsset: number;
  todayPnl: number;
  todayPnlPct: number;
  totalPnl: number;
  totalPnlPct: number;
  runningSessions: number;
}

export interface UISession {
  id: string;
  accountId: string;
  name: string;
  providerId: string;
  providerType: "openai_compatible" | "deepseek";
  providerName: string;
  model: string;
  skillId: string;
  skillName: string;
  status: SessionStatus;
  lastRunAt: string;
  hasTriggers: boolean;
  mode: "realtime" | "replay";
}

export interface Holding {
  symbol: string;
  name: string;
  quantity: number;
  sellable: number;
  cost: number;
  price: number;
  marketValue: number;
  pnl: number;
  pnlPct: number;
  todayPct: number;
  sourceSession: string;
  latestReason: string;
  sparkline: number[];
}

export interface TradeRecord {
  id: string;
  time: string;
  accountId: string;
  sessionId: string;
  model: string;
  symbol: string;
  name: string;
  side: "buy" | "sell";
  quantity: number;
  price: number;
  amount: number;
  fee: number;
  tax: number;
  status: string;
  toolCallId: string;
}

export interface PortfolioPoint {
  label: string;
  total: number;
  cash: number;
  market: number;
  benchmark?: number;
}

export interface SearchResultItem {
  title: string;
  domain: string;
  summary: string;
  url: string;
  publishedAt: string;
  score: number;
}

export interface QuoteResult {
  symbol: string;
  name: string;
  price: number;
  change: number;
  changePct: number;
  open: number;
  high: number;
  low: number;
  amountText: string;
}

export interface HistoryResult {
  symbol: string;
  name: string;
  period: string;
  adjust: string;
  candles: number[];
  volumes: number[];
}

export interface OrderResult {
  status: "买入成功" | "买入失败" | "部分成交" | "卖出成功";
  symbol: string;
  name: string;
  quantity: number;
  orderPrice: number;
  filledPrice: number;
  fee: number;
  sourceSession: string;
  sourceModel: string;
}

export type ToolResultPayload =
  | { kind: "search"; query: string; items: SearchResultItem[] }
  | { kind: "quote"; quote: QuoteResult }
  | { kind: "history"; history: HistoryResult }
  | { kind: "order"; order: OrderResult }
  | { kind: "portfolio"; account: UIAccount }
  | { kind: "json"; title: string; data: Record<string, unknown> };

export interface TimelineItem {
  id: string;
  kind: TimelineKind;
  time: string;
  title: string;
  body?: string;
  runId?: string;
  toolName?: string;
  status?: string;
  durationMs?: number;
  argsSummary?: string;
  result?: ToolResultPayload;
  raw?: Record<string, unknown>;
}

export interface ProviderCard {
  id: string;
  name: string;
  type: "OpenAI-Compatible" | "DeepSeek";
  endpoint: string;
  modelCount: number;
  status: "已连接" | "未配置";
  updatedAt: string;
  supportsReasoning: boolean;
}

export interface DecisionLog {
  time: string;
  account: string;
  session: string;
  model: string;
  trigger: string;
  toolCalls: number;
  action: string;
  cost: string;
  result: string;
}
