import { Activity, Bot, KeyRound, Plus, RefreshCw, Send, Wrench } from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { Account, Message, Provider, RuntimeEvent, Session, ToolSchema, api } from "./api";

const defaultProvider = {
  provider_type: "deepseek",
  name: "DeepSeek V4 Flash",
  base_url: "",
  api_key: "",
  model: "deepseek-v4-flash"
};

export default function App() {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [tools, setTools] = useState<ToolSchema[]>([]);
  const [events, setEvents] = useState<RuntimeEvent[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState<string>("");
  const [providerForm, setProviderForm] = useState(defaultProvider);
  const [accountName, setAccountName] = useState("Primary Trader");
  const [sessionName, setSessionName] = useState("Market Session");
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedSession = useMemo(
    () => sessions.find((session) => session.id === selectedSessionId) ?? null,
    [selectedSessionId, sessions]
  );

  const selectedAccount = useMemo(
    () => accounts.find((account) => account.id === selectedSession?.llm_account_id) ?? null,
    [accounts, selectedSession]
  );

  const selectedProvider = useMemo(
    () => providers.find((provider) => provider.id === selectedAccount?.provider_id) ?? null,
    [providers, selectedAccount]
  );

  useEffect(() => {
    void loadAll();
  }, []);

  useEffect(() => {
    if (!selectedSessionId && sessions.length > 0) {
      setSelectedSessionId(sessions[0].id);
    }
  }, [selectedSessionId, sessions]);

  useEffect(() => {
    if (!selectedSessionId) {
      setMessages([]);
      setEvents([]);
      return;
    }
    void loadMessages(selectedSessionId);

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const socket = new WebSocket(`${protocol}//${window.location.host}/ws/sessions/${selectedSessionId}`);
    socket.onmessage = (event) => {
      const payload = JSON.parse(event.data) as RuntimeEvent;
      setEvents((current) => [payload, ...current].slice(0, 40));
      if (payload.type === "assistant_message" || payload.type === "run_finished") {
        void loadMessages(selectedSessionId);
        void loadSessions();
      }
    };
    socket.onerror = () => setError("WebSocket connection failed.");
    return () => socket.close();
  }, [selectedSessionId]);

  async function loadAll() {
    setError(null);
    try {
      const [nextProviders, nextAccounts, nextSessions, nextTools] = await Promise.all([
        api.providers(),
        api.accounts(),
        api.sessions(),
        api.tools()
      ]);
      setProviders(nextProviders);
      setAccounts(nextAccounts);
      setSessions(nextSessions);
      setTools(nextTools);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load app state.");
    }
  }

  async function loadSessions() {
    const nextSessions = await api.sessions();
    setSessions(nextSessions);
  }

  async function loadMessages(sessionId: string) {
    const nextMessages = await api.messages(sessionId);
    setMessages(nextMessages);
  }

  async function createProvider(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const created = await api.createProvider({
        provider_type: providerForm.provider_type,
        name: providerForm.name,
        base_url: providerForm.base_url || null,
        api_key: providerForm.api_key,
        model: providerForm.model,
        supports_tools: true,
        supports_strict_schema: false,
        strict_tool_schema: false
      });
      setProviders((current) => [created, ...current]);
      setProviderForm({ ...defaultProvider, api_key: "" });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create provider.");
    } finally {
      setBusy(false);
    }
  }

  async function createAccount(event: FormEvent) {
    event.preventDefault();
    if (!providers[0]) return;
    setBusy(true);
    setError(null);
    try {
      const created = await api.createAccount({
        name: accountName,
        provider_id: providers[0].id,
        initial_cash: 1000000
      });
      setAccounts((current) => [created, ...current]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create account.");
    } finally {
      setBusy(false);
    }
  }

  async function createSession(event: FormEvent) {
    event.preventDefault();
    if (!accounts[0]) return;
    setBusy(true);
    setError(null);
    try {
      const created = await api.createSession({
        name: sessionName,
        llm_account_id: accounts[0].id
      });
      setSessions((current) => [created, ...current]);
      setSelectedSessionId(created.id);
      setEvents([]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create session.");
    } finally {
      setBusy(false);
    }
  }

  async function sendMessage(event: FormEvent) {
    event.preventDefault();
    if (!selectedSession || !draft.trim()) return;
    const message = draft.trim();
    setDraft("");
    setBusy(true);
    setError(null);
    try {
      await api.runSession(selectedSession.id, { message, max_tool_rounds: 5 });
      await loadMessages(selectedSession.id);
      await loadSessions();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to run session.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="workspace">
      <aside className="sidebar" aria-label="Sessions">
        <div className="brand">
          <Activity size={22} />
          <div>
            <strong>AutoStock</strong>
            <span>MVP WebChat</span>
          </div>
        </div>

        <form className="stack" onSubmit={createSession}>
          <label>
            <span>New session</span>
            <input value={sessionName} onChange={(event) => setSessionName(event.target.value)} />
          </label>
          <button type="submit" disabled={busy || accounts.length === 0} title="Create session">
            <Plus size={16} />
            Create
          </button>
        </form>

        <nav className="session-list">
          {sessions.map((session) => (
            <button
              className={session.id === selectedSessionId ? "session-row active" : "session-row"}
              key={session.id}
              onClick={() => setSelectedSessionId(session.id)}
            >
              <span>{session.name}</span>
              <small>{session.status}</small>
            </button>
          ))}
        </nav>
      </aside>

      <section className="chat-pane">
        <header className="topbar">
          <div>
            <p className="eyebrow">Session</p>
            <h1>{selectedSession?.name ?? "No session selected"}</h1>
          </div>
          <button className="icon-button" onClick={() => void loadAll()} title="Refresh">
            <RefreshCw size={17} />
          </button>
        </header>

        {error && <div className="error-line">{error}</div>}

        <div className="message-stream">
          {messages.length === 0 && (
            <div className="empty-state">
              <Bot size={24} />
              <span>Create a provider, account, and session, then send the first message.</span>
            </div>
          )}
          {messages.map((message) => (
            <article className={`message ${message.role}`} key={message.id}>
              <header>
                <span>{message.role}</span>
                <small>{message.message_type}</small>
              </header>
              <p>{message.content || "(tool call)"}</p>
            </article>
          ))}
        </div>

        <form className="composer" onSubmit={sendMessage}>
          <textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="Ask the trading agent to inspect tools, call echo, or respond."
            rows={3}
          />
          <button type="submit" disabled={busy || !selectedSession || !draft.trim()} title="Send message">
            <Send size={18} />
          </button>
        </form>
      </section>

      <aside className="inspector" aria-label="Configuration">
        <section>
          <div className="section-title">
            <KeyRound size={17} />
            <h2>Provider</h2>
          </div>
          <form className="stack" onSubmit={createProvider}>
            <select
              value={providerForm.provider_type}
              onChange={(event) =>
                setProviderForm({ ...providerForm, provider_type: event.target.value })
              }
            >
              <option value="deepseek">DeepSeek</option>
              <option value="openai_compatible">OpenAI-compatible</option>
            </select>
            <input
              value={providerForm.name}
              onChange={(event) => setProviderForm({ ...providerForm, name: event.target.value })}
              placeholder="Name"
            />
            <input
              value={providerForm.model}
              onChange={(event) => setProviderForm({ ...providerForm, model: event.target.value })}
              placeholder="Model"
            />
            <input
              value={providerForm.base_url}
              onChange={(event) => setProviderForm({ ...providerForm, base_url: event.target.value })}
              placeholder="Base URL optional"
            />
            <input
              value={providerForm.api_key}
              onChange={(event) => setProviderForm({ ...providerForm, api_key: event.target.value })}
              placeholder="API key"
              type="password"
            />
            <button type="submit" disabled={busy || !providerForm.api_key}>
              <Plus size={16} />
              Add provider
            </button>
          </form>
          <StatusLine label="Active" value={selectedProvider?.name ?? providers[0]?.name ?? "None"} />
        </section>

        <section>
          <div className="section-title">
            <Bot size={17} />
            <h2>Account</h2>
          </div>
          <form className="stack inline" onSubmit={createAccount}>
            <input value={accountName} onChange={(event) => setAccountName(event.target.value)} />
            <button type="submit" disabled={busy || providers.length === 0} title="Create account">
              <Plus size={16} />
            </button>
          </form>
          <StatusLine label="Bound" value={selectedAccount?.name ?? accounts[0]?.name ?? "None"} />
        </section>

        <section>
          <div className="section-title">
            <Wrench size={17} />
            <h2>Tools</h2>
          </div>
          <div className="tool-list">
            {tools.map((tool) => (
              <div className="tool-row" key={tool.name}>
                <strong>{tool.display_name}</strong>
                <span>{tool.strict ? "strict schema" : "best effort"}</span>
              </div>
            ))}
          </div>
        </section>

        <section className="events">
          <div className="section-title">
            <Activity size={17} />
            <h2>Runtime</h2>
          </div>
          {events.length === 0 && <p className="muted">No runtime events yet.</p>}
          {events.map((event, index) => (
            <div className="event-row" key={`${event.type}-${event.run_id}-${index}`}>
              <span>{event.type}</span>
              <small>{event.tool_name ?? event.status ?? event.error ?? event.run_id}</small>
            </div>
          ))}
        </section>
      </aside>
    </main>
  );
}

function StatusLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="status-line">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
