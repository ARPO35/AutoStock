import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { ArrowLeft, Bell, CalendarDays, Check, Clock, FileText, SlidersHorizontal, X } from "lucide-react";
import { api } from "@/api";
import { useDataStore } from "@/stores/dataStore";
import { useTradeStore } from "@/stores/tradeStore";
import { providerModelOptions, resolveModelSelection } from "@/lib/providerModels";

type ConfigPage = "menu" | "models" | "prompt" | "time" | "triggers";

interface TradeConfigPopoverProps {
  open: boolean;
  onClose: () => void;
}

export function TradeConfigPopover({ open, onClose }: TradeConfigPopoverProps) {
  const accounts = useDataStore((s) => s.accounts);
  const sessions = useDataStore((s) => s.sessions);
  const providers = useDataStore((s) => s.providers);
  const promptRoles = useDataStore((s) => s.promptRoles);
  const loadSessions = useDataStore((s) => s.loadSessions);
  const selectedSessionId = useTradeStore((s) => s.selectedSessionId);
  const busy = useTradeStore((s) => s.busy);
  const replayClocks = useTradeStore((s) => s.replayClocks);
  const replayClockLoading = useTradeStore((s) => s.replayClockLoading);
  const replayClockError = useTradeStore((s) => s.replayClockError);
  const updateReplayClock = useTradeStore((s) => s.updateReplayClock);
  const restoreReplayClockLive = useTradeStore((s) => s.restoreReplayClockLive);
  const [page, setPage] = useState<ConfigPage>("menu");
  const [replayDraft, setReplayDraft] = useState("");
  const [speedDraft, setSpeedDraft] = useState("1");
  const replayInputRef = useRef<HTMLInputElement | null>(null);

  const selectedSession = sessions.find((s) => s.id === selectedSessionId) ?? null;
  const selectedAccount = selectedSession?.simulator_account_id
    ? accounts.find((a) => a.id === selectedSession.simulator_account_id) ?? null
    : null;
  const selectedModelOptions = providerModelOptions(providers);
  const selectedModelValue = selectedSession
    ? resolveModelSelection(providers, selectedSession.model, selectedSession.provider_id)?.value ?? ""
    : "";
  const accountId = selectedAccount?.id ?? "";
  const replayClock = accountId ? replayClocks[accountId] : null;

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  useEffect(() => {
    if (!open) setPage("menu");
  }, [open]);

  useEffect(() => {
    if (!replayClock) {
      setReplayDraft("");
      setSpeedDraft("1");
      return;
    }
    setReplayDraft(toDatetimeLocal(replayClock.effective_time));
    setSpeedDraft(String(replayClock.speed ?? 1));
  }, [replayClock?.account_id, replayClock?.effective_time, replayClock?.speed]);

  if (!open) return null;

  const updateSession = async (payload: Record<string, unknown>) => {
    if (!selectedSessionId) return;
    await api.updateSession(selectedSessionId, payload);
    await loadSessions();
  };

  const applyReplay = async () => {
    if (!accountId || !replayDraft) return;
    await updateReplayClock(accountId, {
      mode: "replay",
      replay_time: replayDraft,
      speed: Number(speedDraft) >= 0 ? Number(speedDraft) : 1,
    });
  };

  const openReplayPicker = () => {
    const input = replayInputRef.current;
    if (!input) return;
    if (typeof input.showPicker === "function") {
      input.showPicker();
      return;
    }
    input.focus();
  };

  const headerTitle = {
    menu: "配置",
    models: "模型",
    prompt: "Prompt 配置",
    time: "时间控制",
    triggers: "事件触发配置",
  }[page];

  return (
    <div className="absolute bottom-[58px] right-0 z-30 w-[360px] max-w-[calc(100vw-32px)] animate-fade-in rounded-xl border border-hairline bg-surface-card p-3 shadow-2xl">
      <header className="mb-3 flex items-center justify-between gap-2 border-b border-hairline pb-2">
        <button
          type="button"
          className="grid h-8 w-8 place-items-center rounded-full text-text-muted transition-colors hover:bg-surface-elevated hover:text-text-on-dark"
          onClick={() => page === "menu" ? onClose() : setPage("menu")}
          title={page === "menu" ? "关闭" : "返回"}
        >
          {page === "menu" ? <X size={16} /> : <ArrowLeft size={16} />}
        </button>
        <strong className="min-w-0 flex-1 truncate text-sm text-text-on-dark">{headerTitle}</strong>
      </header>

      {page === "menu" && (
        <div className="grid gap-2">
          <ConfigMenuButton icon={<SlidersHorizontal size={16} />} label="模型" onClick={() => setPage("models")} />
          <ConfigMenuButton icon={<FileText size={16} />} label="配置" onClick={() => setPage("prompt")} />
          <ConfigMenuButton icon={<Clock size={16} />} label="时间控制" onClick={() => setPage("time")} />
          <ConfigMenuButton icon={<Bell size={16} />} label="事件触发配置" onClick={() => setPage("triggers")} />
        </div>
      )}

      {page === "models" && (
        <div className="grid max-h-[320px] gap-1.5 overflow-y-auto">
          {selectedModelOptions.length === 0 && (
            <p className="text-sm text-text-muted">暂无可用模型列表，请先在管理页配置 Provider 模型。</p>
          )}
          {selectedModelOptions.map((option) => (
            <button
              key={option.value}
              type="button"
              disabled={busy}
              onClick={() => updateSession({ model: option.value, provider_id: option.providerId })}
              className="flex min-h-10 items-center justify-between gap-2 rounded-lg border border-hairline bg-surface-canvas px-3 py-2 text-left text-sm text-text-body transition-colors hover:border-brand-primary/60 hover:bg-brand-primary/5 disabled:opacity-50"
            >
              <span className="min-w-0 truncate">{option.label}</span>
              {selectedModelValue === option.value && <Check size={15} className="shrink-0 text-brand-primary" />}
            </button>
          ))}
        </div>
      )}

      {page === "prompt" && (
        <div className="grid max-h-[320px] gap-1.5 overflow-y-auto">
          {promptRoles.length === 0 && <p className="text-sm text-text-muted">暂无 Prompt 配置。</p>}
          {promptRoles.map((role) => {
            const selected = (selectedSession?.prompt_role_id ?? "default") === role.id;
            return (
              <button
                key={role.id}
                type="button"
                disabled={busy}
                onClick={() => updateSession({ prompt_role_id: role.id })}
                className="flex min-h-10 items-center justify-between gap-2 rounded-lg border border-hairline bg-surface-canvas px-3 py-2 text-left text-sm text-text-body transition-colors hover:border-brand-primary/60 hover:bg-brand-primary/5 disabled:opacity-50"
              >
                <span className="min-w-0 truncate">{role.name}</span>
                {selected && <Check size={15} className="shrink-0 text-brand-primary" />}
              </button>
            );
          })}
        </div>
      )}

      {page === "time" && (
        <div className="grid gap-3">
          <div className="rounded-lg border border-hairline bg-surface-canvas p-3 text-xs text-text-muted">
            当前账户时间：
            <span className="ml-1 font-mono text-text-muted-strong">
              {replayClock?.effective_time ? formatClock(replayClock.effective_time) : "未选择账户"}
            </span>
          </div>
          <label className="grid gap-1.5 text-xs text-text-muted">
            回放时间
            <div className="grid grid-cols-[minmax(0,1fr)_40px] gap-2">
              <input
                ref={replayInputRef}
                className="h-10 rounded-lg border border-hairline bg-surface-canvas px-3 text-sm text-text-on-dark focus:border-info focus:ring-2 focus:ring-info/50 disabled:opacity-50"
                type="datetime-local"
                value={replayDraft}
                disabled={!accountId || replayClockLoading || busy}
                onChange={(event) => setReplayDraft(event.target.value)}
              />
              <button
                type="button"
                className="grid h-10 w-10 place-items-center rounded-lg border border-hairline bg-surface-canvas text-text-muted transition-colors hover:border-info/60 hover:text-info disabled:opacity-50"
                disabled={!accountId || replayClockLoading || busy}
                onClick={openReplayPicker}
                title="选择回放时间"
              >
                <CalendarDays size={15} />
              </button>
            </div>
          </label>
          <label className="grid gap-1.5 text-xs text-text-muted">
            速度
            <select
              className="h-10 rounded-lg border border-hairline bg-surface-canvas px-3 text-sm text-text-on-dark focus:border-info focus:ring-2 focus:ring-info/50 disabled:opacity-50"
              value={speedDraft}
              disabled={!accountId || replayClockLoading || busy}
              onChange={(event) => setSpeedDraft(event.target.value)}
            >
              <option value="0">0x</option>
              <option value="0.5">0.5x</option>
              <option value="1">1x</option>
              <option value="2">2x</option>
              <option value="5">5x</option>
              <option value="10">10x</option>
            </select>
          </label>
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              disabled={!accountId || !replayDraft || replayClockLoading || busy}
              onClick={applyReplay}
              className="h-10 rounded-md bg-brand-primary px-3 text-sm font-semibold text-brand-ink transition-colors hover:bg-brand-primary-active disabled:opacity-50"
            >
              应用回放
            </button>
            <button
              type="button"
              disabled={!accountId || replayClockLoading || busy}
              onClick={() => accountId && restoreReplayClockLive(accountId)}
              className="h-10 rounded-md border border-hairline bg-surface-canvas px-3 text-sm text-text-on-dark transition-colors hover:bg-surface-elevated disabled:opacity-50"
            >
              恢复实时
            </button>
          </div>
          {replayClockError && <p className="text-xs text-trading-rise">{replayClockError}</p>}
        </div>
      )}

      {page === "triggers" && (
        <div className="rounded-lg border border-dashed border-hairline bg-surface-canvas p-4 text-sm text-text-muted">
          事件触发配置将在触发器工具接入后显示。
        </div>
      )}
    </div>
  );
}

function ConfigMenuButton({
  icon,
  label,
  onClick,
}: {
  icon: ReactNode;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex h-11 items-center gap-3 rounded-lg border border-hairline bg-surface-canvas px-3 text-left text-sm text-text-body transition-colors hover:border-brand-primary/60 hover:bg-brand-primary/5 hover:text-text-on-dark"
    >
      <span className="grid h-7 w-7 place-items-center rounded-full bg-surface-elevated text-brand-primary">
        {icon}
      </span>
      {label}
    </button>
  );
}

function toDatetimeLocal(value: string | null | undefined): string {
  if (!value) return "";
  return value.replace(" ", "T").slice(0, 16);
}

function formatClock(value: string): string {
  return value.replace("T", " ").slice(0, 19);
}
