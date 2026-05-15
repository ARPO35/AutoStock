import { useEffect } from "react";
import { Clock } from "lucide-react";
import { useDataStore } from "@/stores/dataStore";
import { useTradeStore } from "@/stores/tradeStore";

export function SessionHeader() {
  const accounts = useDataStore((s) => s.accounts);
  const sessions = useDataStore((s) => s.sessions);
  const selectedSessionId = useTradeStore((s) => s.selectedSessionId);
  const replayClocks = useTradeStore((s) => s.replayClocks);
  const loadReplayClock = useTradeStore((s) => s.loadReplayClock);
  const refreshReplayClock = useTradeStore((s) => s.refreshReplayClock);

  const selectedSession = sessions.find((s) => s.id === selectedSessionId) ?? null;
  const selectedAccount = selectedSession?.simulator_account_id
    ? accounts.find((a) => a.id === selectedSession.simulator_account_id) ?? null
    : null;
  const accountId = selectedAccount?.id ?? "";
  const replayClock = accountId ? replayClocks[accountId] : null;
  const displayEffectiveTime = replayClock?.effective_time ?? "";

  useEffect(() => {
    if (accountId) void loadReplayClock(accountId);
  }, [accountId, loadReplayClock]);

  useEffect(() => {
    if (!accountId) return;
    const timer = window.setInterval(() => {
      void refreshReplayClock(accountId);
    }, 1000);
    return () => window.clearInterval(timer);
  }, [accountId, refreshReplayClock]);

  return (
    <header className="flex items-center justify-between gap-4 border-b border-hairline bg-surface-canvas px-4 py-3">
      <div className="min-w-0">
        <p className="mb-1 text-xs font-bold tracking-wide text-brand-primary">
          LLM Linear Flow
        </p>
        <h1 className="truncate text-lg font-semibold text-text-on-dark">
          {selectedSession?.name ?? "No session"}
        </h1>
      </div>

      <div className="ml-auto flex min-w-0 items-center justify-end gap-2 text-right text-xs text-text-muted">
        <Clock size={14} className="shrink-0 text-text-muted" />
        <span className="truncate font-mono">
          {accountId
            ? (displayEffectiveTime ? formatClock(displayEffectiveTime) : "Loading account time")
            : "No account time"}
        </span>
      </div>
    </header>
  );
}

function formatClock(value: string): string {
  return value.replace("T", " ").slice(0, 19);
}
