import {
  Activity,
  AlertTriangle,
  BarChart3,
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
import { Account, Message, Provider, RuntimeEvent, Session, ToolSchema, api } from "./api";
import {
  demoAccounts,
  demoDecisions,
  demoHoldings,
  demoPortfolio,
  demoProviders,
  demoSessions,
  demoTimeline,
  demoTrades
} from "./mockData";
import type {
  DecisionLog,
  Holding,
  PortfolioPoint,
  ProviderCard,
  RouteKey,
  SessionStatus,
  TimelineItem,
  ToolResultPayload,
  TradeRecord,
  UIAccount,
  UISession
} from "./types";

const navItems: Array<{ key: RouteKey; label: string; sub: string }> = [
  { key: "trade", label: "交易（LLM）", sub: "WebChat 工作台" },
  { key: "view", label: "查看", sub: "全局观察" },
  { key: "edit", label: "修改", sub: "审计修改" },
  { key: "manage", label: "管理", sub: "能力配置" }
];
const viewTabs = ["总览", "账号详情", "交易历史", "资产曲线", "股票信息", "决策日志", "时间线控制"];
const editTabs = ["账户信息", "余额修改", "持仓修改", "订单修正", "会话绑定"];
const manageSections = ["模型与API", "Skills", "Tools", "触发器", "数据管理", "系统设置"];
const defaultProvider = { provider_type: "deepseek", name: "DeepSeek Reasoner", base_url: "https://api.deepseek.com", api_key: "", model: "deepseek-reasoner" };
const moneyFormatter = new Intl.NumberFormat("zh-CN", { style: "currency", currency: "CNY", maximumFractionDigits: 2 });
const numberFormatter = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 });

function routeFromPath(pathname: string): RouteKey {
  const first = pathname.split("/").filter(Boolean)[0];
  return first === "view" || first === "edit" || first === "manage" ? first : "trade";
}
function formatMoney(value: number): string { return moneyFormatter.format(value); }
function formatCompactMoney(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 100_000_000) return `${numberFormatter.format(value / 100_000_000)}亿`;
  if (abs >= 10_000) return `${numberFormatter.format(value / 10_000)}万`;
  return numberFormatter.format(value);
}
function formatPercent(value: number): string { return `${value > 0 ? "+" : ""}${value.toFixed(2)}%`; }
function trendClass(value: number): "rise" | "fall" | "flat" { return value > 0 ? "rise" : value < 0 ? "fall" : "flat"; }
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
function readableDomain(raw: string): string {
  try {
    const url = raw.startsWith("http") ? new URL(raw) : new URL(`https://${raw}`);
    const parts = url.hostname.replace(/^www\./, "").split(".");
    if (parts.length <= 3) return parts.join(".");
    if (["com.cn", "gov.cn", "org.cn", "net.cn"].includes(parts.slice(-2).join("."))) return parts.slice(-3).join(".");
    return parts.slice(-3).join(".");
  } catch { return raw.replace(/^www\./, ""); }
}
function isRealSession(sessionId: string, sessions: Session[]): boolean { return sessions.some((session) => session.id === sessionId); }
function messageToTimeline(message: Message): TimelineItem {
  const kind: TimelineItem["kind"] = message.role === "assistant" ? "assistant" : message.message_type === "event" ? "event" : message.role === "tool" ? "tool-result" : "user";
  return { id: message.id, kind, time: humanTime(message.created_at), title: message.role === "assistant" ? "助手" : message.message_type === "event" ? "事件" : message.role === "tool" ? "工具结果" : "用户", body: message.content, raw: { role: message.role, message_type: message.message_type, trigger_id: message.trigger_id } };
}

export default function App() {
  const [route, setRoute] = useState<RouteKey>(() => routeFromPath(window.location.pathname));
  const [providers, setProviders] = useState<Provider[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [tools, setTools] = useState<ToolSchema[]>([]);
  const [events, setEvents] = useState<RuntimeEvent[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState("");
  const [providerForm, setProviderForm] = useState(defaultProvider);
  const [accountName, setAccountName] = useState("Alpha-量化增强");
  const [sessionName, setSessionName] = useState("盘中策略观察");
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [viewTab, setViewTab] = useState(viewTabs[0]);
  const [editTab, setEditTab] = useState(editTabs[0]);
  const [manageSection, setManageSection] = useState(manageSections[0]);
  const [leftCollapsed, setLeftCollapsed] = useState(false);
  const [localTimeline, setLocalTimeline] = useState<TimelineItem[]>([]);
  const [inspectorWidth, setInspectorWidth] = useState(() => {
    const stored = Number(window.localStorage.getItem("autostock.inspectorWidth"));
    return Number.isFinite(stored) && stored >= 420 ? stored : 460;
  });
  const dragRef = useRef(false);

  const providerCards = useMemo<ProviderCard[]>(() => providers.length === 0 ? demoProviders : providers.map((provider) => ({
    id: provider.id,
    name: provider.name,
    type: provider.provider_type === "deepseek" ? "DeepSeek" : "OpenAI-Compatible",
    endpoint: provider.base_url || "未配置 endpoint",
    modelCount: 1,
    status: provider.has_api_key ? "已连接" : "未配置",
    updatedAt: humanTime(provider.updated_at),
    supportsReasoning: provider.thinking_mode === "reasoning" || provider.provider_type === "deepseek"
  })), [providers]);

  const uiAccounts = useMemo<UIAccount[]>(() => {
    if (accounts.length === 0) return demoAccounts;
    return accounts.map((account, index) => {
      const base = account.initial_cash || 1_000_000;
      const totalAsset = base * (1.02 + index * 0.015);
      const cash = base * (0.34 + index * 0.05);
      const todayPnlPct = index % 2 === 0 ? 0.72 + index * 0.18 : -0.34;
      return { id: account.id, name: account.name, broker: "A股全真（本地模拟）", initialCash: base, cash, availableCash: cash * 0.96, frozenCash: cash * 0.04, marketValue: totalAsset - cash, totalAsset, todayPnl: totalAsset * todayPnlPct / 100, todayPnlPct, totalPnl: totalAsset - base, totalPnlPct: ((totalAsset - base) / base) * 100, runningSessions: sessions.filter((session) => session.llm_account_id === account.id && normalizeStatus(session.status) === "running").length };
    });
  }, [accounts, sessions]);

  const uiSessions = useMemo<UISession[]>(() => {
    if (sessions.length === 0) return demoSessions;
    const fallbackAccount = uiAccounts[0]?.id ?? demoAccounts[0].id;
    return sessions.map((session, index) => {
      const account = accounts.find((item) => item.id === session.llm_account_id);
      const provider = providers.find((item) => item.id === account?.provider_id);
      return { id: session.id, accountId: session.llm_account_id ?? fallbackAccount, name: session.name, providerId: provider?.id ?? "provider-local", providerType: provider?.provider_type ?? "deepseek", providerName: provider?.name ?? "Local Provider", model: provider?.model ?? (index % 2 === 0 ? "deepseek-reasoner" : "gpt-4.1"), skillId: session.skill_id ?? "default-trader", skillName: session.skill_id ?? "默认交易 Skill", status: normalizeStatus(session.status), lastRunAt: humanTime(session.updated_at), hasTriggers: index % 2 === 0, mode: "realtime" };
    });
  }, [accounts, providers, sessions, uiAccounts]);

  const selectedSession = useMemo(() => uiSessions.find((session) => session.id === selectedSessionId) ?? uiSessions[0] ?? null, [selectedSessionId, uiSessions]);
  const selectedAccount = useMemo(() => uiAccounts.find((account) => account.id === selectedSession?.accountId) ?? uiAccounts[0] ?? null, [selectedSession, uiAccounts]);
  const timeline = useMemo(() => [...(messages.length ? messages.map(messageToTimeline) : demoTimeline), ...localTimeline], [localTimeline, messages]);

  useEffect(() => { void loadAll(); }, []);
  useEffect(() => {
    const onPop = () => setRoute(routeFromPath(window.location.pathname));
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);
  useEffect(() => {
    if (selectedSession && selectedSession.id !== selectedSessionId) setSelectedSessionId(selectedSession.id);
  }, [selectedSession, selectedSessionId]);
  useEffect(() => {
    if (!selectedSessionId || !isRealSession(selectedSessionId, sessions)) { setMessages([]); setEvents([]); return; }
    void loadMessages(selectedSessionId);
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const socket = new WebSocket(`${protocol}//${window.location.host}/ws/sessions/${selectedSessionId}`);
    socket.onmessage = (event) => {
      const payload = JSON.parse(event.data) as RuntimeEvent;
      setEvents((current) => [payload, ...current].slice(0, 60));
      if (["assistant_message", "run_finished", "message.created", "run.finished"].includes(payload.type)) { void loadMessages(selectedSessionId); void loadSessions(); }
    };
    socket.onerror = () => setError("WebSocket 连接失败，当前仅显示已加载数据。");
    return () => socket.close();
  }, [selectedSessionId, sessions]);
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
      setProviders(nextProviders); setAccounts(nextAccounts); setSessions(nextSessions); setTools(nextTools);
    } catch (err) { setError(err instanceof Error ? err.message : "加载前端状态失败，已切换到演示数据。"); }
  }
  async function loadSessions() { setSessions(await api.sessions()); }
  async function loadMessages(sessionId: string) { setMessages(await api.messages(sessionId)); }
  function navigate(next: RouteKey) { setRoute(next); if (window.location.pathname !== `/${next}`) window.history.pushState({}, "", `/${next}`); }
  function startResize(event: MouseEvent<HTMLDivElement>) { event.preventDefault(); dragRef.current = true; document.body.classList.add("is-resizing"); }

  async function createProvider(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(null);
    try {
      const created = await api.createProvider({ provider_type: providerForm.provider_type, name: providerForm.name, base_url: providerForm.base_url || null, api_key: providerForm.api_key, model: providerForm.model, supports_tools: true, supports_strict_schema: false, strict_tool_schema: false });
      setProviders((current) => [created, ...current]); setProviderForm({ ...defaultProvider, api_key: "" });
    } catch (err) { setError(err instanceof Error ? err.message : "创建 Provider 失败。"); } finally { setBusy(false); }
  }
  async function createAccount(event: FormEvent) {
    event.preventDefault();
    if (!providers[0]) { setError("需要先在管理页创建真实 Provider，才能创建账户。"); return; }
    setBusy(true); setError(null);
    try {
      const created = await api.createAccount({ name: accountName, provider_id: providers[0].id, initial_cash: 1_000_000 });
      setAccounts((current) => [created, ...current]);
    }
    catch (err) { setError(err instanceof Error ? err.message : "创建账户失败。"); } finally { setBusy(false); }
  }
  async function createSession(event?: FormEvent) {
    event?.preventDefault();
    const account = accounts.find((item) => item.id === selectedAccount?.id) ?? accounts[0];
    if (!account) { setError("需要先创建真实账户，演示账户不能写入后端 Session。"); return; }
    setBusy(true); setError(null);
    try {
      const created = await api.createSession({ name: sessionName, llm_account_id: account.id, skill_id: "default-trader" });
      setSessions((current) => [created, ...current]); setSelectedSessionId(created.id); setLocalTimeline([]); setEvents([]);
    } catch (err) { setError(err instanceof Error ? err.message : "创建 Session 失败。"); } finally { setBusy(false); }
  }
  async function sendMessage(mode: "run" | "event" | "write") {
    if (!selectedSession || !draft.trim()) return;
    const content = draft.trim(); setDraft(""); setBusy(true); setError(null);
    const localUserItem: TimelineItem = { id: `local-${Date.now()}`, kind: mode === "event" ? "event" : "user", time: new Date().toLocaleTimeString("zh-CN", { hour12: false }), title: mode === "event" ? "手动事件" : "用户", body: content, raw: { local: !isRealSession(selectedSession.id, sessions), mode } };
    try {
      if (!isRealSession(selectedSession.id, sessions)) {
        setLocalTimeline((current) => [...current, localUserItem, { id: `local-assistant-${Date.now()}`, kind: "assistant", time: new Date().toLocaleTimeString("zh-CN", { hour12: false }), title: "助手", body: "当前运行在演示数据模式。真实发送需要先创建 Provider、账户和 Session。" }]);
        return;
      }
      if (mode === "write") await api.createMessage(selectedSession.id, { role: "user", content, message_type: "user" });
      else await api.runSession(selectedSession.id, { message: mode === "event" ? `[手动事件]\n${content}` : content, max_tool_rounds: 5 });
      await loadMessages(selectedSession.id); await loadSessions();
    } catch (err) { setError(err instanceof Error ? err.message : "发送失败。"); setLocalTimeline((current) => [...current, { ...localUserItem, id: `${localUserItem.id}-failed` }]); }
    finally { setBusy(false); }
  }
  function stopCurrentRun() {
    setLocalTimeline((current) => [...current, { id: `stop-${Date.now()}`, kind: "error", time: new Date().toLocaleTimeString("zh-CN", { hour12: false }), title: "停止请求已记录", body: "当前后端尚未提供 stop run API，前端已保留停止入口与状态反馈。" }]);
  }

  const shellStyle = { "--inspector-width": `${inspectorWidth}px` } as CSSProperties;
  return (
    <main className="app-shell" style={shellStyle}>
      <TopNavigation route={route} onNavigate={navigate} />
      {error && <div className="global-error"><AlertTriangle size={16} />{error}</div>}
      {route === "trade" && <TradePage accounts={uiAccounts} sessions={uiSessions} selectedAccount={selectedAccount} selectedSession={selectedSession} selectedSessionId={selectedSessionId} onSelectSession={setSelectedSessionId} onCreateSession={createSession} sessionName={sessionName} setSessionName={setSessionName} timeline={timeline} holdings={demoHoldings} trades={demoTrades} portfolio={demoPortfolio} events={events} draft={draft} setDraft={setDraft} sendMessage={sendMessage} stopCurrentRun={stopCurrentRun} busy={busy} leftCollapsed={leftCollapsed} setLeftCollapsed={setLeftCollapsed} onStartResize={startResize} />}
      {route === "view" && <ViewPage tab={viewTab} setTab={setViewTab} accounts={uiAccounts} sessions={uiSessions} portfolio={demoPortfolio} trades={demoTrades} decisions={demoDecisions} holdings={demoHoldings} />}
      {route === "edit" && <EditPage tab={editTab} setTab={setEditTab} accounts={uiAccounts} sessions={uiSessions} trades={demoTrades} accountName={accountName} setAccountName={setAccountName} createAccount={createAccount} busy={busy} />}
      {route === "manage" && <ManagePage section={manageSection} setSection={setManageSection} providerCards={providerCards} tools={tools} providerForm={providerForm} setProviderForm={setProviderForm} createProvider={createProvider} busy={busy} />}
    </main>
  );
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
      <div className="top-meta"><span>A股全真（演示）</span><span className="avatar-dot"><UserRound size={14} /></span></div>
    </header>
  );
}

function TradePage(props: {
  accounts: UIAccount[]; sessions: UISession[]; selectedAccount: UIAccount | null; selectedSession: UISession | null; selectedSessionId: string;
  onSelectSession: (id: string) => void; onCreateSession: (event?: FormEvent) => void; sessionName: string; setSessionName: (value: string) => void;
  timeline: TimelineItem[]; holdings: Holding[]; trades: TradeRecord[]; portfolio: PortfolioPoint[]; events: RuntimeEvent[];
  draft: string; setDraft: (value: string) => void; sendMessage: (mode: "run" | "event" | "write") => void; stopCurrentRun: () => void; busy: boolean;
  leftCollapsed: boolean; setLeftCollapsed: (value: boolean) => void; onStartResize: (event: MouseEvent<HTMLDivElement>) => void;
}) {
  return (
    <section className={props.leftCollapsed ? "trade-workspace collapsed" : "trade-workspace"}>
      <AccountSessionSidebar {...props} />
      <section className="chat-workspace panel-frame">
        <SessionHeader selectedAccount={props.selectedAccount} selectedSession={props.selectedSession} />
        <LLMLinearTimeline timeline={props.timeline} />
        <ChatInputBox draft={props.draft} setDraft={props.setDraft} sendMessage={props.sendMessage} stopCurrentRun={props.stopCurrentRun} busy={props.busy} />
      </section>
      <div className="resize-handle" onMouseDown={props.onStartResize} aria-label="调整账户观察栏宽度" />
      <AccountInspectorPanel account={props.selectedAccount} session={props.selectedSession} holdings={props.holdings} trades={props.trades} portfolio={props.portfolio} events={props.events} />
    </section>
  );
}

function AccountSessionSidebar(props: {
  accounts: UIAccount[]; sessions: UISession[]; selectedSessionId: string; onSelectSession: (id: string) => void; onCreateSession: (event?: FormEvent) => void;
  sessionName: string; setSessionName: (value: string) => void; leftCollapsed: boolean; setLeftCollapsed: (value: boolean) => void;
}) {
  if (props.leftCollapsed) {
    return <aside className="account-rail collapsed-rail"><button className="rail-toggle" type="button" onClick={() => props.setLeftCollapsed(false)} title="展开账户栏"><ChevronDown size={16} /></button>{props.accounts.map((account) => <button className="rail-account" key={account.id} type="button" title={account.name}>{account.name.slice(0, 1)}</button>)}</aside>;
  }
  return (
    <aside className="account-rail panel-frame">
      <div className="rail-head"><div><p className="eyebrow">账户与会话</p><h2>Account Tree</h2></div><button className="ghost-button square" type="button" onClick={() => props.setLeftCollapsed(true)} title="折叠账户栏"><ChevronDown size={16} /></button></div>
      <label className="search-field"><Search size={15} /><input placeholder="搜索账户 / 会话" /></label>
      <form className="create-session" onSubmit={props.onCreateSession}><input value={props.sessionName} onChange={(event) => props.setSessionName(event.target.value)} placeholder="新建 Session 名称" /><button type="submit" title="新建 Session"><Plus size={15} /></button></form>
      <div className="account-tree">
        {props.accounts.map((account) => {
          const sessions = props.sessions.filter((session) => session.accountId === account.id);
          return (
            <details className="account-node" key={account.id} open>
              <summary><span className="node-title"><Wallet size={15} />{account.name}</span><span className={trendClass(account.todayPnl)}>{formatCompactMoney(account.todayPnl)}</span></summary>
              <div className="account-node-meta"><span>总资产 {formatCompactMoney(account.totalAsset)}</span><span>{account.runningSessions} running</span></div>
              <div className="session-list">
                {sessions.map((session) => <button className={session.id === props.selectedSessionId ? "session-row active" : "session-row"} key={session.id} onClick={() => props.onSelectSession(session.id)} type="button"><span className={`status-dot ${session.status}`} /><span><strong>{session.name}</strong><small>{session.model} · {session.lastRunAt}</small></span>{session.hasTriggers && <Bell size={13} />}</button>)}
              </div>
            </details>
          );
        })}
      </div>
      <div className="rail-actions"><button className="ghost-button" type="button"><Code2 size={14} />复制</button><button className="ghost-button" type="button"><History size={14} />归档</button></div>
    </aside>
  );
}

function SessionHeader({ selectedAccount, selectedSession }: { selectedAccount: UIAccount | null; selectedSession: UISession | null }) {
  return (
    <header className="session-header">
      <div><p className="eyebrow">LLM Linear Flow</p><h1>{selectedSession?.name ?? "未选择 Session"}</h1><div className="session-tags"><span>账户：{selectedAccount?.name ?? "--"}</span><span>模型：{selectedSession?.model ?? "--"}</span><span>Provider：{selectedSession?.providerName ?? "--"}</span><span>Skill：{selectedSession?.skillName ?? "--"}</span><span>模式：{selectedSession?.mode === "replay" ? "回放" : "实时"}</span><span className={selectedSession ? `status-chip ${selectedSession.status}` : "status-chip"}>{selectedSession ? statusLabel(selectedSession.status) : "--"}</span></div></div>
      <div className="header-actions"><button className="ghost-button" type="button"><Play size={15} />运行一次</button><button className="ghost-button" type="button"><StopCircle size={15} />停止</button><button className="ghost-button" type="button"><Bell size={15} />触发器摘要</button><button className="ghost-button" type="button"><SlidersHorizontal size={15} />修改配置</button></div>
    </header>
  );
}

function LLMLinearTimeline({ timeline }: { timeline: TimelineItem[] }) {
  return <div className="timeline-scroll"><div className="timeline-line" />{timeline.map((item, index) => <TimelineCard item={item} key={item.id} index={index} />)}</div>;
}
function TimelineCard({ item, index }: { item: TimelineItem; index: number }) {
  return <article className={`timeline-card ${item.kind}`} style={{ animationDelay: `${Math.min(index * 45, 420)}ms` }}><div className="timeline-time"><Clock3 size={13} />{item.time}</div><div className="timeline-marker"><TimelineIcon kind={item.kind} /></div><div className="timeline-body"><header><span>{item.title}</span>{item.toolName && <code>{item.toolName}</code>}</header>{item.kind === "tool-call" && <ToolCallCard item={item} />}{item.result && <ToolResultRenderer payload={item.result} raw={item.raw} />}{item.body && <p>{item.body}</p>}{item.raw && item.kind !== "tool-call" && <RawJson data={item.raw} />}</div></article>;
}
function TimelineIcon({ kind }: { kind: TimelineItem["kind"] }) {
  if (kind === "user") return <UserRound size={14} />;
  if (kind === "event") return <Zap size={14} />;
  if (kind === "assistant") return <Bot size={14} />;
  if (kind === "reasoning") return <Activity size={14} />;
  if (kind === "tool-call") return <Wrench size={14} />;
  if (kind === "tool-result") return <CheckCircle2 size={14} />;
  if (kind === "order") return <BarChart3 size={14} />;
  return <AlertTriangle size={14} />;
}
function ToolCallCard({ item }: { item: TimelineItem }) {
  return <details className="tool-call"><summary><span>[Tool Call] {item.toolName}</span><small>{item.argsSummary}</small><span className="tool-status">{item.status ?? "started"} · {item.durationMs ?? 0}ms</span></summary><div className="tool-call-detail"><InfoGrid items={[["调用工具", item.toolName ?? "--"], ["调用状态", item.status ?? "--"], ["耗时", `${item.durationMs ?? 0}ms`], ["参数摘要", item.argsSummary ?? "--"]]} />{item.raw && <RawJson data={item.raw} />}</div></details>;
}

function ToolResultRenderer({ payload, raw }: { payload: ToolResultPayload; raw?: Record<string, unknown> }) {
  if (payload.kind === "search") return <TavilySearchRenderer payload={payload} raw={raw} />;
  if (payload.kind === "quote") return <MarketQuoteRenderer payload={payload} raw={raw} />;
  if (payload.kind === "history") return <MarketHistoryRenderer payload={payload} raw={raw} />;
  if (payload.kind === "order") return <OrderResultRenderer payload={payload} raw={raw} />;
  if (payload.kind === "portfolio") return <PortfolioStateRenderer payload={payload} raw={raw} />;
  return <div className="tool-result"><div className="result-title">{payload.title}</div><RawJson data={payload.data} />{raw && <RawJson data={raw} />}</div>;
}
function TavilySearchRenderer({ payload, raw }: { payload: Extract<ToolResultPayload, { kind: "search" }>; raw?: Record<string, unknown> }) {
  return <div className="tool-result search-result"><div className="result-title">搜索：{payload.query}</div><ol>{payload.items.map((item, index) => <li key={`${item.url}-${index}`}><details><summary><span>{item.title}</span><small>{readableDomain(item.domain || item.url)}</small></summary><p>{item.summary}</p><InfoGrid items={[["URL", item.url], ["发布时间", item.publishedAt], ["相关度", item.score.toFixed(2)]]} /></details></li>)}</ol>{raw && <RawJson data={raw} />}</div>;
}
function MarketQuoteRenderer({ payload, raw }: { payload: Extract<ToolResultPayload, { kind: "quote" }>; raw?: Record<string, unknown> }) {
  const quote = payload.quote;
  return <div className="compact-quote"><strong>{quote.name} {quote.symbol}</strong><span>¥{quote.price.toFixed(2)}</span><span className={trendClass(quote.change)}>{quote.change > 0 ? "+" : ""}{quote.change.toFixed(2)} {formatPercent(quote.changePct)}</span><span>今开 {quote.open.toFixed(2)}</span><span>最高 {quote.high.toFixed(2)}</span><span>最低 {quote.low.toFixed(2)}</span><span>成交额 {quote.amountText}</span>{raw && <RawJson data={raw} />}</div>;
}
function MarketHistoryRenderer({ payload, raw }: { payload: Extract<ToolResultPayload, { kind: "history" }>; raw?: Record<string, unknown> }) {
  return <div className="history-result"><div className="result-title">{payload.history.name} {payload.history.symbol} · {payload.history.period} · {payload.history.adjust}</div><CandleVolumeChart values={payload.history.candles} volumes={payload.history.volumes} /><details className="large-chart-toggle"><summary>展开查看大图</summary><CandleVolumeChart values={payload.history.candles} volumes={payload.history.volumes} large /></details>{raw && <RawJson data={raw} />}</div>;
}
function OrderResultRenderer({ payload, raw }: { payload: Extract<ToolResultPayload, { kind: "order" }>; raw?: Record<string, unknown> }) {
  const order = payload.order;
  return <div className="order-result"><strong>{order.status}</strong><InfoGrid items={[["股票", `${order.symbol} ${order.name}`], ["数量", `${order.quantity} 股`], ["委托价", formatMoney(order.orderPrice)], ["成交价", formatMoney(order.filledPrice)], ["手续费", formatMoney(order.fee)], ["来源 Session", order.sourceSession], ["来源模型", order.sourceModel]]} />{raw && <RawJson data={raw} />}</div>;
}
function PortfolioStateRenderer({ payload, raw }: { payload: Extract<ToolResultPayload, { kind: "portfolio" }>; raw?: Record<string, unknown> }) {
  const account = payload.account;
  return <div className="portfolio-grid"><Metric label="总资产" value={formatMoney(account.totalAsset)} /><Metric label="现金" value={formatMoney(account.cash)} /><Metric label="持仓市值" value={formatMoney(account.marketValue)} /><Metric label="今日收益" value={formatMoney(account.todayPnl)} tone={trendClass(account.todayPnl)} /><Metric label="累计收益" value={formatMoney(account.totalPnl)} tone={trendClass(account.totalPnl)} /><Metric label="冻结资金" value={formatMoney(account.frozenCash)} />{raw && <RawJson data={raw} />}</div>;
}

function ChatInputBox(props: { draft: string; setDraft: (value: string) => void; sendMessage: (mode: "run" | "event" | "write") => void; stopCurrentRun: () => void; busy: boolean }) {
  return <footer className="chat-composer"><div className="quick-events">{["开盘前观察", "盘中检查", "尾盘决策", "收盘复盘"].map((event) => <button key={event} type="button" onClick={() => props.setDraft(event)}>{event}</button>)}</div><div className="composer-row"><textarea value={props.draft} onChange={(event) => props.setDraft(event.target.value)} placeholder="输入给 LLM 的问题。Shift + Enter 换行，Enter 发送。" onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void props.sendMessage("run"); } }} /><div className="send-stack"><button className="send-button" type="button" disabled={props.busy || !props.draft.trim()} onClick={() => props.sendMessage("run")}><Send size={17} />发送</button><button className="ghost-button" type="button" disabled={props.busy || !props.draft.trim()} onClick={() => props.sendMessage("event")}>作为事件运行</button><button className="ghost-button" type="button" disabled={props.busy || !props.draft.trim()} onClick={() => props.sendMessage("write")}>只写入</button><button className="danger-button" type="button" onClick={props.stopCurrentRun}><StopCircle size={15} />停止</button></div></div><div className="composer-foot">可用工具：market.quote · market.history · tavily.search · order.buy · order.sell · portfolio</div></footer>;
}

function AccountInspectorPanel(props: { account: UIAccount | null; session: UISession | null; holdings: Holding[]; trades: TradeRecord[]; portfolio: PortfolioPoint[]; events: RuntimeEvent[] }) {
  const account = props.account;
  return <aside className="account-inspector panel-frame"><header className="inspector-title"><div><p className="eyebrow">账户观察 · 刷新于 10:30:20</p><h2>{account?.name ?? "未选择账户"}</h2></div><Eye size={17} /></header>{account && <><div className="context-strip"><span>当前账户：{account.name}</span><span>当前 Session：{props.session?.name ?? "--"}</span><span>模型：{props.session?.model ?? "--"}</span><span>Skill：{props.session?.skillName ?? "--"}</span></div><div className="metrics-grid dense"><Metric label="总资产" value={formatMoney(account.totalAsset)} /><Metric label="今日收益" value={formatMoney(account.todayPnl)} tone={trendClass(account.todayPnl)} /><Metric label="现金" value={formatMoney(account.cash)} /><Metric label="持仓市值" value={formatMoney(account.marketValue)} /></div><section className="inspector-section"><PanelHeader icon={<LineChart size={16} />} title="资产趋势（近 7 日）" /><MiniLineChart values={props.portfolio.map((point) => point.total)} /></section><section className="inspector-section"><PanelHeader icon={<Gauge size={16} />} title="数字指标" /><InfoGrid items={[["初始资金", formatMoney(account.initialCash)], ["可用资金", formatMoney(account.availableCash)], ["冻结资金", formatMoney(account.frozenCash)], ["累计收益", formatMoney(account.totalPnl)], ["累计收益率", formatPercent(account.totalPnlPct)], ["今日 run 次数", "6"], ["今日 tool call", "42"], ["今日成本估算", "¥0.18"]]} /></section><section className="inspector-section"><PanelHeader icon={<Table2 size={16} />} title="持仓股票" /><div className="holding-list">{props.holdings.map((holding) => <HoldingRow holding={holding} key={holding.symbol} />)}</div></section><section className="inspector-section"><PanelHeader icon={<History size={16} />} title="交易记录（今日）" /><TradeList trades={props.trades.slice(0, 4)} compact /></section><section className="inspector-section"><PanelHeader icon={<Activity size={16} />} title="实时事件" />{props.events.length === 0 ? <p className="muted">暂无后端 WebSocket 事件。</p> : props.events.slice(0, 6).map((event, index) => <div className="event-line" key={`${event.type}-${index}`}><span>{event.type}</span><small>{event.tool_name ?? event.status ?? event.error ?? event.run_id}</small></div>)}</section></>}</aside>;
}

function HoldingRow({ holding }: { holding: Holding }) {
  return <details className="holding-row"><summary><span>{holding.symbol} {holding.name}</span><small>{holding.quantity}股 · 市值 {formatMoney(holding.marketValue)}</small><strong className={trendClass(holding.pnlPct)}>{formatPercent(holding.pnlPct)}</strong></summary><InfoGrid items={[["可卖数量", `${holding.sellable} 股`], ["平均成本", formatMoney(holding.cost)], ["现价", formatMoney(holding.price)], ["浮动盈亏", formatMoney(holding.pnl)], ["今日涨跌幅", formatPercent(holding.todayPct)], ["买入来源", holding.sourceSession]]} /><p>{holding.latestReason}</p><MiniLineChart values={holding.sparkline} compact /></details>;
}

function ViewPage(props: { tab: string; setTab: (tab: string) => void; accounts: UIAccount[]; sessions: UISession[]; portfolio: PortfolioPoint[]; trades: TradeRecord[]; decisions: DecisionLog[]; holdings: Holding[] }) {
  const totalAsset = props.accounts.reduce((sum, account) => sum + account.totalAsset, 0);
  const todayPnl = props.accounts.reduce((sum, account) => sum + account.todayPnl, 0);
  return <section className="module-page view-page"><PageHeader eyebrow="查看 - 总览（默认）" title="全局观察、对比分析、行情浏览、模拟时间线控制" actions={<><button className="ghost-button"><RefreshCw size={15} />刷新</button><button className="ghost-button"><Pause size={15} />暂停同步</button></>} /><SubTabs tabs={viewTabs} active={props.tab} onChange={props.setTab} /><FilterBar /><div className="account-card-row">{props.accounts.map((account) => <AccountSummaryCard account={account} key={account.id} />)}</div><div className="view-grid"><section className="panel-frame chart-panel wide"><PanelHeader icon={<LineChart size={16} />} title="资产对比（全部账号 + 沪深300基准）" /><MultiLineChart portfolio={props.portfolio} accounts={props.accounts} /></section><section className="panel-frame key-metrics"><PanelHeader icon={<Gauge size={16} />} title="关键指标汇总" /><Metric label="总资产（元）" value={formatMoney(totalAsset)} /><Metric label="今日收益" value={formatMoney(todayPnl)} tone={trendClass(todayPnl)} /><Metric label="累计收益" value={formatMoney(props.accounts.reduce((sum, account) => sum + account.totalPnl, 0))} tone="rise" /><Metric label="运行中 Session" value={String(props.sessions.filter((session) => session.status === "running").length)} /><Metric label="持仓股票数" value={String(props.holdings.length)} /></section><section className="panel-frame"><PanelHeader icon={<MessageSquare size={16} />} title="最近 LLM 决策" /><DecisionTable decisions={props.decisions} /></section><section className="panel-frame"><PanelHeader icon={<History size={16} />} title="最近交易" /><TradeList trades={props.trades} /></section></div><section className="subpage-strip">{viewTabs.slice(1).map((tab, index) => <button className="subpage-card" key={tab} type="button" onClick={() => props.setTab(tab)}><span>{index + 1}</span><strong>{tab}</strong><small>{viewTabDescription(tab)}</small></button>)}</section></section>;
}

function EditPage(props: { tab: string; setTab: (tab: string) => void; accounts: UIAccount[]; sessions: UISession[]; trades: TradeRecord[]; accountName: string; setAccountName: (name: string) => void; createAccount: (event: FormEvent) => void; busy: boolean }) {
  return <section className="module-page edit-page"><PageHeader eyebrow="修改 - 账户信息（默认）" title="人工修改账户状态与 Session 绑定，所有变更进入审计记录" actions={<><button className="ghost-button">取消</button><button className="send-button"><Save size={15} />保存</button></>} /><SubTabs tabs={editTabs} active={props.tab} onChange={props.setTab} /><div className="edit-grid"><section className="panel-frame form-panel wide"><PanelHeader icon={<ShieldAlert size={16} />} title="账户身份信息" /><form className="form-grid" onSubmit={props.createAccount}><label>账户名<input value={props.accountName} onChange={(event) => props.setAccountName(event.target.value)} /></label><label>账户 PID<input value="ACC-202405-001" readOnly /></label><label>资金账户<input value="SH-B***8921" readOnly /></label><label>风险等级<select defaultValue="稳健型"><option>稳健型</option><option>激进型</option></select></label><label>交易权限<select defaultValue="A股 / 融资融券"><option>A股 / 融资融券</option><option>A股</option></select></label><label>开户营业部<input value="中信证券上海分公司" readOnly /></label><label className="wide-field">修改原因<textarea defaultValue="模拟账户用于策略验证与回测，需要保留审计原因。" /></label><button className="send-button" type="submit" disabled={props.busy}><Plus size={15} />创建真实账户</button></form></section><section className="panel-frame"><PanelHeader icon={<Wallet size={16} />} title="余额修改" /><InfoGrid items={[["当前现金", formatMoney(props.accounts[0]?.cash ?? 0)], ["可用资金", formatMoney(props.accounts[0]?.availableCash ?? 0)], ["冻结资金", formatMoney(props.accounts[0]?.frozenCash ?? 0)], ["影响 Session", String(props.sessions.length)]]} /></section><section className="panel-frame wide"><PanelHeader icon={<Table2 size={16} />} title="会话与模型关系概览" /><table className="data-table"><thead><tr><th>Session</th><th>账户</th><th>模型</th><th>Skill</th><th>状态</th><th>操作</th></tr></thead><tbody>{props.sessions.map((session) => <tr key={session.id}><td>{session.name}</td><td>{props.accounts.find((account) => account.id === session.accountId)?.name ?? "--"}</td><td>{session.model}</td><td>{session.skillName}</td><td>{statusLabel(session.status)}</td><td><button className="link-button">修改</button></td></tr>)}</tbody></table></section><section className="panel-frame audit-panel"><PanelHeader icon={<AlertTriangle size={16} />} title="高风险提示" /><p>账户、余额、持仓和订单修正会影响收益归因。保存时必须记录修改前后、原因、影响账号和影响 Session，并在资产曲线打人工干预标记。</p></section></div><section className="panel-frame audit-log-table"><PanelHeader icon={<History size={16} />} title="审计记录" /><TradeList trades={props.trades} /></section></section>;
}

function ManagePage(props: { section: string; setSection: (section: string) => void; providerCards: ProviderCard[]; tools: ToolSchema[]; providerForm: typeof defaultProvider; setProviderForm: (value: typeof defaultProvider) => void; createProvider: (event: FormEvent) => void; busy: boolean }) {
  return <section className="module-page manage-page"><PageHeader eyebrow="管理中心 - 模型与 API（默认）" title="管理 LLM 提供商、API 配置、Skills、Tools、触发器与数据源" actions={<><button className="ghost-button"><KeyRound size={15} />使用指南</button><button className="send-button"><Plus size={15} />新增提供商</button></>} /><div className="manage-layout"><aside className="panel-frame secondary-nav">{manageSections.map((section) => <button className={props.section === section ? "secondary-item active" : "secondary-item"} key={section} type="button" onClick={() => props.setSection(section)}>{manageIcon(section)}<span>{section}</span></button>)}</aside><section className="panel-frame manage-main"><PanelHeader icon={<KeyRound size={16} />} title="提供商配置详情" /><div className="provider-cards">{props.providerCards.map((provider) => <article className="provider-card" key={provider.id}><header><strong>{provider.name}</strong><span className={provider.status === "已连接" ? "online" : "offline"}>{provider.status}</span></header><InfoGrid items={[["接口 URL", provider.endpoint], ["模型数量", String(provider.modelCount)], ["更新时间", provider.updatedAt], ["可见 Reasoning", provider.supportsReasoning ? "支持" : "按模型返回"]]} /><button className="ghost-button">管理配置</button></article>)}</div><form className="provider-form" onSubmit={props.createProvider}><label>Provider 类型<select value={props.providerForm.provider_type} onChange={(event) => props.setProviderForm({ ...props.providerForm, provider_type: event.target.value })}><option value="deepseek">DeepSeek</option><option value="openai_compatible">OpenAI-Compatible</option></select></label><label>名称<input value={props.providerForm.name} onChange={(event) => props.setProviderForm({ ...props.providerForm, name: event.target.value })} /></label><label>Base URL<input value={props.providerForm.base_url} onChange={(event) => props.setProviderForm({ ...props.providerForm, base_url: event.target.value })} /></label><label>模型<input value={props.providerForm.model} onChange={(event) => props.setProviderForm({ ...props.providerForm, model: event.target.value })} /></label><label>API Key<input type="password" value={props.providerForm.api_key} onChange={(event) => props.setProviderForm({ ...props.providerForm, api_key: event.target.value })} /></label><button className="send-button" type="submit" disabled={props.busy || !props.providerForm.api_key}>保存 Provider</button></form></section><aside className="panel-frame tool-catalog"><PanelHeader icon={<Wrench size={16} />} title="Tools（工具目录）" /><div className="tool-table">{(props.tools.length > 0 ? props.tools : demoToolSchemas()).map((tool) => <div className="tool-table-row" key={tool.name}><span>{tool.name}</span><small>{tool.description}</small><strong>{tool.strict ? "Strict" : "Best effort"}</strong><button className="link-button">测试</button></div>)}</div><div className="json-test-block"><PanelHeader icon={<Code2 size={15} />} title="工具测试" /><pre>{`{
  "symbol": "600519.SH",
  "start_date": "2024-05-01",
  "end_date": "2024-05-15"
}`}</pre><button className="send-button">运行</button></div></aside></div><section className="panel-frame capability-matrix"><PanelHeader icon={<Database size={16} />} title="模型能力矩阵" /><table className="data-table"><thead><tr><th>提供商</th><th>模型</th><th>上下文窗口</th><th>工具调用</th><th>结构化输出</th><th>Strict Schema</th><th>可见 Reasoning</th><th>日志上限</th><th>费用</th></tr></thead><tbody>{[["OpenAI-Compatible", "gpt-4.1", "128K", "支持", "支持", "支持", "按模型", "120 RPM", "$0.02 / $0.08"], ["OpenAI-Compatible", "gpt-4o-mini", "128K", "支持", "支持", "支持", "按模型", "300 RPM", "$0.003 / $0.01"], ["DeepSeek", "deepseek-chat", "128K", "支持", "支持", "支持", "隐藏", "200 RPM", "$0.003 / $0.01"], ["DeepSeek", "deepseek-reasoner", "128K", "部分支持", "支持", "支持", "可见", "100 RPM", "$0.006 / $0.018"]].map((row) => <tr key={row.join("-")}>{row.map((cell) => <td key={cell}>{cell}</td>)}</tr>)}</tbody></table></section></section>;
}

function FilterBar() {
  return <div className="filter-bar"><button><ListFilter size={14} />全部账户</button><button>全部策略</button><button>全部市场：A股</button><label>起始日期<input type="date" defaultValue="2024-05-01" /></label><label>结束日期<input type="date" defaultValue="2024-05-16" /></label><button className="send-button">筛选</button><button className="ghost-button">重置</button><span className="auto-refresh"><span />自动刷新 30s</span></div>;
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
  return <div className="info-grid">{items.map(([label, value]) => <div key={`${label}-${value}`}><span>{label}</span><strong>{value}</strong></div>)}</div>;
}
function Metric({ label, value, tone }: { label: string; value: string; tone?: "rise" | "fall" | "flat" }) {
  return <div className="metric"><span>{label}</span><strong className={tone}>{value}</strong></div>;
}
function AccountSummaryCard({ account }: { account: UIAccount }) {
  return <article className="account-summary-card"><header><span>{account.name}</span><MiniLineChart values={[10, 11, 10.8, 11.5, 12.2, 11.9, 12.8]} compact /></header><small>{account.broker}</small><strong>{formatMoney(account.totalAsset)}</strong><div><span>今日收益</span><b className={trendClass(account.todayPnl)}>{formatMoney(account.todayPnl)} · {formatPercent(account.todayPnlPct)}</b></div><div><span>持仓</span><b>{formatCompactMoney(account.marketValue)}</b></div></article>;
}
function TradeList({ trades, compact = false }: { trades: TradeRecord[]; compact?: boolean }) {
  return <table className={compact ? "data-table compact" : "data-table"}><thead><tr><th>时间</th><th>方向</th><th>股票</th><th>数量</th><th>价格</th><th>金额</th><th>状态</th></tr></thead><tbody>{trades.map((trade) => <tr key={trade.id}><td>{trade.time}</td><td className={trade.side === "buy" ? "rise" : "fall"}>{trade.side === "buy" ? "买入" : "卖出"}</td><td>{trade.symbol} {trade.name}</td><td>{trade.quantity}</td><td>{trade.price.toFixed(2)}</td><td>{formatCompactMoney(trade.amount)}</td><td>{trade.status}</td></tr>)}</tbody></table>;
}
function DecisionTable({ decisions }: { decisions: DecisionLog[] }) {
  return <table className="data-table"><thead><tr><th>时间</th><th>账户</th><th>Session</th><th>模型</th><th>触发</th><th>Tool</th><th>动作</th><th>结果</th></tr></thead><tbody>{decisions.map((decision) => <tr key={`${decision.time}-${decision.session}`}><td>{decision.time}</td><td>{decision.account}</td><td>{decision.session}</td><td>{decision.model}</td><td>{decision.trigger}</td><td>{decision.toolCalls}</td><td>{decision.action}</td><td>{decision.result}</td></tr>)}</tbody></table>;
}
function MiniLineChart({ values, compact = false }: { values: number[]; compact?: boolean }) {
  const points = linePoints(values, 100, compact ? 28 : 52);
  return <svg className={compact ? "mini-chart compact" : "mini-chart"} viewBox={`0 0 100 ${compact ? 28 : 52}`} role="img" aria-label="资产曲线"><defs><linearGradient id="lineGlow" x1="0" x2="1"><stop offset="0" stopColor="#4c8bff" /><stop offset="1" stopColor="#2cd6b3" /></linearGradient></defs><polyline points={points} fill="none" stroke="url(#lineGlow)" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />{points.split(" ").filter(Boolean).map((point) => { const [x, y] = point.split(","); return <circle cx={x} cy={y} r="1.3" fill="#86a8ff" key={point} />; })}</svg>;
}
function MultiLineChart({ portfolio, accounts }: { portfolio: PortfolioPoint[]; accounts: UIAccount[] }) {
  const base = portfolio.map((point) => point.total);
  const benchmark = portfolio.map((point) => point.benchmark ?? point.total * 0.86);
  return <div className="multi-chart"><div className="legend-row">{accounts.slice(0, 4).map((account, index) => <span key={account.id}><i style={{ background: ["#4c8bff", "#9a6cff", "#2cd6b3", "#f59e0b"][index] }} />{account.name}</span>)}<span><i className="benchmark" />沪深300</span></div><svg viewBox="0 0 640 260" role="img" aria-label="多账户资产曲线">{[0, 1, 2, 3, 4].map((row) => <line key={row} x1="24" x2="620" y1={30 + row * 45} y2={30 + row * 45} className="grid-line" />)}<polyline points={linePoints(base, 596, 190, 24, 30)} className="chart-line blue" /><polyline points={linePoints(base.map((value, index) => value * (0.92 + index * 0.01)), 596, 190, 24, 30)} className="chart-line violet" /><polyline points={linePoints(base.map((value, index) => value * (0.82 + index * 0.025)), 596, 190, 24, 30)} className="chart-line green" /><polyline points={linePoints(base.map((value) => value * 0.72), 596, 190, 24, 30)} className="chart-line amber" /><polyline points={linePoints(benchmark, 596, 190, 24, 30)} className="chart-line benchmark" /></svg><div className="chart-foot">对比基准：沪深300（000300） · 数据更新：2024-05-16 10:35:12</div></div>;
}
function CandleVolumeChart({ values, volumes, large = false }: { values: number[]; volumes: number[]; large?: boolean }) {
  const height = large ? 190 : 110;
  const maxVolume = Math.max(...volumes);
  return <svg className={large ? "candle-chart large" : "candle-chart"} viewBox={`0 0 284 ${height}`} role="img" aria-label="行情历史图"><polyline points={linePoints(values, 260, height - 34, 12, 10)} fill="none" stroke="#4c8bff" strokeWidth="2" strokeLinecap="round" />{volumes.map((volume, index) => { const width = 180 / volumes.length; const barHeight = (volume / maxVolume) * 26; return <rect key={`${volume}-${index}`} x={18 + index * width} y={height - 10 - barHeight} width={Math.max(width - 3, 4)} height={barHeight} rx="1.5" fill="#2cd6b3" opacity="0.7" />; })}</svg>;
}
function linePoints(values: number[], width: number, height: number, offsetX = 0, offsetY = 0): string {
  if (values.length === 0) return "";
  const min = Math.min(...values); const max = Math.max(...values); const span = max - min || 1;
  return values.map((value, index) => { const x = offsetX + (index / Math.max(values.length - 1, 1)) * width; const y = offsetY + height - ((value - min) / span) * height; return `${x.toFixed(2)},${y.toFixed(2)}`; }).join(" ");
}
function RawJson({ data }: { data: Record<string, unknown> }) {
  return <details className="raw-json"><summary>查看原始 JSON</summary><pre>{JSON.stringify(data, null, 2)}</pre></details>;
}
function viewTabDescription(tab: string): string {
  return { 账号详情: "资产、持仓、绩效、成本和贡献", 交易历史: "按账号、Session、模型和股票筛选", 资产曲线: "多账号曲线与基准对比", 股票信息: "临时行情、K线、公告和观察列表", 决策日志: "完整 messages、reasoning 与工具链", 时间线控制: "全局跳转、暂停、加速和覆盖重跑" }[tab] ?? "查看子页面";
}
function manageIcon(section: string) {
  if (section === "模型与API") return <KeyRound size={15} />;
  if (section === "Skills") return <Bot size={15} />;
  if (section === "Tools") return <Wrench size={15} />;
  if (section === "触发器") return <Bell size={15} />;
  if (section === "数据管理") return <Database size={15} />;
  return <Settings size={15} />;
}
function demoToolSchemas(): ToolSchema[] {
  return [
    { name: "market.quote", display_name: "价格查询", description: "读取 A 股实时价格", parameters: {}, strict: true },
    { name: "market.history", display_name: "历史行情", description: "读取 K 线、分钟线和成交量", parameters: {}, strict: true },
    { name: "tavily.search", display_name: "网页搜索", description: "搜索公告、新闻和研报", parameters: {}, strict: false },
    { name: "order.buy", display_name: "买入", description: "提交模拟买入订单", parameters: {}, strict: true },
    { name: "order.sell", display_name: "卖出", description: "提交模拟卖出订单", parameters: {}, strict: true },
    { name: "portfolio.state", display_name: "账户状态", description: "读取现金、持仓和收益", parameters: {}, strict: true }
  ];
}
