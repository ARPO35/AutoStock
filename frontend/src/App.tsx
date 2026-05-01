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
  ListFilter,
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
import { Account, Message, Provider, ProviderType, RuntimeEvent, Session, SessionTimelineItem, ToolSchema, api } from "./api";
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
function summarizeArgs(value: string | null | undefined): string {
  const parsed = parseJsonObject(value);
  const entries = Object.entries(parsed).slice(0, 3);
  if (entries.length === 0) return "无参数";
  return entries.map(([key, item]) => `${key}: ${String(item)}`).join(" / ");
}
function objectEntries(data: Record<string, unknown>): Array<[string, string]> {
  return Object.entries(data).map(([key, value]) => [key, value == null ? "--" : typeof value === "object" ? JSON.stringify(value) : String(value)]);
}
function providerTypeLabel(type: ProviderType | string | null | undefined): "OpenAI-Compatible" | "DeepSeek" {
  return type === "deepseek" ? "DeepSeek" : "OpenAI-Compatible";
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
  const [sessionName, setSessionName] = useState("");
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [viewTab, setViewTab] = useState(viewTabs[0]);
  const [editTab, setEditTab] = useState(editTabs[0]);
  const [manageSection, setManageSection] = useState(manageSections[0]);
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

  useEffect(() => { void loadAll(); }, []);
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
    if (!providers[0]) { setError("需要先在管理页创建 Provider，才能创建账户。"); return; }
    if (!accountName.trim()) { setError("请填写账户名称。"); return; }
    setBusy(true); setError(null);
    try {
      const created = await api.createAccount({ name: accountName.trim(), provider_id: providers[0].id, initial_cash: 1_000_000 });
      setAccounts((current) => [created, ...current]);
      setAccountName("");
    } catch (err) { setError(err instanceof Error ? err.message : "创建账户失败。"); } finally { setBusy(false); }
  }
  async function createSession(event?: FormEvent) {
    event?.preventDefault();
    if (!accounts[0]) { setError("需要先创建账户，才能创建 Session。"); return; }
    if (!sessionName.trim()) { setError("请填写 Session 名称。"); return; }
    setBusy(true); setError(null);
    try {
      const targetAccount = selectedAccount ? accounts.find((account) => account.id === selectedAccount.id) ?? accounts[0] : accounts[0];
      const created = await api.createSession({ name: sessionName.trim(), llm_account_id: targetAccount.id });
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
  function stopCurrentRun() { setError("后端尚未提供停止当前 run 的接口。"); }

  const shellStyle = { "--inspector-width": `${inspectorWidth}px` } as CSSProperties;
  return (
    <main className="app-shell" style={shellStyle}>
      <TopNavigation route={route} onNavigate={navigate} />
      {error && <div className="global-error"><AlertTriangle size={16} />{error}</div>}
      {route === "trade" && <TradePage accounts={accountViews} sessions={sessionViews} selectedAccount={selectedAccount} selectedSession={selectedSession} selectedSessionId={selectedSessionId} onSelectSession={setSelectedSessionId} onCreateSession={createSession} sessionName={sessionName} setSessionName={setSessionName} timeline={timeline} events={events} draft={draft} setDraft={setDraft} sendMessage={sendMessage} runSelectedOnce={runSelectedOnce} stopCurrentRun={stopCurrentRun} busy={busy} leftCollapsed={leftCollapsed} setLeftCollapsed={setLeftCollapsed} onStartResize={startResize} />}
      {route === "view" && <ViewPage tab={viewTab} setTab={setViewTab} accounts={accountViews} sessions={sessionViews} providers={providers} />}
      {route === "edit" && <EditPage tab={editTab} setTab={setEditTab} accounts={accountViews} sessions={sessionViews} accountName={accountName} setAccountName={setAccountName} createAccount={createAccount} busy={busy} hasProviders={providers.length > 0} />}
      {route === "manage" && <ManagePage section={manageSection} setSection={setManageSection} providerCards={providerCards} tools={tools} providerForm={providerForm} setProviderForm={setProviderForm} createProvider={createProvider} busy={busy} />}
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
    title: role === "assistant" ? (item.message_type === "tool_call_request" ? "工具调用请求" : "助手") : item.message_type === "event" ? "事件" : role === "tool" ? "工具消息" : "用户",
    body: item.content || (item.message_type === "tool_call_request" ? "模型请求调用工具。" : ""),
    raw: { role: item.role, message_type: item.message_type }
  };
}
function classifyToolResult(toolName: string | null | undefined, envelope: Record<string, unknown>): ToolResultPayload {
  const result = envelope.result && typeof envelope.result === "object" && !Array.isArray(envelope.result) ? envelope.result as Record<string, unknown> : envelope;
  if (toolName === "system_echo" && "echo" in result) return { kind: "echo", echo: result.echo };
  if (toolName === "market_quote") return { kind: "quote", quote: result };
  if (toolName === "market_history") return { kind: "history", history: result, bars: Array.isArray(result.bars) ? result.bars as Record<string, unknown>[] : [] };
  if (toolName === "data_fetch_history") return { kind: "fetch-history", stats: result };
  return { kind: "json", title: toolName ? `${toolName} 结果` : "工具结果", data: envelope };
}

function TopNavigation({ route, onNavigate }: { route: RouteKey; onNavigate: (route: RouteKey) => void }) {
  return (
    <header className="top-navigation">
      <button className="brand-lockup" type="button" onClick={() => onNavigate("trade")}>
        <span className="brand-mark">A</span>
        <span><strong>A股 LLM 交易系统</strong><small>模拟盘 · 可见推理 · 工具追踪</small></span>
      </button>
      <nav className="primary-tabs" aria-label="一级导航">
        {navItems.map((item) => <button className={route === item.key ? "primary-tab active" : "primary-tab"} key={item.key} onClick={() => onNavigate(item.key)} type="button"><span>{item.label}</span><small>{item.sub}</small></button>)}
      </nav>
      <div className="top-meta"><span>真实数据</span><span className="avatar-dot"><UserRound size={14} /></span></div>
    </header>
  );
}
function TradePage(props: {
  accounts: AccountView[]; sessions: SessionView[]; selectedAccount: AccountView | null; selectedSession: SessionView | null; selectedSessionId: string;
  onSelectSession: (id: string) => void; onCreateSession: (event?: FormEvent) => void; sessionName: string; setSessionName: (value: string) => void;
  timeline: TimelineItem[]; events: RuntimeEvent[]; draft: string; setDraft: (value: string) => void; sendMessage: (mode: "run" | "event" | "write") => void; runSelectedOnce: () => void; stopCurrentRun: () => void; busy: boolean;
  leftCollapsed: boolean; setLeftCollapsed: (value: boolean) => void; onStartResize: (event: MouseEvent<HTMLDivElement>) => void;
}) {
  return <section className={props.leftCollapsed ? "trade-workspace collapsed" : "trade-workspace"}><AccountSessionSidebar {...props} /><section className="chat-workspace panel-frame"><SessionHeader selectedAccount={props.selectedAccount} selectedSession={props.selectedSession} onRunOnce={props.runSelectedOnce} onStop={props.stopCurrentRun} busy={props.busy} /><LLMLinearTimeline timeline={props.timeline} hasSession={Boolean(props.selectedSession)} /><ChatInputBox draft={props.draft} setDraft={props.setDraft} sendMessage={props.sendMessage} stopCurrentRun={props.stopCurrentRun} busy={props.busy} disabled={!props.selectedSession} /></section><div className="resize-handle" onMouseDown={props.onStartResize} aria-label="调整账户观察栏宽度" /><AccountInspectorPanel account={props.selectedAccount} session={props.selectedSession} events={props.events} /></section>;
}
function AccountSessionSidebar(props: { accounts: AccountView[]; sessions: SessionView[]; selectedSessionId: string; onSelectSession: (id: string) => void; onCreateSession: (event?: FormEvent) => void; sessionName: string; setSessionName: (value: string) => void; leftCollapsed: boolean; setLeftCollapsed: (value: boolean) => void }) {
  if (props.leftCollapsed) return <aside className="account-rail collapsed-rail"><button className="rail-toggle" type="button" onClick={() => props.setLeftCollapsed(false)} title="展开账户栏"><ChevronDown size={16} /></button>{props.accounts.map((account) => <button className="rail-account" key={account.id} type="button" title={account.name}>{account.name.slice(0, 1)}</button>)}</aside>;
  return <aside className="account-rail panel-frame"><div className="rail-head"><div><p className="eyebrow">账户与会话</p><h2>Account Tree</h2></div><button className="ghost-button square" type="button" onClick={() => props.setLeftCollapsed(true)} title="折叠账户栏"><ChevronDown size={16} /></button></div><label className="search-field"><Search size={15} /><input placeholder="搜索账户 / 会话" /></label><form className="create-session" onSubmit={props.onCreateSession}><input value={props.sessionName} onChange={(event) => props.setSessionName(event.target.value)} placeholder="新建 Session 名称" /><button type="submit" title="新建 Session"><Plus size={15} /></button></form><div className="account-tree">{props.accounts.length === 0 ? <EmptyState title="暂无账户" description="请先在管理页配置 Provider，然后在修改页创建账户。" /> : props.accounts.map((account) => { const sessions = props.sessions.filter((session) => session.accountId === account.id); return <details className="account-node" key={account.id} open><summary><span className="node-title"><Wallet size={15} />{account.name}</span><span>{account.sessionCount} 会话</span></summary><div className="account-node-meta"><span>初始资金 {formatMoney(account.initialCash)}</span><span>{account.providerName ?? "Provider 未配置"}</span></div><div className="session-list">{sessions.length === 0 ? <p className="muted">暂无 Session。</p> : sessions.map((session) => <button className={session.id === props.selectedSessionId ? "session-row active" : "session-row"} key={session.id} onClick={() => props.onSelectSession(session.id)} type="button"><span className={`status-dot ${session.status}`} /><span><strong>{session.name}</strong><small>{session.model ?? "模型未配置"} · {humanTime(session.lastRunAt)}</small></span></button>)}</div></details>; })}</div><div className="rail-actions"><button className="ghost-button" type="button"><Code2 size={14} />复制</button><button className="ghost-button" type="button"><History size={14} />归档</button></div></aside>;
}
function SessionHeader({ selectedAccount, selectedSession, onRunOnce, onStop, busy }: { selectedAccount: AccountView | null; selectedSession: SessionView | null; onRunOnce: () => void; onStop: () => void; busy: boolean }) {
  return <header className="session-header"><div><p className="eyebrow">LLM Linear Flow</p><h1>{selectedSession?.name ?? "暂无会话"}</h1><div className="session-tags"><span>账户：{selectedAccount?.name ?? "--"}</span><span>模型：{selectedSession?.model ?? "--"}</span><span>Provider：{selectedSession?.providerName ?? "--"}</span><span>Skill：{selectedSession?.skillId ?? "--"}</span><span>模式：实时</span><span className={selectedSession ? `status-chip ${selectedSession.status}` : "status-chip"}>{selectedSession ? statusLabel(selectedSession.status) : "--"}</span></div></div><div className="header-actions"><button className="ghost-button" type="button" disabled={!selectedSession || busy} onClick={onRunOnce}><Play size={15} />运行一次</button><button className="ghost-button" type="button" disabled={!selectedSession} onClick={onStop}><StopCircle size={15} />停止</button><button className="ghost-button" type="button"><Bell size={15} />触发器未接入</button><button className="ghost-button" type="button"><SlidersHorizontal size={15} />修改配置</button></div></header>;
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
  if (payload.kind === "echo") return <div className="tool-result"><div className="result-title">Echo</div><p>{String(payload.echo ?? "")}</p>{raw && <RawJson data={raw} />}</div>;
  if (payload.kind === "quote") return <div className="compact-quote"><strong>{String(payload.quote.name ?? payload.quote.symbol ?? "行情结果")}</strong>{objectEntries(payload.quote).slice(0, 8).map(([key, value]) => <span key={key}>{key}: {value}</span>)}{raw && <RawJson data={raw} />}</div>;
  if (payload.kind === "history") { const values = payload.bars.map((bar) => Number(bar.close ?? bar.Close ?? bar.price)).filter(Number.isFinite); return <div className="history-result"><div className="result-title">历史行情 · {String(payload.history.symbol ?? "--")}</div><InfoGrid items={[["周期", String(payload.history.interval ?? "--")], ["复权", String(payload.history.adjust ?? "--")], ["缓存命中", String(payload.history.cache_hit ?? "--")], ["记录数", String(payload.bars.length)]]} />{values.length > 1 && <MiniLineChart values={values} />}{raw && <RawJson data={raw} />}</div>; }
  if (payload.kind === "fetch-history") return <div className="tool-result"><div className="result-title">数据拉取结果</div><InfoGrid items={objectEntries(payload.stats)} />{raw && <RawJson data={raw} />}</div>;
  return <div className="tool-result"><div className="result-title">{payload.title}</div><InfoGrid items={objectEntries(payload.data).slice(0, 8)} />{raw && <RawJson data={raw} />}</div>;
}
function ChatInputBox(props: { draft: string; setDraft: (value: string) => void; sendMessage: (mode: "run" | "event" | "write") => void; stopCurrentRun: () => void; busy: boolean; disabled: boolean }) {
  return <footer className="chat-composer"><div className="quick-events">{["开盘前观察", "盘中检查", "尾盘决策", "收盘复盘"].map((event) => <button key={event} type="button" disabled={props.disabled} onClick={() => props.setDraft(event)}>{event}</button>)}</div><div className="composer-row"><textarea value={props.draft} disabled={props.disabled} onChange={(event) => props.setDraft(event.target.value)} placeholder={props.disabled ? "请先创建并选择 Session。" : "输入给 LLM 的问题。Shift + Enter 换行，Enter 发送。"} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void props.sendMessage("run"); } }} /><div className="send-stack"><button className="send-button" type="button" disabled={props.busy || props.disabled || !props.draft.trim()} onClick={() => props.sendMessage("run")}><Send size={17} />发送</button><button className="ghost-button" type="button" disabled={props.busy || props.disabled || !props.draft.trim()} onClick={() => props.sendMessage("event")}>作为事件运行</button><button className="ghost-button" type="button" disabled={props.busy || props.disabled || !props.draft.trim()} onClick={() => props.sendMessage("write")}>只写入</button><button className="danger-button" type="button" disabled={props.disabled} onClick={props.stopCurrentRun}><StopCircle size={15} />停止</button></div></div><div className="composer-foot">工具列表来自后端 `/api/tools`；工具结果来自 Session timeline。</div></footer>;
}
function AccountInspectorPanel(props: { account: AccountView | null; session: SessionView | null; events: RuntimeEvent[] }) {
  const account = props.account;
  return <aside className="account-inspector panel-frame"><header className="inspector-title"><div><p className="eyebrow">账户观察</p><h2>{account?.name ?? "未选择账户"}</h2></div><Eye size={17} /></header>{account ? <><div className="context-strip"><span>当前账户：{account.name}</span><span>当前 Session：{props.session?.id ?? "--"}</span><span>模型：{props.session?.model ?? "--"}</span><span>Skill：{props.session?.skillId ?? "--"}</span></div><div className="metrics-grid dense"><Metric label="初始资金" value={formatMoney(account.initialCash)} /><Metric label="Provider" value={account.providerName ?? "--"} /><Metric label="Session 数" value={String(account.sessionCount)} /><Metric label="运行中" value={String(account.runningSessions)} /></div><section className="inspector-section"><PanelHeader icon={<LineChart size={16} />} title="资产曲线" /><EmptyState title="暂无数据" description="后端尚未接入模拟交易账本，无法展示资产曲线。" /></section><section className="inspector-section"><PanelHeader icon={<Table2 size={16} />} title="持仓股票" /><EmptyState title="暂无数据" description="后端尚未提供持仓接口。" /></section><section className="inspector-section"><PanelHeader icon={<History size={16} />} title="交易记录" /><EmptyState title="暂无数据" description="后端尚未提供订单和成交接口。" /></section><section className="inspector-section"><PanelHeader icon={<Activity size={16} />} title="实时事件" />{props.events.length === 0 ? <p className="muted">暂无后端 WebSocket 事件。</p> : props.events.slice(0, 6).map((event, index) => <div className="event-line" key={`${event.type}-${index}`}><span>{event.type}</span><small>{event.tool_name ?? event.status ?? event.error ?? event.run_id}</small></div>)}</section></> : <EmptyState title="未选择账户" description="选择或创建账户后显示账户上下文。" />}</aside>;
}
function ViewPage(props: { tab: string; setTab: (tab: string) => void; accounts: AccountView[]; sessions: SessionView[]; providers: Provider[] }) {
  return <section className="module-page view-page"><PageHeader eyebrow="查看 - 总览" title="全局观察、对比分析、行情浏览、模拟时间线控制" actions={<><button className="ghost-button"><RefreshCw size={15} />刷新</button><button className="ghost-button"><Pause size={15} />暂停同步</button></>} /><SubTabs tabs={viewTabs} active={props.tab} onChange={props.setTab} /><FilterBar /><div className="account-card-row">{props.accounts.length === 0 ? <EmptyState title="暂无账户" description="创建账户后这里会展示真实账户列表。" /> : props.accounts.map((account) => <AccountSummaryCard account={account} key={account.id} />)}</div><div className="view-grid"><section className="panel-frame chart-panel wide"><PanelHeader icon={<LineChart size={16} />} title="资产曲线" /><EmptyState title="暂无数据" description="后端尚未接入资产曲线接口。" /></section><section className="panel-frame key-metrics"><PanelHeader icon={<Gauge size={16} />} title="当前对象统计" /><Metric label="Provider" value={String(props.providers.length)} /><Metric label="账户" value={String(props.accounts.length)} /><Metric label="Session" value={String(props.sessions.length)} /><Metric label="运行中 Session" value={String(props.sessions.filter((session) => session.status === "running").length)} /></section><section className="panel-frame"><PanelHeader icon={<MessageSquare size={16} />} title="最近 LLM 决策" /><EmptyState title="暂无数据" description="后端尚未提供决策日志聚合接口。" /></section><section className="panel-frame"><PanelHeader icon={<History size={16} />} title="最近交易" /><EmptyState title="暂无数据" description="后端尚未提供交易历史接口。" /></section></div><section className="subpage-strip">{viewTabs.slice(1).map((tab, index) => <button className="subpage-card" key={tab} type="button" onClick={() => props.setTab(tab)}><span>{index + 1}</span><strong>{tab}</strong><small>{viewTabDescription(tab)}</small></button>)}</section></section>;
}
function EditPage(props: { tab: string; setTab: (tab: string) => void; accounts: AccountView[]; sessions: SessionView[]; accountName: string; setAccountName: (name: string) => void; createAccount: (event: FormEvent) => void; busy: boolean; hasProviders: boolean }) {
  return <section className="module-page edit-page"><PageHeader eyebrow="修改 - 账户信息" title="人工修改账户状态与 Session 绑定，所有变更进入审计记录" actions={<><button className="ghost-button">取消</button><button className="send-button"><Save size={15} />保存</button></>} /><SubTabs tabs={editTabs} active={props.tab} onChange={props.setTab} /><div className="edit-grid"><section className="panel-frame form-panel wide"><PanelHeader icon={<ShieldAlert size={16} />} title="创建账户" /><form className="form-grid" onSubmit={props.createAccount}><label>账户名<input value={props.accountName} onChange={(event) => props.setAccountName(event.target.value)} placeholder="请输入账户名称" /></label><label>初始资金<input value="1000000" readOnly /></label><label>Provider<input value={props.hasProviders ? "使用当前第一个 Provider" : "请先配置 Provider"} readOnly /></label><button className="send-button" type="submit" disabled={props.busy || !props.hasProviders}><Plus size={15} />创建账户</button></form></section><section className="panel-frame"><PanelHeader icon={<Wallet size={16} />} title="余额修改" /><EmptyState title="暂无接口" description="后端尚未接入余额修改与审计接口。" /></section><section className="panel-frame wide"><PanelHeader icon={<Table2 size={16} />} title="会话与模型关系概览" />{props.sessions.length === 0 ? <EmptyState title="暂无 Session" description="创建 Session 后显示绑定关系。" /> : <table className="data-table"><thead><tr><th>Session</th><th>账户</th><th>模型</th><th>Skill</th><th>状态</th></tr></thead><tbody>{props.sessions.map((session) => <tr key={session.id}><td>{session.id}</td><td>{session.accountName ?? "--"}</td><td>{session.model ?? "--"}</td><td>{session.skillId ?? "--"}</td><td>{statusLabel(session.status)}</td></tr>)}</tbody></table>}</section><section className="panel-frame audit-panel"><PanelHeader icon={<AlertTriangle size={16} />} title="审计提示" /><p>后端未接入人工修改账本能力前，本页只允许创建账户和查看绑定关系。</p></section></div><section className="panel-frame audit-log-table"><PanelHeader icon={<History size={16} />} title="审计记录" /><EmptyState title="暂无数据" description="后端尚未提供审计记录接口。" /></section></section>;
}

function ManagePage(props: { section: string; setSection: (section: string) => void; providerCards: ProviderCard[]; tools: ToolSchema[]; providerForm: typeof defaultProvider; setProviderForm: (value: typeof defaultProvider) => void; createProvider: (event: FormEvent) => void; busy: boolean }) {
  return <section className="module-page manage-page"><PageHeader eyebrow="管理中心 - 模型与 API" title="管理 LLM 提供商、API 配置、Skills、Tools、触发器与数据源" actions={<><button className="ghost-button"><KeyRound size={15} />使用指南</button><button className="send-button"><Plus size={15} />新增提供商</button></>} /><div className="manage-layout"><aside className="panel-frame secondary-nav">{manageSections.map((section) => <button className={props.section === section ? "secondary-item active" : "secondary-item"} key={section} type="button" onClick={() => props.setSection(section)}>{manageIcon(section)}<span>{section}</span></button>)}</aside><section className="panel-frame manage-main"><PanelHeader icon={<KeyRound size={16} />} title="提供商配置详情" />{props.providerCards.length === 0 ? <EmptyState title="暂无 Provider" description="填写下方表单创建真实 Provider。" /> : <div className="provider-cards">{props.providerCards.map((provider) => <article className="provider-card" key={provider.id}><header><strong>{provider.name}</strong><span className={provider.status === "已连接" ? "online" : "offline"}>{provider.status}</span></header><InfoGrid items={[["接口 URL", provider.endpoint], ["模型", provider.model], ["更新时间", provider.updatedAt], ["工具调用", provider.supportsTools ? "支持" : "未启用"], ["Strict Schema", provider.supportsStrictSchema ? "支持" : "未启用"], ["可见 Reasoning", provider.supportsReasoning ? "可能支持" : "未配置"]]} /></article>)}</div>}<form className="provider-form" onSubmit={props.createProvider}><label>Provider 类型<select value={props.providerForm.provider_type} onChange={(event) => props.setProviderForm({ ...props.providerForm, provider_type: event.target.value as ProviderType })}><option value="deepseek">DeepSeek</option><option value="openai_compatible">OpenAI-Compatible</option></select></label><label>名称<input value={props.providerForm.name} onChange={(event) => props.setProviderForm({ ...props.providerForm, name: event.target.value })} placeholder="Provider 名称" /></label><label>Base URL<input value={props.providerForm.base_url} onChange={(event) => props.setProviderForm({ ...props.providerForm, base_url: event.target.value })} placeholder="留空使用后端默认" /></label><label>模型<input value={props.providerForm.model} onChange={(event) => props.setProviderForm({ ...props.providerForm, model: event.target.value })} placeholder="模型名称" /></label><label>API Key<input type="password" value={props.providerForm.api_key} onChange={(event) => props.setProviderForm({ ...props.providerForm, api_key: event.target.value })} placeholder="API Key" /></label><button className="send-button" type="submit" disabled={props.busy || !props.providerForm.api_key.trim()}>保存 Provider</button></form></section><aside className="panel-frame tool-catalog"><PanelHeader icon={<Wrench size={16} />} title="Tools（工具目录）" />{props.tools.length === 0 ? <EmptyState title="暂无工具" description="后端 `/api/tools` 未返回工具。" /> : <div className="tool-table">{props.tools.map((tool) => <div className="tool-table-row" key={tool.name}><span>{tool.display_name || tool.name}</span><small>{tool.description}</small><strong>{tool.strict ? "Strict" : "Best effort"}</strong><button className="link-button">测试</button></div>)}</div>}<div className="json-test-block"><PanelHeader icon={<Code2 size={15} />} title="工具测试" /><EmptyState title="等待输入" description="选择工具后使用真实 schema 组织参数。" /></div></aside></div><section className="panel-frame capability-matrix"><PanelHeader icon={<Database size={16} />} title="模型能力矩阵" />{props.providerCards.length === 0 ? <EmptyState title="暂无数据" description="创建 Provider 后展示真实能力配置。" /> : <table className="data-table"><thead><tr><th>提供商</th><th>模型</th><th>工具调用</th><th>并行工具</th><th>Strict Schema</th><th>可见 Reasoning</th></tr></thead><tbody>{props.providerCards.map((provider) => <tr key={provider.id}><td>{provider.name}</td><td>{provider.model}</td><td>{provider.supportsTools ? "支持" : "未启用"}</td><td>按后端配置</td><td>{provider.supportsStrictSchema ? "支持" : "未启用"}</td><td>{provider.supportsReasoning ? "可能支持" : "未配置"}</td></tr>)}</tbody></table>}</section></section>;
}
function FilterBar() {
  return <div className="filter-bar"><button><ListFilter size={14} />全部账户</button><button>全部策略</button><button>全部市场：A股</button><label>起始日期<input type="date" /></label><label>结束日期<input type="date" /></label><button className="send-button">筛选</button><button className="ghost-button">重置</button><span className="auto-refresh"><span />自动刷新</span></div>;
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
  return { 账号详情: "账户、Session 与 Provider 绑定", 交易历史: "等待后端交易历史接口", 资产曲线: "等待后端账本接口", 股票信息: "行情查询与本地缓存", 决策日志: "等待后端决策日志接口", 时间线控制: "等待后端模拟时间线接口" }[tab] ?? "查看子页面";
}
function manageIcon(section: string) {
  if (section === "模型与API") return <KeyRound size={15} />;
  if (section === "Skills") return <Bot size={15} />;
  if (section === "Tools") return <Wrench size={15} />;
  if (section === "触发器") return <Bell size={15} />;
  if (section === "数据管理") return <Database size={15} />;
  return <Settings size={15} />;
}
