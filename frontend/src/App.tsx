import {
  Activity,
  AlertTriangle,
  Bell,
  Bot,
  CheckCircle2,
  ChevronDown,
  Clock3,
  Code2,
  Database,
  Eye,
  Gauge,
  History,
  KeyRound,
  LineChart,
  MessageSquare,
  Pause,
  Play,
  Plus,
  RefreshCw,
  Save,
  Search,
  Send,
  Settings,
  ShieldAlert,
  SlidersHorizontal,
  StopCircle,
  Table2,
  UserRound,
  Wallet,
  Wrench,
  Zap
} from "lucide-react";
import { CSSProperties, FormEvent, MouseEvent, ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { Account, CacheStatusRow, DataConflict, FetchHistoryResponse, MarketHistoryResponse, MarketQuote, Provider, ProviderType, RuntimeEvent, Session, SessionTimelineItem, ToolSchema, api } from "./api";
import type { AccountView, ProviderCard, RouteKey, SessionStatus, SessionView, TimelineItem, ToolResultPayload } from "./types";

const navItems: Array<{ key: RouteKey; label: string; sub: string }> = [
  { key: "trade", label: "交易（LLM）", sub: "WebChat 工作台" },
  { key: "view", label: "查看", sub: "全局观察" },
  { key: "edit", label: "修改", sub: "审计修改" },
  { key: "manage", label: "管理", sub: "能力配置" }
];
const viewTabs = ["总览", "账号详情", "交易历史", "资产曲线", "股票信息", "决策日志", "时间线控制"];
const editTabs = ["账户信息", "余额修改", "持仓修改", "订单修正", "会话绑定"];
const manageSections = ["模型与API", "Skills", "Tools", "触发器", "数据管理", "系统设置"];
const defaultProvider: { provider_type: ProviderType; name: string; base_url: string; api_key: string; model: string } = {
  provider_type: "deepseek",
  name: "",
  base_url: "",
  api_key: "",
  model: ""
};
const defaultMarketForm = { symbol: "", start: "", end: "", adjust: "", allowFetchMissing: false };
const defaultDataFetchForm = { symbol: "", start: "", end: "", adjust: "" };
const moneyFormatter = new Intl.NumberFormat("zh-CN", { style: "currency", currency: "CNY", maximumFractionDigits: 2 });

function routeFromPath(pathname: string): RouteKey {
  const first = pathname.split("/").filter(Boolean)[0];
  return first === "view" || first === "edit" || first === "manage" ? first : "trade";
}
function formatMoney(value: number | null | undefined): string {
  return value == null ? "--" : moneyFormatter.format(value);
}
function normalizeStatus(status: string | null | undefined): SessionStatus {
  const value = (status ?? "idle").toLowerCase();
  if (value.includes("run")) return "running";
  if (value.includes("queue")) return "queued";
  if (value.includes("error") || value.includes("fail")) return "error";
  if (value.includes("archive")) return "archived";
  return "idle";
}
function statusLabel(status: SessionStatus): string {
  return { idle: "空闲", running: "运行中", queued: "排队", error: "报错", archived: "归档" }[status];
}
function humanTime(value: string | null | undefined): string {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", { hour12: false, month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}
function parseJsonObject(value: string | null | undefined): Record<string, unknown> {
  if (!value) return {};
  try {
    const parsed = JSON.parse(value) as unknown;
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed as Record<string, unknown> : { value: parsed };
  } catch {
    return { content: value };
  }
}
function parseInputObject(value: string): Record<string, unknown> | null {
  try {
    const parsed = JSON.parse(value || "{}") as unknown;
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed as Record<string, unknown> : null;
  } catch {
    return null;
  }
}
function formatValue(value: unknown): string {
  if (value == null || value === "") return "--";
  if (typeof value === "number") return Number.isFinite(value) ? String(value) : "--";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}
function summarizeArgs(value: string | null | undefined): string {
  const parsed = parseJsonObject(value);
  const entries = Object.entries(parsed).slice(0, 3);
  if (entries.length === 0) return "无参数";
  return entries.map(([key, item]) => `${key}: ${formatValue(item)}`).join(" / ");
}
function objectEntries(data: Record<string, unknown>): Array<[string, string]> {
  return Object.entries(data).map(([key, value]) => [key, formatValue(value)]);
}
function providerTypeLabel(type: ProviderType | string | null | undefined): "OpenAI-Compatible" | "DeepSeek" {
  return type === "deepseek" ? "DeepSeek" : "OpenAI-Compatible";
}
function barClose(bar: Record<string, unknown>): number | null {
  const value = Number(bar.close ?? bar.Close ?? bar.price ?? bar["收盘"]);
  return Number.isFinite(value) ? value : null;
}
function barTime(bar: Record<string, unknown>): string {
  return formatValue(bar.datetime ?? bar.date ?? bar.time ?? bar["日期"]);
}
function conflictSummary(conflict: DataConflict): string {
  return `${Object.keys(parseJsonObject(conflict.existing_value_json)).length} old / ${Object.keys(parseJsonObject(conflict.new_value_json)).length} new`;
}

export default function App() {
  const [route, setRoute] = useState<RouteKey>(() => routeFromPath(window.location.pathname));
  const [providers, setProviders] = useState<Provider[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [timelineSource, setTimelineSource] = useState<SessionTimelineItem[]>([]);
  const [tools, setTools] = useState<ToolSchema[]>([]);
  const [events, setEvents] = useState<RuntimeEvent[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState("");
  const [providerForm, setProviderForm] = useState(defaultProvider);
  const [accountName, setAccountName] = useState("");
  const [accountProviderId, setAccountProviderId] = useState("");
  const [accountInitialCash, setAccountInitialCash] = useState("");
  const [sessionName, setSessionName] = useState("");
  const [sessionAccountId, setSessionAccountId] = useState("");
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [viewTab, setViewTab] = useState(viewTabs[0]);
  const [editTab, setEditTab] = useState(editTabs[0]);
  const [manageSection, setManageSection] = useState(manageSections[0]);
  const [marketForm, setMarketForm] = useState(defaultMarketForm);
  const [marketQuote, setMarketQuote] = useState<MarketQuote | null>(null);
  const [marketHistory, setMarketHistory] = useState<MarketHistoryResponse | null>(null);
  const [cacheRows, setCacheRows] = useState<CacheStatusRow[]>([]);
  const [dataFetchForm, setDataFetchForm] = useState(defaultDataFetchForm);
  const [dataFetchResult, setDataFetchResult] = useState<FetchHistoryResponse | null>(null);
  const [conflicts, setConflicts] = useState<DataConflict[]>([]);
  const [selectedToolName, setSelectedToolName] = useState("");
  const [toolArgs, setToolArgs] = useState("{}");
  const [toolResult, setToolResult] = useState<Record<string, unknown> | null>(null);
  const [leftCollapsed, setLeftCollapsed] = useState(false);
  const [inspectorWidth, setInspectorWidth] = useState(() => {
    const stored = Number(window.localStorage.getItem("autostock.inspectorWidth"));
    return Number.isFinite(stored) && stored >= 420 ? stored : 460;
  });
  const dragRef = useRef(false);

  const providerById = useMemo(() => new Map(providers.map((provider) => [provider.id, provider])), [providers]);
  const accountViews = useMemo<AccountView[]>(() => accounts.map((account) => {
    const provider = providerById.get(account.provider_id);
    const relatedSessions = sessions.filter((session) => session.llm_account_id === account.id);
    return {
      id: account.id,
      name: account.name,
      providerId: account.provider_id,
      providerName: provider?.name ?? null,
      initialCash: account.initial_cash,
      createdAt: account.created_at,
      updatedAt: account.updated_at,
      sessionCount: relatedSessions.length,
      runningSessions: relatedSessions.filter((session) => normalizeStatus(session.status) === "running").length
    };
  }), [accounts, providerById, sessions]);
  const accountById = useMemo(() => new Map(accountViews.map((account) => [account.id, account])), [accountViews]);
  const sessionViews = useMemo<SessionView[]>(() => sessions.map((session) => {
    const account = session.llm_account_id ? accountById.get(session.llm_account_id) : null;
    const provider = account?.providerId ? providerById.get(account.providerId) : null;
    return {
      id: session.id,
      name: session.name,
      accountId: session.llm_account_id,
      accountName: account?.name ?? null,
      providerId: provider?.id ?? null,
      providerName: provider?.name ?? null,
      providerType: provider?.provider_type ?? null,
      model: provider?.model ?? null,
      skillId: session.skill_id,
      status: normalizeStatus(session.status),
      lastRunAt: session.updated_at
    };
  }), [accountById, providerById, sessions]);
  const selectedSession = useMemo(() => sessionViews.find((session) => session.id === selectedSessionId) ?? null, [selectedSessionId, sessionViews]);
  const selectedAccount = useMemo(() => selectedSession?.accountId ? accountById.get(selectedSession.accountId) ?? null : null, [accountById, selectedSession]);
  const providerCards = useMemo<ProviderCard[]>(() => providers.map((provider) => ({
    id: provider.id,
    name: provider.name,
    type: providerTypeLabel(provider.provider_type),
    endpoint: provider.base_url || "未配置 endpoint",
    model: provider.model,
    status: provider.has_api_key ? "已连接" : "未配置",
    updatedAt: humanTime(provider.updated_at),
    supportsTools: provider.supports_tools,
    supportsStrictSchema: provider.supports_strict_schema,
    supportsReasoning: provider.thinking_mode === "thinking" || provider.provider_type === "deepseek"
  })), [providers]);
  const timeline = useMemo(() => buildTimeline(timelineSource), [timelineSource]);
  const selectedTool = useMemo(() => tools.find((tool) => tool.name === selectedToolName) ?? null, [selectedToolName, tools]);

  useEffect(() => { void loadAll(); void loadDataState(); }, []);
  useEffect(() => {
    const onPop = () => setRoute(routeFromPath(window.location.pathname));
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);
  useEffect(() => {
    if (!selectedSessionId && sessions.length > 0) setSelectedSessionId(sessions[0].id);
    if (selectedSessionId && !sessions.some((session) => session.id === selectedSessionId)) setSelectedSessionId(sessions[0]?.id ?? "");
  }, [selectedSessionId, sessions]);
  useEffect(() => {
    if (!selectedToolName && tools.length > 0) setSelectedToolName(tools[0].name);
    if (selectedToolName && !tools.some((tool) => tool.name === selectedToolName)) setSelectedToolName(tools[0]?.name ?? "");
  }, [selectedToolName, tools]);
  useEffect(() => {
    if (!selectedSessionId) { setTimelineSource([]); setEvents([]); return; }
    void loadTimeline(selectedSessionId);
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const socket = new WebSocket(`${protocol}//${window.location.host}/ws/sessions/${selectedSessionId}`);
    socket.onmessage = (event) => {
      const payload = JSON.parse(event.data) as RuntimeEvent;
      setEvents((current) => [payload, ...current].slice(0, 60));
      void loadTimeline(selectedSessionId);
      if (["run_finished", "assistant_message", "error"].includes(payload.type)) void loadSessions();
    };
    socket.onerror = () => setError("WebSocket 连接失败，请确认后端服务可用。");
    return () => socket.close();
  }, [selectedSessionId]);
  useEffect(() => {
    const onMouseMove = (event: globalThis.MouseEvent) => {
      if (!dragRef.current) return;
      const next = Math.min(Math.max(window.innerWidth - event.clientX, 420), Math.round(window.innerWidth * 0.7));
      setInspectorWidth(next);
      window.localStorage.setItem("autostock.inspectorWidth", String(next));
    };
    const onMouseUp = () => { dragRef.current = false; document.body.classList.remove("is-resizing"); };
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
    return () => { window.removeEventListener("mousemove", onMouseMove); window.removeEventListener("mouseup", onMouseUp); };
  }, []);

  async function loadAll() {
    setError(null);
    try {
      const [nextProviders, nextAccounts, nextSessions, nextTools] = await Promise.all([api.providers(), api.accounts(), api.sessions(), api.tools()]);
      setProviders(nextProviders);
      setAccounts(nextAccounts);
      setSessions(nextSessions);
      setTools(nextTools);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载前端状态失败，请确认后端服务可用。");
    }
  }
  async function loadDataState() {
    try {
      const [nextCacheRows, nextConflicts] = await Promise.all([api.cacheStatus(), api.dataConflicts("open")]);
      setCacheRows(nextCacheRows);
      setConflicts(nextConflicts);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载数据缓存状态失败。");
    }
  }
  async function refreshAll() {
    setBusy(true); setError(null);
    try {
      await Promise.all([loadAll(), loadDataState(), selectedSessionId ? loadTimeline(selectedSessionId) : Promise.resolve()]);
    } finally { setBusy(false); }
  }
  async function loadSessions() { setSessions(await api.sessions()); }
  async function loadTimeline(sessionId: string) { setTimelineSource(await api.sessionTimeline(sessionId)); }
  function navigate(next: RouteKey) { setRoute(next); if (window.location.pathname !== `/${next}`) window.history.pushState({}, "", `/${next}`); }
  function startResize(event: MouseEvent<HTMLDivElement>) { event.preventDefault(); dragRef.current = true; document.body.classList.add("is-resizing"); }

  async function createProvider(event: FormEvent) {
    event.preventDefault();
    if (!providerForm.name.trim() || !providerForm.model.trim() || !providerForm.api_key.trim()) { setError("请填写 Provider 名称、模型和 API Key。"); return; }
    setBusy(true); setError(null);
    try {
      const created = await api.createProvider({
        provider_type: providerForm.provider_type,
        name: providerForm.name.trim(),
        base_url: providerForm.base_url.trim() || null,
        api_key: providerForm.api_key,
        model: providerForm.model.trim(),
        supports_tools: true,
        supports_strict_schema: false,
        strict_tool_schema: false
      });
      setProviders((current) => [created, ...current]);
      setProviderForm(defaultProvider);
    } catch (err) { setError(err instanceof Error ? err.message : "创建 Provider 失败。"); } finally { setBusy(false); }
  }
  async function createAccount(event: FormEvent) {
    event.preventDefault();
    if (!accountProviderId) { setError("请选择 Provider，不能隐式使用默认 Provider。"); return; }
    if (!accountName.trim()) { setError("请填写账户名称。"); return; }
    if (accountInitialCash.trim() && !Number.isFinite(Number(accountInitialCash))) { setError("初始资金必须是数字，或留空使用后端默认值。"); return; }
    setBusy(true); setError(null);
    try {
      const payload: Record<string, unknown> = { name: accountName.trim(), provider_id: accountProviderId };
      if (accountInitialCash.trim()) payload.initial_cash = Number(accountInitialCash);
      const created = await api.createAccount(payload);
      setAccounts((current) => [created, ...current]);
      setAccountName("");
      setAccountInitialCash("");
    } catch (err) { setError(err instanceof Error ? err.message : "创建账户失败。"); } finally { setBusy(false); }
  }
  async function createSession(event?: FormEvent) {
    event?.preventDefault();
    if (!sessionAccountId) { setError("请选择账户，不能隐式使用默认账户。"); return; }
    if (!sessionName.trim()) { setError("请填写 Session 名称。"); return; }
    setBusy(true); setError(null);
    try {
      const created = await api.createSession({ name: sessionName.trim(), llm_account_id: sessionAccountId });
      setSessions((current) => [created, ...current]);
      setSelectedSessionId(created.id);
      setSessionName("");
    } catch (err) { setError(err instanceof Error ? err.message : "创建 Session 失败。"); } finally { setBusy(false); }
  }
  async function sendMessage(mode: "run" | "event" | "write") {
    if (!selectedSession || !draft.trim()) return;
    const content = draft.trim();
    setDraft(""); setBusy(true); setError(null);
    try {
      if (mode === "write") await api.createMessage(selectedSession.id, { role: "user", content, message_type: "user" });
      else await api.runSession(selectedSession.id, { message: mode === "event" ? `[手动事件]\n${content}` : content, max_tool_rounds: 5 });
      await loadTimeline(selectedSession.id);
      await loadSessions();
    } catch (err) { setError(err instanceof Error ? err.message : "发送失败。"); } finally { setBusy(false); }
  }
  async function runSelectedOnce() {
    if (!selectedSession) return;
    setBusy(true); setError(null);
    try {
      await api.runSession(selectedSession.id, { max_tool_rounds: 5 });
      await loadTimeline(selectedSession.id);
      await loadSessions();
    } catch (err) { setError(err instanceof Error ? err.message : "运行失败。"); } finally { setBusy(false); }
  }
  async function queryQuote(event?: FormEvent) {
    event?.preventDefault();
    const symbol = marketForm.symbol.trim();
    if (!symbol) { setError("请输入股票代码。"); return; }
    setBusy(true); setError(null);
    try {
      setMarketQuote(await api.quote(symbol));
      await loadDataState();
    } catch (err) { setError(err instanceof Error ? err.message : "查询行情失败。"); } finally { setBusy(false); }
  }
  async function queryHistory(event?: FormEvent) {
    event?.preventDefault();
    const symbol = marketForm.symbol.trim();
    if (!symbol) { setError("请输入股票代码。"); return; }
    if (marketForm.allowFetchMissing && (!marketForm.start || !marketForm.end)) { setError("允许缺失拉取时必须填写起止日期。"); return; }
    setBusy(true); setError(null);
    try {
      setMarketHistory(await api.history({ symbol, start: marketForm.start || undefined, end: marketForm.end || undefined, interval: "daily", adjust: marketForm.adjust, allowFetchMissing: marketForm.allowFetchMissing }));
      await loadDataState();
    } catch (err) { setError(err instanceof Error ? err.message : "查询历史行情失败。"); } finally { setBusy(false); }
  }
  async function fetchHistory(event: FormEvent) {
    event.preventDefault();
    const symbol = dataFetchForm.symbol.trim();
    if (!symbol || !dataFetchForm.start || !dataFetchForm.end) { setError("请填写股票代码、起始日期和结束日期。"); return; }
    setBusy(true); setError(null);
    try {
      setDataFetchResult(await api.fetchHistory({ symbol, start: dataFetchForm.start, end: dataFetchForm.end, interval: "daily", adjust: dataFetchForm.adjust }));
      await loadDataState();
    } catch (err) { setError(err instanceof Error ? err.message : "拉取历史数据失败。"); } finally { setBusy(false); }
  }
  async function runToolTest(event: FormEvent) {
    event.preventDefault();
    if (!selectedToolName) { setError("请选择工具。"); return; }
    const args = parseInputObject(toolArgs);
    if (!args) { setError("工具参数必须是 JSON object。"); return; }
    setBusy(true); setError(null);
    try {
      setToolResult(await api.testTool(selectedToolName, args));
      await loadDataState();
    } catch (err) { setError(err instanceof Error ? err.message : "工具测试失败。"); } finally { setBusy(false); }
  }
  async function resolveConflict(conflictId: string, status: "resolved" | "ignored") {
    setBusy(true); setError(null);
    try {
      await api.resolveConflict(conflictId, status);
      await loadDataState();
    } catch (err) { setError(err instanceof Error ? err.message : "处理数据冲突失败。"); } finally { setBusy(false); }
  }
  const shellStyle = { "--inspector-width": `${inspectorWidth}px` } as CSSProperties;
  return (
    <main className="app-shell" style={shellStyle}>
      <TopNavigation route={route} onNavigate={navigate} providerCount={providers.length} hasSelectedSession={Boolean(selectedSession)} />
      {error && <div className="global-error"><AlertTriangle size={16} />{error}</div>}
      {route === "trade" && <TradePage accounts={accountViews} sessions={sessionViews} selectedAccount={selectedAccount} selectedSession={selectedSession} selectedSessionId={selectedSessionId} onSelectSession={setSelectedSessionId} onCreateSession={createSession} sessionName={sessionName} setSessionName={setSessionName} sessionAccountId={sessionAccountId} setSessionAccountId={setSessionAccountId} timeline={timeline} events={events} draft={draft} setDraft={setDraft} sendMessage={sendMessage} runSelectedOnce={runSelectedOnce} busy={busy} leftCollapsed={leftCollapsed} setLeftCollapsed={setLeftCollapsed} onStartResize={startResize} />}
      {route === "view" && <ViewPage tab={viewTab} setTab={setViewTab} accounts={accountViews} sessions={sessionViews} providers={providers} marketForm={marketForm} setMarketForm={setMarketForm} marketQuote={marketQuote} marketHistory={marketHistory} cacheRows={cacheRows} onQueryQuote={queryQuote} onQueryHistory={queryHistory} onRefresh={refreshAll} busy={busy} />}
      {route === "edit" && <EditPage tab={editTab} setTab={setEditTab} providers={providers} accounts={accountViews} sessions={sessionViews} accountName={accountName} setAccountName={setAccountName} accountProviderId={accountProviderId} setAccountProviderId={setAccountProviderId} accountInitialCash={accountInitialCash} setAccountInitialCash={setAccountInitialCash} sessionName={sessionName} setSessionName={setSessionName} sessionAccountId={sessionAccountId} setSessionAccountId={setSessionAccountId} createAccount={createAccount} createSession={createSession} busy={busy} />}
      {route === "manage" && <ManagePage section={manageSection} setSection={setManageSection} providerCards={providerCards} tools={tools} providerForm={providerForm} setProviderForm={setProviderForm} createProvider={createProvider} busy={busy} selectedToolName={selectedToolName} setSelectedToolName={setSelectedToolName} selectedTool={selectedTool} toolArgs={toolArgs} setToolArgs={setToolArgs} toolResult={toolResult} runToolTest={runToolTest} dataFetchForm={dataFetchForm} setDataFetchForm={setDataFetchForm} dataFetchResult={dataFetchResult} cacheRows={cacheRows} conflicts={conflicts} fetchHistory={fetchHistory} resolveConflict={resolveConflict} onRefresh={refreshAll} />}
    </main>
  );
}

function buildTimeline(source: SessionTimelineItem[]): TimelineItem[] {
  const callsById = new Map(source.filter((item) => item.type === "tool_call").map((item) => [item.id, item]));
  return source.map((item) => {
    if (item.type === "message") return messageTimelineItem(item);
    if (item.type === "tool_call") {
      return {
        id: item.id,
        kind: "tool-call",
        time: humanTime(item.started_at),
        title: "Tool Call",
        runId: item.run_id,
        toolCallId: item.tool_call_id ?? item.id,
        toolName: item.tool_name,
        status: item.status,
        argsSummary: summarizeArgs(item.arguments_json),
        raw: { ...item, arguments: parseJsonObject(item.arguments_json) }
      };
    }
    const call = item.tool_call_id ? callsById.get(item.tool_call_id) : undefined;
    const parsed = parseJsonObject(item.result_json);
    return {
      id: item.id,
      kind: parsed.error ? "error" : "tool-result",
      time: humanTime(item.created_at),
      title: parsed.error ? "工具错误" : "工具结果",
      runId: item.run_id,
      toolCallId: item.tool_call_id,
      toolName: call?.tool_name ?? null,
      body: typeof parsed.error === "string" ? parsed.error : undefined,
      result: classifyToolResult(call?.tool_name, parsed),
      raw: parsed
    };
  });
}
function messageTimelineItem(item: SessionTimelineItem): TimelineItem {
  const role = item.role ?? "user";
  const kind = role === "assistant" ? "assistant" : item.message_type === "event" ? "event" : role === "tool" ? "tool-result" : "user";
  return {
    id: item.id,
    kind,
    time: humanTime(item.created_at),
    title: role === "assistant" ? "助手" : item.message_type === "event" ? "事件" : role === "tool" ? "工具消息" : "用户",
    body: item.content || "",
    raw: { role: item.role, message_type: item.message_type }
  };
}
function classifyToolResult(toolName: string | null | undefined, envelope: Record<string, unknown>): ToolResultPayload {
  const result = envelope.result && typeof envelope.result === "object" && !Array.isArray(envelope.result) ? envelope.result as Record<string, unknown> : envelope;
  if (toolName === "market_quote") return { kind: "quote", quote: result };
  if (toolName === "market_history") return { kind: "history", history: result, bars: Array.isArray(result.bars) ? result.bars as Record<string, unknown>[] : [] };
  if (toolName === "data_fetch_history") return { kind: "fetch-history", stats: result };
  return { kind: "json", title: toolName ? `${toolName} 结果` : "工具结果", data: envelope };
}

function TopNavigation({ route, onNavigate, providerCount, hasSelectedSession }: { route: RouteKey; onNavigate: (route: RouteKey) => void; providerCount: number; hasSelectedSession: boolean }) {
  return (
    <header className="top-navigation">
      <button className="brand-lockup" type="button" onClick={() => onNavigate("trade")}>
        <span className="brand-mark">A</span>
        <span><strong>A股 LLM 交易系统</strong><small>模拟盘 · 可见推理 · 工具追踪</small></span>
      </button>
      <nav className="primary-tabs" aria-label="一级导航">
        {navItems.map((item) => <button className={route === item.key ? "primary-tab active" : "primary-tab"} key={item.key} onClick={() => onNavigate(item.key)} type="button"><span>{item.label}</span><small>{item.sub}</small></button>)}
      </nav>
      <div className="top-meta"><span>{providerCount > 0 ? `${providerCount} Provider` : "未配置 Provider"}</span><span>{hasSelectedSession ? "已选择 Session" : "暂无会话"}</span><span className="avatar-dot"><UserRound size={14} /></span></div>
    </header>
  );
}
function TradePage(props: {
  accounts: AccountView[]; sessions: SessionView[]; selectedAccount: AccountView | null; selectedSession: SessionView | null; selectedSessionId: string;
  onSelectSession: (id: string) => void; onCreateSession: (event?: FormEvent) => void; sessionName: string; setSessionName: (value: string) => void;
  sessionAccountId: string; setSessionAccountId: (value: string) => void;
  timeline: TimelineItem[]; events: RuntimeEvent[]; draft: string; setDraft: (value: string) => void; sendMessage: (mode: "run" | "event" | "write") => void; runSelectedOnce: () => void; busy: boolean;
  leftCollapsed: boolean; setLeftCollapsed: (value: boolean) => void; onStartResize: (event: MouseEvent<HTMLDivElement>) => void;
}) {
  return <section className={props.leftCollapsed ? "trade-workspace collapsed" : "trade-workspace"}><AccountSessionSidebar {...props} /><section className="chat-workspace panel-frame"><SessionHeader selectedAccount={props.selectedAccount} selectedSession={props.selectedSession} onRunOnce={props.runSelectedOnce} busy={props.busy} /><LLMLinearTimeline timeline={props.timeline} hasSession={Boolean(props.selectedSession)} /><ChatInputBox draft={props.draft} setDraft={props.setDraft} sendMessage={props.sendMessage} busy={props.busy} disabled={!props.selectedSession} /></section><div className="resize-handle" onMouseDown={props.onStartResize} aria-label="调整账户观察栏宽度" /><AccountInspectorPanel account={props.selectedAccount} session={props.selectedSession} events={props.events} /></section>;
}
function AccountSessionSidebar(props: { accounts: AccountView[]; sessions: SessionView[]; selectedSessionId: string; onSelectSession: (id: string) => void; onCreateSession: (event?: FormEvent) => void; sessionName: string; setSessionName: (value: string) => void; sessionAccountId: string; setSessionAccountId: (value: string) => void; leftCollapsed: boolean; setLeftCollapsed: (value: boolean) => void }) {
  if (props.leftCollapsed) return <aside className="account-rail collapsed-rail"><button className="rail-toggle" type="button" onClick={() => props.setLeftCollapsed(false)} title="展开账户栏"><ChevronDown size={16} /></button>{props.accounts.map((account) => <button className="rail-account" key={account.id} type="button" title="折叠态账户跳转尚未接入" disabled>{account.name.slice(0, 1)}</button>)}</aside>;
  return <aside className="account-rail panel-frame"><div className="rail-head"><div><p className="eyebrow">账户与会话</p><h2>Account Tree</h2></div><button className="ghost-button square" type="button" onClick={() => props.setLeftCollapsed(true)} title="折叠账户栏"><ChevronDown size={16} /></button></div><label className="search-field"><Search size={15} /><input placeholder="搜索尚未接入" disabled /></label><form className="create-session" onSubmit={props.onCreateSession}><select value={props.sessionAccountId} onChange={(event) => props.setSessionAccountId(event.target.value)} disabled={props.accounts.length === 0}><option value="">选择账户</option>{props.accounts.map((account) => <option key={account.id} value={account.id}>{account.name}</option>)}</select><input value={props.sessionName} onChange={(event) => props.setSessionName(event.target.value)} placeholder="新建 Session 名称" /><button type="submit" title="新建 Session" disabled={!props.sessionAccountId || !props.sessionName.trim()}><Plus size={15} /></button></form><div className="account-tree">{props.accounts.length === 0 ? <EmptyState title="暂无账户" description="请先在管理页配置 Provider，然后在修改页创建账户。" /> : props.accounts.map((account) => { const sessions = props.sessions.filter((session) => session.accountId === account.id); return <details className="account-node" key={account.id} open><summary><span className="node-title"><Wallet size={15} />{account.name}</span><span>{account.sessionCount} 会话</span></summary><div className="account-node-meta"><span>初始资金 {formatMoney(account.initialCash)}</span><span>{account.providerName ?? "Provider 未配置"}</span></div><div className="session-list">{sessions.length === 0 ? <p className="muted">暂无 Session。</p> : sessions.map((session) => <button className={session.id === props.selectedSessionId ? "session-row active" : "session-row"} key={session.id} onClick={() => props.onSelectSession(session.id)} type="button"><span className={`status-dot ${session.status}`} /><span><strong>{session.name}</strong><small>{session.model ?? "模型未配置"} · {humanTime(session.lastRunAt)}</small></span></button>)}</div></details>; })}</div><div className="rail-actions"><button className="ghost-button" type="button" disabled title="后端尚未提供复制 Session 接口"><Code2 size={14} />复制</button><button className="ghost-button" type="button" disabled title="后端尚未提供归档 Session 接口"><History size={14} />归档</button></div></aside>;
}
function SessionHeader({ selectedAccount, selectedSession, onRunOnce, busy }: { selectedAccount: AccountView | null; selectedSession: SessionView | null; onRunOnce: () => void; busy: boolean }) {
  return <header className="session-header"><div><p className="eyebrow">LLM Linear Flow</p><h1>{selectedSession?.name ?? "暂无会话"}</h1><div className="session-tags"><span>账户：{selectedAccount?.name ?? "--"}</span><span>模型：{selectedSession?.model ?? "--"}</span><span>Provider：{selectedSession?.providerName ?? "--"}</span><span>Skill：{selectedSession?.skillId ?? "--"}</span><span>模式：实时</span><span className={selectedSession ? `status-chip ${selectedSession.status}` : "status-chip"}>{selectedSession ? statusLabel(selectedSession.status) : "--"}</span></div></div><div className="header-actions"><button className="ghost-button" type="button" disabled={!selectedSession || busy} onClick={onRunOnce}><Play size={15} />运行一次</button><button className="ghost-button" type="button" disabled title="后端尚未提供停止当前 run 的接口"><StopCircle size={15} />停止</button><button className="ghost-button" type="button" disabled title="后端尚未接入触发器接口"><Bell size={15} />触发器未接入</button><button className="ghost-button" type="button" disabled title="后端尚未提供 Session 配置修改接口"><SlidersHorizontal size={15} />修改配置</button></div></header>;
}
function LLMLinearTimeline({ timeline, hasSession }: { timeline: TimelineItem[]; hasSession: boolean }) {
  if (!hasSession) return <div className="timeline-scroll"><EmptyState title="暂无会话" description="创建账户和 Session 后，这里会显示真实消息、工具调用与工具结果。" /></div>;
  if (timeline.length === 0) return <div className="timeline-scroll"><EmptyState title="暂无消息" description="发送消息或运行 Session 后，这里会显示真实执行链。" /></div>;
  return <div className="timeline-scroll"><div className="timeline-line" />{timeline.map((item, index) => <TimelineCard item={item} key={item.id} index={index} />)}</div>;
}
function TimelineCard({ item, index }: { item: TimelineItem; index: number }) {
  return <article className={`timeline-card ${item.kind}`} style={{ animationDelay: `${Math.min(index * 45, 420)}ms` }}><div className="timeline-time"><Clock3 size={13} />{item.time}</div><div className="timeline-marker"><TimelineIcon kind={item.kind} /></div><div className="timeline-body"><header><span>{item.title}</span>{item.toolName && <code>{item.toolName}</code>}</header>{item.kind === "tool-call" && <ToolCallCard item={item} />}{item.result && <ToolResultRenderer payload={item.result} raw={item.raw} />}{item.body && <p>{item.body}</p>}{item.raw && item.kind !== "tool-call" && <RawJson data={item.raw} />}</div></article>;
}
function TimelineIcon({ kind }: { kind: TimelineItem["kind"] }) {
  if (kind === "user") return <UserRound size={14} />;
  if (kind === "event") return <Zap size={14} />;
  if (kind === "assistant") return <Bot size={14} />;
  if (kind === "tool-call") return <Wrench size={14} />;
  if (kind === "tool-result") return <CheckCircle2 size={14} />;
  return <AlertTriangle size={14} />;
}
function ToolCallCard({ item }: { item: TimelineItem }) {
  return <details className="tool-call"><summary><span>[Tool Call] {item.toolName ?? "unknown"}</span><small>{item.argsSummary}</small><span className="tool-status">{item.status ?? "--"}</span></summary><div className="tool-call-detail"><InfoGrid items={[["调用工具", item.toolName ?? "--"], ["调用状态", item.status ?? "--"], ["参数摘要", item.argsSummary ?? "--"]]} />{item.raw && <RawJson data={item.raw} />}</div></details>;
}

function ToolResultRenderer({ payload, raw }: { payload: ToolResultPayload; raw?: Record<string, unknown> }) {
  if (payload.kind === "quote") return <div className="compact-quote"><strong>{String(payload.quote.name ?? payload.quote.symbol ?? "行情结果")}</strong>{objectEntries(payload.quote).slice(0, 8).map(([key, value]) => <span key={key}>{key}: {value}</span>)}{raw && <RawJson data={raw} />}</div>;
  if (payload.kind === "history") { const values = payload.bars.map((bar) => Number(bar.close ?? bar.Close ?? bar.price)).filter(Number.isFinite); return <div className="history-result"><div className="result-title">历史行情 · {String(payload.history.symbol ?? "--")}</div><InfoGrid items={[["周期", String(payload.history.interval ?? "--")], ["复权", String(payload.history.adjust ?? "--")], ["缓存命中", String(payload.history.cache_hit ?? "--")], ["记录数", String(payload.bars.length)]]} />{values.length > 1 && <MiniLineChart values={values} />}{raw && <RawJson data={raw} />}</div>; }
  if (payload.kind === "fetch-history") return <div className="tool-result"><div className="result-title">数据拉取结果</div><InfoGrid items={objectEntries(payload.stats)} />{raw && <RawJson data={raw} />}</div>;
  return <div className="tool-result"><div className="result-title">{payload.title}</div><InfoGrid items={objectEntries(payload.data).slice(0, 8)} />{raw && <RawJson data={raw} />}</div>;
}
function ChatInputBox(props: { draft: string; setDraft: (value: string) => void; sendMessage: (mode: "run" | "event" | "write") => void; busy: boolean; disabled: boolean }) {
  return <footer className="chat-composer"><div className="composer-row"><textarea value={props.draft} disabled={props.disabled} onChange={(event) => props.setDraft(event.target.value)} placeholder={props.disabled ? "请先创建并选择 Session。" : "输入给 LLM 的问题。Shift + Enter 换行，Enter 发送。"} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void props.sendMessage("run"); } }} /><div className="send-stack"><button className="send-button" type="button" disabled={props.busy || props.disabled || !props.draft.trim()} onClick={() => props.sendMessage("run")}><Send size={17} />发送</button><button className="ghost-button" type="button" disabled={props.busy || props.disabled || !props.draft.trim()} onClick={() => props.sendMessage("event")}>作为事件运行</button><button className="ghost-button" type="button" disabled={props.busy || props.disabled || !props.draft.trim()} onClick={() => props.sendMessage("write")}>只写入</button><button className="danger-button" type="button" disabled title="后端尚未提供停止当前 run 的接口"><StopCircle size={15} />停止</button></div></div><div className="composer-foot">工具列表来自后端 `/api/tools`；工具结果来自 Session timeline。</div></footer>;
}
function AccountInspectorPanel(props: { account: AccountView | null; session: SessionView | null; events: RuntimeEvent[] }) {
  const account = props.account;
  return <aside className="account-inspector panel-frame"><header className="inspector-title"><div><p className="eyebrow">账户观察</p><h2>{account?.name ?? "未选择账户"}</h2></div><Eye size={17} /></header>{account ? <><div className="context-strip"><span>当前账户：{account.name}</span><span>当前 Session：{props.session?.id ?? "--"}</span><span>模型：{props.session?.model ?? "--"}</span><span>Skill：{props.session?.skillId ?? "--"}</span></div><div className="metrics-grid dense"><Metric label="初始资金" value={formatMoney(account.initialCash)} /><Metric label="Provider" value={account.providerName ?? "--"} /><Metric label="Session 数" value={String(account.sessionCount)} /><Metric label="运行中" value={String(account.runningSessions)} /></div><section className="inspector-section"><PanelHeader icon={<LineChart size={16} />} title="资产曲线" /><EmptyState title="暂无数据" description="后端尚未接入模拟交易账本，无法展示资产曲线。" /></section><section className="inspector-section"><PanelHeader icon={<Table2 size={16} />} title="持仓股票" /><EmptyState title="暂无数据" description="后端尚未提供持仓接口。" /></section><section className="inspector-section"><PanelHeader icon={<History size={16} />} title="交易记录" /><EmptyState title="暂无数据" description="后端尚未提供订单和成交接口。" /></section><section className="inspector-section"><PanelHeader icon={<Activity size={16} />} title="实时事件" />{props.events.length === 0 ? <p className="muted">暂无后端 WebSocket 事件。</p> : props.events.slice(0, 6).map((event, index) => <div className="event-line" key={`${event.type}-${index}`}><span>{event.type}</span><small>{event.tool_name ?? event.status ?? event.error ?? event.run_id}</small></div>)}</section></> : <EmptyState title="未选择账户" description="选择或创建账户后显示账户上下文。" />}</aside>;
}
function ViewPage(props: { tab: string; setTab: (tab: string) => void; accounts: AccountView[]; sessions: SessionView[]; providers: Provider[]; marketForm: typeof defaultMarketForm; setMarketForm: (value: typeof defaultMarketForm) => void; marketQuote: MarketQuote | null; marketHistory: MarketHistoryResponse | null; cacheRows: CacheStatusRow[]; onQueryQuote: (event?: FormEvent) => void; onQueryHistory: (event?: FormEvent) => void; onRefresh: () => void; busy: boolean }) {
  return <section className="module-page view-page"><PageHeader eyebrow={`查看 - ${props.tab}`} title="全局观察、对比分析、行情浏览、模拟时间线控制" actions={<><button className="ghost-button" type="button" disabled={props.busy} onClick={props.onRefresh}><RefreshCw size={15} />刷新</button><button className="ghost-button" type="button" disabled title="后端尚未提供自动同步控制接口"><Pause size={15} />暂停同步</button></>} /><SubTabs tabs={viewTabs} active={props.tab} onChange={props.setTab} />{props.tab === "总览" && <ViewOverview accounts={props.accounts} sessions={props.sessions} providers={props.providers} cacheRows={props.cacheRows} />}{props.tab === "账号详情" && <AccountDetailsPanel accounts={props.accounts} sessions={props.sessions} />}{props.tab === "股票信息" && <MarketDataPanel form={props.marketForm} setForm={props.setMarketForm} quote={props.marketQuote} history={props.marketHistory} cacheRows={props.cacheRows} onQueryQuote={props.onQueryQuote} onQueryHistory={props.onQueryHistory} busy={props.busy} />}{!["总览", "账号详情", "股票信息"].includes(props.tab) && <PlaceholderSection title={props.tab} description={viewTabDescription(props.tab)} />}</section>;
}
function ViewOverview({ accounts, sessions, providers, cacheRows }: { accounts: AccountView[]; sessions: SessionView[]; providers: Provider[]; cacheRows: CacheStatusRow[] }) {
  return <><div className="account-card-row">{accounts.length === 0 ? <EmptyState title="暂无账户" description="创建账户后这里会展示真实账户列表。" /> : accounts.map((account) => <AccountSummaryCard account={account} key={account.id} />)}</div><div className="view-grid"><section className="panel-frame key-metrics"><PanelHeader icon={<Gauge size={16} />} title="当前对象统计" /><Metric label="Provider" value={String(providers.length)} /><Metric label="账户" value={String(accounts.length)} /><Metric label="Session" value={String(sessions.length)} /><Metric label="运行中 Session" value={String(sessions.filter((session) => session.status === "running").length)} /></section><section className="panel-frame"><PanelHeader icon={<Database size={16} />} title="行情缓存" /><Metric label="缓存标的" value={String(cacheRows.length)} /><Metric label="缓存记录" value={String(cacheRows.reduce((sum, row) => sum + Number(row.bar_count || 0), 0))} /></section><section className="panel-frame wide"><PanelHeader icon={<LineChart size={16} />} title="资产曲线" /><EmptyState title="暂无数据" description="后端尚未接入模拟交易账本，无法展示资产曲线。" /></section><section className="panel-frame"><PanelHeader icon={<MessageSquare size={16} />} title="最近 LLM 决策" /><EmptyState title="暂无数据" description="后端尚未提供决策日志聚合接口。" /></section><section className="panel-frame"><PanelHeader icon={<History size={16} />} title="最近交易" /><EmptyState title="暂无数据" description="后端尚未提供交易历史接口。" /></section></div></>;
}
function AccountDetailsPanel({ accounts, sessions }: { accounts: AccountView[]; sessions: SessionView[] }) {
  return <div className="view-grid"><section className="panel-frame wide"><PanelHeader icon={<Wallet size={16} />} title="账户详情" />{accounts.length === 0 ? <EmptyState title="暂无账户" description="创建账户后展示账户与 Provider 绑定。" /> : <table className="data-table"><thead><tr><th>账户</th><th>Provider</th><th>初始资金</th><th>Session</th><th>运行中</th></tr></thead><tbody>{accounts.map((account) => <tr key={account.id}><td>{account.name}</td><td>{account.providerName ?? "--"}</td><td>{formatMoney(account.initialCash)}</td><td>{account.sessionCount}</td><td>{account.runningSessions}</td></tr>)}</tbody></table>}</section><section className="panel-frame wide"><PanelHeader icon={<MessageSquare size={16} />} title="Session 列表" />{sessions.length === 0 ? <EmptyState title="暂无 Session" description="创建 Session 后展示真实会话状态。" /> : <table className="data-table"><thead><tr><th>Session</th><th>账户</th><th>模型</th><th>Provider</th><th>状态</th><th>更新时间</th></tr></thead><tbody>{sessions.map((session) => <tr key={session.id}><td>{session.name}</td><td>{session.accountName ?? "--"}</td><td>{session.model ?? "--"}</td><td>{session.providerName ?? "--"}</td><td>{statusLabel(session.status)}</td><td>{humanTime(session.lastRunAt)}</td></tr>)}</tbody></table>}</section></div>;
}
function MarketDataPanel(props: { form: typeof defaultMarketForm; setForm: (value: typeof defaultMarketForm) => void; quote: MarketQuote | null; history: MarketHistoryResponse | null; cacheRows: CacheStatusRow[]; onQueryQuote: (event?: FormEvent) => void; onQueryHistory: (event?: FormEvent) => void; busy: boolean }) {
  const closeValues = props.history?.bars.map(barClose).filter((value): value is number => value != null) ?? [];
  return <div className="view-grid"><section className="panel-frame wide"><PanelHeader icon={<LineChart size={16} />} title="行情查询" /><form className="market-form" onSubmit={props.onQueryHistory}><label>股票代码<input value={props.form.symbol} onChange={(event) => props.setForm({ ...props.form, symbol: event.target.value })} placeholder="输入股票代码" /></label><label>起始日期<input type="date" value={props.form.start} onChange={(event) => props.setForm({ ...props.form, start: event.target.value })} /></label><label>结束日期<input type="date" value={props.form.end} onChange={(event) => props.setForm({ ...props.form, end: event.target.value })} /></label><label>复权<select value={props.form.adjust} onChange={(event) => props.setForm({ ...props.form, adjust: event.target.value })}><option value="">不复权</option><option value="qfq">前复权</option><option value="hfq">后复权</option></select></label><label className="checkbox-field"><input type="checkbox" checked={props.form.allowFetchMissing} onChange={(event) => props.setForm({ ...props.form, allowFetchMissing: event.target.checked })} />允许缺失拉取</label><div className="form-actions"><button className="ghost-button" type="button" disabled={props.busy || !props.form.symbol.trim()} onClick={() => props.onQueryQuote()}><Activity size={15} />查询行情</button><button className="send-button" type="submit" disabled={props.busy || !props.form.symbol.trim()}><LineChart size={15} />查询历史</button></div></form></section><section className="panel-frame"><PanelHeader icon={<Activity size={16} />} title="行情快照" />{props.quote ? <><InfoGrid items={objectEntries(props.quote).slice(0, 10)} /><RawJson data={props.quote} /></> : <EmptyState title="暂无行情" description="输入股票代码后调用 `/api/market/quote`。" />}</section><section className="panel-frame wide chart-panel"><PanelHeader icon={<LineChart size={16} />} title="历史行情" />{props.history ? <><InfoGrid items={[["股票代码", props.history.symbol], ["周期", props.history.interval], ["复权", props.history.adjust || "不复权"], ["缓存命中", String(props.history.cache_hit)], ["记录数", String(props.history.bars.length)], ["拉取统计", props.history.fetch_stats ? JSON.stringify(props.history.fetch_stats) : "--"]]} />{closeValues.length > 1 && <MiniLineChart values={closeValues} />}{props.history.bars.length === 0 ? <EmptyState title="暂无历史行情" description="本地缓存没有记录；可开启允许缺失拉取并填写起止日期。" /> : <MarketBarsTable bars={props.history.bars} />}</> : <EmptyState title="暂无历史行情" description="输入股票代码后调用 `/api/market/history`。" />}</section><section className="panel-frame wide"><PanelHeader icon={<Database size={16} />} title="本地行情缓存" /><CacheStatusTable rows={props.cacheRows} /></section></div>;
}
function MarketBarsTable({ bars }: { bars: Record<string, unknown>[] }) {
  return <div className="table-scroll"><table className="data-table"><thead><tr><th>时间</th><th>开</th><th>高</th><th>低</th><th>收</th><th>量</th><th>额</th></tr></thead><tbody>{bars.slice(0, 16).map((bar, index) => <tr key={`${barTime(bar)}-${index}`}><td>{barTime(bar)}</td><td>{formatValue(bar.open)}</td><td>{formatValue(bar.high)}</td><td>{formatValue(bar.low)}</td><td>{formatValue(bar.close)}</td><td>{formatValue(bar.volume)}</td><td>{formatValue(bar.amount)}</td></tr>)}</tbody></table></div>;
}
function EditPage(props: { tab: string; setTab: (tab: string) => void; providers: Provider[]; accounts: AccountView[]; sessions: SessionView[]; accountName: string; setAccountName: (name: string) => void; accountProviderId: string; setAccountProviderId: (id: string) => void; accountInitialCash: string; setAccountInitialCash: (value: string) => void; sessionName: string; setSessionName: (name: string) => void; sessionAccountId: string; setSessionAccountId: (id: string) => void; createAccount: (event: FormEvent) => void; createSession: (event?: FormEvent) => void; busy: boolean }) {
  return <section className="module-page edit-page"><PageHeader eyebrow={`修改 - ${props.tab}`} title="人工修改账户状态与 Session 绑定，所有变更进入审计记录" actions={<><button className="ghost-button" type="button" disabled title="后端尚未提供修改草稿接口">取消</button><button className="send-button" type="button" disabled title="后端尚未提供批量保存接口"><Save size={15} />保存</button></>} /><SubTabs tabs={editTabs} active={props.tab} onChange={props.setTab} />{props.tab === "账户信息" || props.tab === "会话绑定" ? <div className="edit-grid"><section className="panel-frame form-panel wide"><PanelHeader icon={<ShieldAlert size={16} />} title="创建账户" /><form className="form-grid" onSubmit={props.createAccount}><label>账户名<input value={props.accountName} onChange={(event) => props.setAccountName(event.target.value)} placeholder="请输入账户名称" /></label><label>Provider<select value={props.accountProviderId} onChange={(event) => props.setAccountProviderId(event.target.value)} disabled={props.providers.length === 0}><option value="">选择 Provider</option>{props.providers.map((provider) => <option key={provider.id} value={provider.id}>{provider.name}</option>)}</select></label><label>初始资金<input value={props.accountInitialCash} onChange={(event) => props.setAccountInitialCash(event.target.value)} inputMode="decimal" placeholder="留空使用后端默认值" /></label><button className="send-button" type="submit" disabled={props.busy || !props.accountProviderId || !props.accountName.trim()}><Plus size={15} />创建账户</button></form></section><section className="panel-frame form-panel wide"><PanelHeader icon={<MessageSquare size={16} />} title="创建 Session" /><form className="form-grid" onSubmit={props.createSession}><label>Session 名称<input value={props.sessionName} onChange={(event) => props.setSessionName(event.target.value)} placeholder="请输入 Session 名称" /></label><label>账户<select value={props.sessionAccountId} onChange={(event) => props.setSessionAccountId(event.target.value)} disabled={props.accounts.length === 0}><option value="">选择账户</option>{props.accounts.map((account) => <option key={account.id} value={account.id}>{account.name}</option>)}</select></label><button className="send-button" type="submit" disabled={props.busy || !props.sessionAccountId || !props.sessionName.trim()}><Plus size={15} />创建 Session</button></form></section><section className="panel-frame wide"><PanelHeader icon={<Table2 size={16} />} title="会话与模型关系概览" />{props.sessions.length === 0 ? <EmptyState title="暂无 Session" description="创建 Session 后显示绑定关系。" /> : <table className="data-table"><thead><tr><th>Session</th><th>账户</th><th>模型</th><th>Skill</th><th>状态</th></tr></thead><tbody>{props.sessions.map((session) => <tr key={session.id}><td>{session.id}</td><td>{session.accountName ?? "--"}</td><td>{session.model ?? "--"}</td><td>{session.skillId ?? "--"}</td><td>{statusLabel(session.status)}</td></tr>)}</tbody></table>}</section><section className="panel-frame audit-panel"><PanelHeader icon={<AlertTriangle size={16} />} title="审计提示" /><p>后端未接入人工修改账本能力前，本页只允许创建账户、创建 Session 和查看绑定关系。</p></section></div> : <PlaceholderSection title={props.tab} description={editTabDescription(props.tab)} />}</section>;
}

function ManagePage(props: { section: string; setSection: (section: string) => void; providerCards: ProviderCard[]; tools: ToolSchema[]; providerForm: typeof defaultProvider; setProviderForm: (value: typeof defaultProvider) => void; createProvider: (event: FormEvent) => void; busy: boolean; selectedToolName: string; setSelectedToolName: (name: string) => void; selectedTool: ToolSchema | null; toolArgs: string; setToolArgs: (value: string) => void; toolResult: Record<string, unknown> | null; runToolTest: (event: FormEvent) => void; dataFetchForm: typeof defaultDataFetchForm; setDataFetchForm: (value: typeof defaultDataFetchForm) => void; dataFetchResult: FetchHistoryResponse | null; cacheRows: CacheStatusRow[]; conflicts: DataConflict[]; fetchHistory: (event: FormEvent) => void; resolveConflict: (id: string, status: "resolved" | "ignored") => void; onRefresh: () => void }) {
  return <section className="module-page manage-page"><PageHeader eyebrow={`管理中心 - ${props.section}`} title="管理 LLM 提供商、API 配置、Skills、Tools、触发器与数据源" actions={<><button className="ghost-button" type="button" disabled title="后端尚未提供帮助文档接口"><KeyRound size={15} />使用指南</button><button className="ghost-button" type="button" disabled={props.busy} onClick={props.onRefresh}><RefreshCw size={15} />刷新</button></>} /><div className="manage-layout"><aside className="panel-frame secondary-nav">{manageSections.map((section) => <button className={props.section === section ? "secondary-item active" : "secondary-item"} key={section} type="button" onClick={() => props.setSection(section)}>{manageIcon(section)}<span>{section}</span></button>)}</aside><section className="panel-frame manage-main">{props.section === "模型与API" && <ProviderManagement providerCards={props.providerCards} providerForm={props.providerForm} setProviderForm={props.setProviderForm} createProvider={props.createProvider} busy={props.busy} />}{props.section === "Tools" && <ToolManagement tools={props.tools} selectedToolName={props.selectedToolName} setSelectedToolName={props.setSelectedToolName} selectedTool={props.selectedTool} toolArgs={props.toolArgs} setToolArgs={props.setToolArgs} toolResult={props.toolResult} runToolTest={props.runToolTest} busy={props.busy} />}{props.section === "数据管理" && <DataManagement form={props.dataFetchForm} setForm={props.setDataFetchForm} result={props.dataFetchResult} cacheRows={props.cacheRows} conflicts={props.conflicts} fetchHistory={props.fetchHistory} resolveConflict={props.resolveConflict} busy={props.busy} />}{!["模型与API", "Tools", "数据管理"].includes(props.section) && <ManagePlaceholder section={props.section} />}</section><aside className="panel-frame tool-catalog"><PanelHeader icon={<Wrench size={16} />} title="Tools（工具目录）" />{props.tools.length === 0 ? <EmptyState title="暂无工具" description="后端 `/api/tools` 未返回工具。" /> : <div className="tool-table">{props.tools.map((tool) => <button className={props.selectedToolName === tool.name ? "tool-table-row active" : "tool-table-row"} key={tool.name} type="button" onClick={() => { props.setSelectedToolName(tool.name); props.setToolArgs("{}"); }}><span>{tool.display_name || tool.name}</span><small>{tool.description}</small><strong>{tool.strict ? "Strict" : "Best effort"}</strong><b>选择</b></button>)}</div>}</aside></div>{props.section === "模型与API" && <CapabilityMatrix providerCards={props.providerCards} />}</section>;
}
function ProviderManagement(props: { providerCards: ProviderCard[]; providerForm: typeof defaultProvider; setProviderForm: (value: typeof defaultProvider) => void; createProvider: (event: FormEvent) => void; busy: boolean }) {
  return <><PanelHeader icon={<KeyRound size={16} />} title="提供商配置详情" />{props.providerCards.length === 0 ? <EmptyState title="暂无 Provider" description="填写下方表单创建真实 Provider。" /> : <div className="provider-cards">{props.providerCards.map((provider) => <article className="provider-card" key={provider.id}><header><strong>{provider.name}</strong><span className={provider.status === "已连接" ? "online" : "offline"}>{provider.status}</span></header><InfoGrid items={[["接口 URL", provider.endpoint], ["模型", provider.model], ["更新时间", provider.updatedAt], ["工具调用", provider.supportsTools ? "支持" : "未启用"], ["Strict Schema", provider.supportsStrictSchema ? "支持" : "未启用"], ["可见 Reasoning", provider.supportsReasoning ? "可能支持" : "未配置"]]} /></article>)}</div>}<form className="provider-form" onSubmit={props.createProvider}><label>Provider 类型<select value={props.providerForm.provider_type} onChange={(event) => props.setProviderForm({ ...props.providerForm, provider_type: event.target.value as ProviderType })}><option value="deepseek">DeepSeek</option><option value="openai_compatible">OpenAI-Compatible</option></select></label><label>名称<input value={props.providerForm.name} onChange={(event) => props.setProviderForm({ ...props.providerForm, name: event.target.value })} placeholder="Provider 名称" /></label><label>Base URL<input value={props.providerForm.base_url} onChange={(event) => props.setProviderForm({ ...props.providerForm, base_url: event.target.value })} placeholder="留空使用后端默认" /></label><label>模型<input value={props.providerForm.model} onChange={(event) => props.setProviderForm({ ...props.providerForm, model: event.target.value })} placeholder="模型名称" /></label><label>API Key<input type="password" value={props.providerForm.api_key} onChange={(event) => props.setProviderForm({ ...props.providerForm, api_key: event.target.value })} placeholder="API Key" /></label><button className="send-button" type="submit" disabled={props.busy || !props.providerForm.api_key.trim()}>保存 Provider</button></form></>;
}
function ToolManagement(props: { tools: ToolSchema[]; selectedToolName: string; setSelectedToolName: (name: string) => void; selectedTool: ToolSchema | null; toolArgs: string; setToolArgs: (value: string) => void; toolResult: Record<string, unknown> | null; runToolTest: (event: FormEvent) => void; busy: boolean }) {
  return <><PanelHeader icon={<Wrench size={16} />} title="工具测试" /><form className="tool-test-form" onSubmit={props.runToolTest}><label>工具<select value={props.selectedToolName} onChange={(event) => props.setSelectedToolName(event.target.value)} disabled={props.tools.length === 0}><option value="">选择工具</option>{props.tools.map((tool) => <option key={tool.name} value={tool.name}>{tool.display_name || tool.name}</option>)}</select></label><label className="wide-field">参数 JSON<textarea value={props.toolArgs} onChange={(event) => props.setToolArgs(event.target.value)} spellCheck={false} /></label><button className="send-button" type="submit" disabled={props.busy || !props.selectedToolName}>运行工具测试</button></form>{props.selectedTool ? <div className="json-test-block"><PanelHeader icon={<Code2 size={15} />} title="工具 Schema" /><RawJson data={props.selectedTool.parameters} /></div> : <EmptyState title="暂无工具" description="后端 `/api/tools` 未返回工具，或尚未选择工具。" />}{props.toolResult && <div className="json-test-block"><PanelHeader icon={<CheckCircle2 size={15} />} title="调用结果" /><RawJson data={props.toolResult} /></div>}</>;
}
function DataManagement(props: { form: typeof defaultDataFetchForm; setForm: (value: typeof defaultDataFetchForm) => void; result: FetchHistoryResponse | null; cacheRows: CacheStatusRow[]; conflicts: DataConflict[]; fetchHistory: (event: FormEvent) => void; resolveConflict: (id: string, status: "resolved" | "ignored") => void; busy: boolean }) {
  return <div className="data-management"><PanelHeader icon={<Database size={16} />} title="历史数据拉取" /><form className="market-form" onSubmit={props.fetchHistory}><label>股票代码<input value={props.form.symbol} onChange={(event) => props.setForm({ ...props.form, symbol: event.target.value })} placeholder="输入股票代码" /></label><label>起始日期<input type="date" value={props.form.start} onChange={(event) => props.setForm({ ...props.form, start: event.target.value })} /></label><label>结束日期<input type="date" value={props.form.end} onChange={(event) => props.setForm({ ...props.form, end: event.target.value })} /></label><label>复权<select value={props.form.adjust} onChange={(event) => props.setForm({ ...props.form, adjust: event.target.value })}><option value="">不复权</option><option value="qfq">前复权</option><option value="hfq">后复权</option></select></label><button className="send-button" type="submit" disabled={props.busy || !props.form.symbol.trim() || !props.form.start || !props.form.end}>拉取并写入缓存</button></form>{props.result && <section className="result-section"><InfoGrid items={[["股票代码", props.result.symbol], ["拉取", String(props.result.fetched)], ["写入", String(props.result.inserted)], ["跳过", String(props.result.skipped)], ["冲突", String(props.result.conflicted)], ["复权", props.result.adjust || "不复权"]]} /></section>}<section className="result-section"><PanelHeader icon={<Database size={15} />} title="缓存状态" /><CacheStatusTable rows={props.cacheRows} /></section><section className="result-section"><PanelHeader icon={<AlertTriangle size={15} />} title="数据冲突" /><ConflictsTable conflicts={props.conflicts} resolveConflict={props.resolveConflict} busy={props.busy} /></section></div>;
}
function CacheStatusTable({ rows }: { rows: CacheStatusRow[] }) {
  if (rows.length === 0) return <EmptyState title="暂无缓存" description="调用历史行情拉取后，这里会显示真实缓存覆盖范围。" />;
  return <div className="table-scroll"><table className="data-table"><thead><tr><th>代码</th><th>名称</th><th>周期</th><th>复权</th><th>起始</th><th>结束</th><th>记录</th><th>更新时间</th></tr></thead><tbody>{rows.map((row) => <tr key={`${row.symbol}-${row.interval}-${row.adjust}`}><td>{row.symbol}</td><td>{row.name ?? "--"}</td><td>{row.interval}</td><td>{row.adjust || "不复权"}</td><td>{row.start_datetime}</td><td>{row.end_datetime}</td><td>{row.bar_count}</td><td>{humanTime(row.updated_at)}</td></tr>)}</tbody></table></div>;
}
function ConflictsTable({ conflicts, resolveConflict, busy }: { conflicts: DataConflict[]; resolveConflict: (id: string, status: "resolved" | "ignored") => void; busy: boolean }) {
  if (conflicts.length === 0) return <EmptyState title="暂无冲突" description="数据写入出现冲突时，这里会显示待处理记录。" />;
  return <div className="table-scroll"><table className="data-table"><thead><tr><th>代码</th><th>时间</th><th>周期</th><th>复权</th><th>来源</th><th>差异</th><th>状态</th><th>操作</th></tr></thead><tbody>{conflicts.map((conflict) => <tr key={conflict.id}><td>{conflict.symbol}</td><td>{conflict.datetime}</td><td>{conflict.interval}</td><td>{conflict.adjust || "不复权"}</td><td>{conflict.source}</td><td>{conflictSummary(conflict)}</td><td>{conflict.status}</td><td><div className="table-actions"><button className="link-button" type="button" disabled={busy} onClick={() => resolveConflict(conflict.id, "resolved")}>标记解决</button><button className="link-button" type="button" disabled={busy} onClick={() => resolveConflict(conflict.id, "ignored")}>忽略</button></div></td></tr>)}</tbody></table></div>;
}
function CapabilityMatrix({ providerCards }: { providerCards: ProviderCard[] }) {
  return <section className="panel-frame capability-matrix"><PanelHeader icon={<Database size={16} />} title="模型能力矩阵" />{providerCards.length === 0 ? <EmptyState title="暂无数据" description="创建 Provider 后展示真实能力配置。" /> : <table className="data-table"><thead><tr><th>提供商</th><th>模型</th><th>工具调用</th><th>并行工具</th><th>Strict Schema</th><th>可见 Reasoning</th></tr></thead><tbody>{providerCards.map((provider) => <tr key={provider.id}><td>{provider.name}</td><td>{provider.model}</td><td>{provider.supportsTools ? "支持" : "未启用"}</td><td>按后端配置</td><td>{provider.supportsStrictSchema ? "支持" : "未启用"}</td><td>{provider.supportsReasoning ? "可能支持" : "未配置"}</td></tr>)}</tbody></table>}</section>;
}
function ManagePlaceholder({ section }: { section: string }) {
  return <PlaceholderSection title={section} description={{ Skills: "后端尚未提供 Skills 管理接口。", 触发器: "后端尚未接入触发器 CRUD 和调度控制。", 系统设置: "后端尚未提供系统设置读写接口。" }[section] ?? "该管理项后端尚未接入。"} />;
}
function PlaceholderSection({ title, description }: { title: string; description: string }) {
  return <section className="panel-frame placeholder-panel"><PanelHeader icon={<AlertTriangle size={16} />} title={title} /><EmptyState title="功能占位" description={description} /></section>;
}
function PageHeader({ eyebrow, title, actions }: { eyebrow: string; title: string; actions?: ReactNode }) {
  return <header className="page-header"><div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1></div><div className="header-actions">{actions}</div></header>;
}
function SubTabs({ tabs, active, onChange }: { tabs: string[]; active: string; onChange: (tab: string) => void }) {
  return <nav className="sub-tabs">{tabs.map((tab) => <button className={active === tab ? "active" : ""} key={tab} onClick={() => onChange(tab)} type="button">{tab}</button>)}</nav>;
}
function PanelHeader({ icon, title }: { icon: ReactNode; title: string }) {
  return <header className="panel-title">{icon}<h3>{title}</h3></header>;
}
function InfoGrid({ items }: { items: Array<[string, string]> }) {
  return <div className="info-grid">{items.length === 0 ? <div><span>数据</span><strong>--</strong></div> : items.map(([label, value]) => <div key={`${label}-${value}`}><span>{label}</span><strong>{value}</strong></div>)}</div>;
}
function Metric({ label, value, tone }: { label: string; value: string; tone?: "rise" | "fall" | "flat" }) {
  return <div className="metric"><span>{label}</span><strong className={tone}>{value}</strong></div>;
}
function AccountSummaryCard({ account }: { account: AccountView }) {
  return <article className="account-summary-card"><header><span>{account.name}</span></header><small>{account.providerName ?? "Provider 未配置"}</small><strong>{formatMoney(account.initialCash)}</strong><div><span>Session</span><b>{account.sessionCount}</b></div><div><span>创建时间</span><b>{humanTime(account.createdAt)}</b></div></article>;
}
function MiniLineChart({ values }: { values: number[] }) {
  const points = linePoints(values, 100, 52);
  return <svg className="mini-chart" viewBox="0 0 100 52" role="img" aria-label="数据曲线"><polyline points={points} fill="none" stroke="#4c8bff" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" /></svg>;
}
function linePoints(values: number[], width: number, height: number, offsetX = 0, offsetY = 0): string {
  if (values.length === 0) return "";
  const min = Math.min(...values); const max = Math.max(...values); const span = max - min || 1;
  return values.map((value, index) => { const x = offsetX + (index / Math.max(values.length - 1, 1)) * width; const y = offsetY + height - ((value - min) / span) * height; return `${x.toFixed(2)},${y.toFixed(2)}`; }).join(" ");
}
function RawJson({ data }: { data: Record<string, unknown> }) {
  return <details className="raw-json"><summary>查看原始 JSON</summary><pre>{JSON.stringify(data, null, 2)}</pre></details>;
}
function EmptyState({ title, description }: { title: string; description: string }) {
  return <div className="empty-state"><strong>{title}</strong><span>{description}</span></div>;
}
function viewTabDescription(tab: string): string {
  return { 交易历史: "后端尚未提供交易历史接口。", 资产曲线: "后端尚未接入模拟交易账本和资产曲线接口。", 决策日志: "后端尚未提供决策日志聚合接口。", 时间线控制: "后端尚未提供模拟时间线控制接口。" }[tab] ?? "查看子页面";
}
function editTabDescription(tab: string): string {
  return { 余额修改: "后端尚未接入余额修改与审计接口。", 持仓修改: "后端尚未提供持仓修改接口。", 订单修正: "后端尚未提供订单修正接口。" }[tab] ?? "后端尚未提供该修改接口。";
}
function manageIcon(section: string) {
  if (section === "模型与API") return <KeyRound size={15} />;
  if (section === "Skills") return <Bot size={15} />;
  if (section === "Tools") return <Wrench size={15} />;
  if (section === "触发器") return <Bell size={15} />;
  if (section === "数据管理") return <Database size={15} />;
  return <Settings size={15} />;
}
