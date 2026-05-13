import { useEffect, useMemo, useState } from "react";
import { Bell, Clock, PauseCircle, Play, RotateCcw, SlidersHorizontal, StopCircle } from "lucide-react";
import { useDataStore } from "@/stores/dataStore";
import { useTradeStore } from "@/stores/tradeStore";
import { Badge } from "@/components/ui/Shared";
import { normalizeStatus, statusLabel } from "@/lib/utils";
import { api } from "@/api";
import type { SessionStatus } from "@/types";

export function SessionHeader() {
  const accounts = useDataStore((s) => s.accounts);
  const sessions = useDataStore((s) => s.sessions);
  const providers = useDataStore((s) => s.providers);
  const promptRoles = useDataStore((s) => s.promptRoles);
  const loadSessions = useDataStore((s) => s.loadSessions);
  const selectedSessionId = useTradeStore((s) => s.selectedSessionId);
  const busy = useTradeStore((s) => s.busy);
  const runOnce = useTradeStore((s) => s.runOnce);
  const stopCurrentRun = useTradeStore((s) => s.stopCurrentRun);
  const replayClocks = useTradeStore((s) => s.replayClocks);
  const replayClockLoading = useTradeStore((s) => s.replayClockLoading);
  const replayClockError = useTradeStore((s) => s.replayClockError);
  const loadReplayClock = useTradeStore((s) => s.loadReplayClock);
  const updateReplayClock = useTradeStore((s) => s.updateReplayClock);
  const restoreReplayClockLive = useTradeStore((s) => s.restoreReplayClockLive);
  const [replayDraft, setReplayDraft] = useState("");
  const [speedDraft, setSpeedDraft] = useState("1");
  const [editingReplayTime, setEditingReplayTime] = useState(false);
  const [clockTick, setClockTick] = useState(() => Date.now());

  const selectedSession = sessions.find((s) => s.id === selectedSessionId) ?? null;
  const selectedAccount = selectedSession?.simulator_account_id
    ? accounts.find((a) => a.id === selectedSession.simulator_account_id) ?? null
    : null;
  const selectedProvider = selectedSession?.provider_id
    ? providers.find((p) => p.id === selectedSession.provider_id) ?? null
    : null;
  const selectedPromptRole = selectedSession?.prompt_role_id
    ? promptRoles.find((role) => role.id === selectedSession.prompt_role_id) ?? null
    : promptRoles[0] ?? null;
  const accountId = selectedAccount?.id ?? "";
  const replayClock = accountId ? replayClocks[accountId] : null;
  const displayEffectiveTime = useMemo(
    () => deriveDisplayEffectiveTime(replayClock, clockTick),
    [replayClock, clockTick]
  );

  useEffect(() => {
    if (accountId) void loadReplayClock(accountId);
  }, [accountId, loadReplayClock]);

  useEffect(() => {
    const timer = window.setInterval(() => setClockTick(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!replayClock) {
      setReplayDraft("");
      setSpeedDraft("1");
      return;
    }
    setSpeedDraft(String(replayClock.speed ?? 1));
  }, [replayClock?.account_id, replayClock?.speed, replayClock?.updated_at]);

  useEffect(() => {
    if (!replayClock) return;
    if (!editingReplayTime) {
      setReplayDraft(toDatetimeLocal(displayEffectiveTime));
    }
  }, [displayEffectiveTime, editingReplayTime, replayClock]);

  const status: SessionStatus = normalizeStatus(selectedSession?.status);
  const statusVariant = status === "running"
    ? "running"
    : status === "error"
      ? "error"
      : status === "queued"
        ? "queued"
        : status === "cancelled"
          ? "cancelled"
          : "default";

  const handleProviderChange = async (providerId: string) => {
    if (!selectedSessionId) return;
    const provider = providerId ? providers.find((p) => p.id === providerId) : null;
    try {
      await api.updateSession(selectedSessionId, {
        provider_id: providerId || null,
        model: provider?.model ?? null,
      });
      await loadSessions();
    } catch {
      // Store-level errors are surfaced elsewhere.
    }
  };

  const handleModelChange = async (model: string) => {
    if (!selectedSessionId) return;
    try {
      await api.updateSession(selectedSessionId, { model: model || null });
      await loadSessions();
    } catch {
      // Store-level errors are surfaced elsewhere.
    }
  };

  const handlePromptRoleChange = async (promptRoleId: string) => {
    if (!selectedSessionId) return;
    try {
      await api.updateSession(selectedSessionId, { prompt_role_id: promptRoleId || "default" });
      await loadSessions();
    } catch {
      // Store-level errors are surfaced elsewhere.
    }
  };

  const handleApplyReplay = async () => {
    if (!accountId || !replayDraft) return;
    await updateReplayClock(accountId, {
      mode: "replay",
      replay_time: replayDraft,
      speed: Number(speedDraft) >= 0 ? Number(speedDraft) : 1,
    });
  };

  const handlePauseResume = async () => {
    if (!accountId) return;
    const current = replayClock?.mode === "replay"
      ? replayClock.effective_time
      : new Date().toISOString();
    if (replayClock?.mode === "replay" && replayClock.speed === 0) {
      await updateReplayClock(accountId, {
        mode: "replay",
        replay_time: current,
        speed: Number(speedDraft) > 0 ? Number(speedDraft) : 1,
      });
      return;
    }
    await updateReplayClock(accountId, {
      mode: "replay",
      replay_time: current,
      speed: 0,
    });
  };

  return (
    <header className="flex items-center justify-between gap-3.5 px-4 py-3 border-b border-hairline bg-surface-canvas/50">
      <div className="min-w-0">
        <p className="text-brand-primary text-xs font-bold tracking-wide mb-1">
          LLM Linear Flow
        </p>
        <h1 className="text-lg font-semibold text-text-on-dark truncate">
          {selectedSession?.name ?? "No session"}
        </h1>
        {selectedSessionId && (
          <div className="flex items-center gap-2 mt-2 flex-wrap">
            <select
              className="h-8 px-2 rounded-lg bg-surface-card border border-hairline text-text-on-dark text-xs focus:border-info focus:ring-2 focus:ring-info/50 min-w-[130px]"
              value={selectedSession?.provider_id ?? ""}
              onChange={(e) => handleProviderChange(e.target.value)}
              disabled={busy}
            >
              <option value="">Provider</option>
              {providers.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
            <input
              className="h-8 px-2 rounded-lg bg-surface-card border border-hairline text-text-on-dark text-xs focus:border-info focus:ring-2 focus:ring-info/50 placeholder:text-text-muted min-w-[120px]"
              value={selectedSession?.model ?? selectedProvider?.model ?? ""}
              onChange={(e) => handleModelChange(e.target.value)}
              placeholder="Model"
              disabled={busy}
              onBlur={(e) => handleModelChange(e.target.value)}
            />
            <select
              className="h-8 px-2 rounded-lg bg-surface-card border border-hairline text-text-on-dark text-xs focus:border-info focus:ring-2 focus:ring-info/50 min-w-[130px]"
              value={selectedSession?.prompt_role_id ?? selectedPromptRole?.id ?? ""}
              onChange={(e) => handlePromptRoleChange(e.target.value)}
              disabled={busy || promptRoles.length === 0}
              title="Prompt role"
            >
              {promptRoles.length === 0 ? (
                <option value="">No prompt role</option>
              ) : (
                promptRoles.map((role) => (
                  <option key={role.id} value={role.id}>{role.name}</option>
                ))
              )}
            </select>
          </div>
        )}
        <div className="flex flex-wrap gap-1.5 mt-2">
          <span className="px-2 py-0.5 border border-hairline rounded-full bg-surface-elevated text-text-muted text-xs">
            Account: {selectedAccount?.name ?? "--"}
          </span>
          <span className="px-2 py-0.5 border border-hairline rounded-full bg-surface-elevated text-text-muted text-xs">
            Skill: {selectedSession?.skill_id ?? "--"}
          </span>
          <span className="px-2 py-0.5 border border-hairline rounded-full bg-surface-elevated text-text-muted text-xs">
            Prompt: {selectedPromptRole?.name ?? "--"}
          </span>
          <span className="px-2 py-0.5 border border-hairline rounded-full bg-surface-elevated text-text-muted text-xs">
            Clock: {replayClock?.mode === "replay" ? `Replay ${replayClock.speed}x` : "Live"}
          </span>
          <Badge variant={statusVariant}>{statusLabel(status)}</Badge>
        </div>
        <div className="flex items-center gap-1.5 mt-2 flex-wrap">
          <span className="inline-flex items-center gap-1 h-8 px-2 rounded-md border border-hairline bg-surface-elevated text-text-muted text-xs">
            <Clock size={13} />
            {accountId ? (displayEffectiveTime ? formatClock(displayEffectiveTime) : "Loading") : "No account"}
          </span>
          <input
            className="h-8 w-[168px] px-2 rounded-md bg-surface-card border border-hairline text-text-on-dark text-xs focus:border-info focus:ring-2 focus:ring-info/50 disabled:opacity-50"
            type="datetime-local"
            value={replayDraft}
            disabled={!accountId || replayClockLoading || busy}
            onFocus={() => setEditingReplayTime(true)}
            onBlur={() => setEditingReplayTime(false)}
            onChange={(e) => setReplayDraft(e.target.value)}
          />
          <select
            className="h-8 w-[76px] px-2 rounded-md bg-surface-card border border-hairline text-text-on-dark text-xs focus:border-info focus:ring-2 focus:ring-info/50 disabled:opacity-50"
            value={speedDraft}
            disabled={!accountId || replayClockLoading || busy}
            onChange={(e) => setSpeedDraft(e.target.value)}
          >
            <option value="0">0x</option>
            <option value="0.5">0.5x</option>
            <option value="1">1x</option>
            <option value="2">2x</option>
            <option value="5">5x</option>
            <option value="10">10x</option>
          </select>
          <button
            className="inline-flex items-center gap-1 h-8 px-2 rounded-md border border-hairline bg-surface-card text-text-on-dark text-xs hover:bg-surface-elevated disabled:opacity-50 transition-colors"
            type="button"
            disabled={!accountId || !replayDraft || replayClockLoading || busy}
            onClick={handleApplyReplay}
          >
            Apply
          </button>
          <button
            className="inline-flex items-center gap-1 h-8 px-2 rounded-md border border-hairline bg-surface-card text-text-on-dark text-xs hover:bg-surface-elevated disabled:opacity-50 transition-colors"
            type="button"
            disabled={!accountId || replayClockLoading || busy}
            onClick={handlePauseResume}
            title={replayClock?.mode === "replay" && replayClock.speed === 0 ? "Resume replay" : "Pause at effective time"}
          >
            {replayClock?.mode === "replay" && replayClock.speed === 0 ? <Play size={13} /> : <PauseCircle size={13} />}
            {replayClock?.mode === "replay" && replayClock.speed === 0 ? "Resume" : "Pause"}
          </button>
          <button
            className="inline-flex items-center gap-1 h-8 px-2 rounded-md border border-hairline bg-surface-card text-text-on-dark text-xs hover:bg-surface-elevated disabled:opacity-50 transition-colors"
            type="button"
            disabled={!accountId || replayClockLoading || busy}
            onClick={() => accountId && restoreReplayClockLive(accountId)}
            title="Restore live clock"
          >
            <RotateCcw size={13} />
            Live
          </button>
          {replayClockError && (
            <span className="text-xs text-trading-rise max-w-[240px] truncate" title={replayClockError}>
              {replayClockError}
            </span>
          )}
        </div>
      </div>
      <div className="flex items-center gap-2 flex-shrink-0">
        <button
          className="inline-flex items-center gap-1.5 h-9 px-3 rounded-lg border border-hairline bg-surface-card text-text-on-dark text-sm hover:bg-surface-elevated disabled:opacity-50 transition-colors"
          type="button"
          disabled={!selectedSessionId || busy || !selectedSession?.provider_id}
          onClick={() => selectedSessionId && runOnce(selectedSessionId, selectedSession?.model)}
        >
          <Play size={15} />
          Run once
        </button>
        <button
          className="inline-flex items-center gap-1.5 h-9 px-3 rounded-lg border border-hairline bg-surface-card text-text-on-dark text-sm transition-colors"
          type="button"
          disabled={!selectedSessionId || !busy}
          onClick={() => selectedSessionId && stopCurrentRun(selectedSessionId)}
          title={busy ? "Stop current run" : "No active run"}
        >
          <StopCircle size={15} />
          Stop
        </button>
        <button
          className="inline-flex items-center gap-1.5 h-9 px-3 rounded-lg border border-hairline bg-surface-card text-text-on-dark text-sm transition-colors"
          type="button"
          disabled
          title="Trigger API is not wired yet"
        >
          <Bell size={15} />
          Trigger
        </button>
        <button
          className="inline-flex items-center gap-1.5 h-9 px-3 rounded-lg border border-hairline bg-surface-card text-text-on-dark text-sm transition-colors"
          type="button"
          disabled
          title="Session configuration editing is not wired yet"
        >
          <SlidersHorizontal size={15} />
          Config
        </button>
      </div>
    </header>
  );
}

function toDatetimeLocal(value: string | null | undefined): string {
  if (!value) return "";
  return value.replace(" ", "T").slice(0, 16);
}

function formatClock(value: string): string {
  return value.replace("T", " ").slice(0, 19);
}

function deriveDisplayEffectiveTime(clock: { mode: string; effective_time: string; updated_at?: string | null; speed: number } | null, tickMs: number): string {
  if (!clock?.effective_time) return "";
  if (clock.mode !== "replay") {
    return isoInChinaTime(tickMs);
  }
  const speed = Number(clock.speed ?? 1);
  if (speed === 0) return clock.effective_time;

  const baseEffective = Date.parse(clock.effective_time);
  const baseUpdated = Date.parse(clock.updated_at || clock.effective_time);
  if (!Number.isFinite(baseEffective) || !Number.isFinite(baseUpdated)) {
    return clock.effective_time;
  }

  const elapsedMs = Math.max(0, tickMs - baseUpdated);
  return isoInChinaTime(baseEffective + elapsedMs * speed);
}

function isoInChinaTime(ms: number): string {
  return `${new Date(ms + 8 * 60 * 60 * 1000).toISOString().slice(0, 19)}+08:00`;
}
