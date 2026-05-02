import { Play, StopCircle, Bell, SlidersHorizontal } from "lucide-react";
import { useDataStore } from "@/stores/dataStore";
import { useTradeStore } from "@/stores/tradeStore";
import { Badge } from "@/components/ui/Shared";
import { statusLabel, normalizeStatus } from "@/lib/utils";
import { api } from "@/api";
import type { SessionStatus } from "@/types";

export function SessionHeader() {
  const accounts = useDataStore((s) => s.accounts);
  const sessions = useDataStore((s) => s.sessions);
  const providers = useDataStore((s) => s.providers);
  const loadSessions = useDataStore((s) => s.loadSessions);
  const selectedSessionId = useTradeStore((s) => s.selectedSessionId);
  const busy = useTradeStore((s) => s.busy);
  const runOnce = useTradeStore((s) => s.runOnce);

  const selectedSession = sessions.find((s) => s.id === selectedSessionId) ?? null;
  const selectedAccount = selectedSession?.llm_account_id
    ? accounts.find((a) => a.id === selectedSession.llm_account_id) ?? null
    : null;
  const selectedProvider = selectedSession?.provider_id
    ? providers.find((p) => p.id === selectedSession.provider_id) ?? null
    : null;

  const status: SessionStatus = normalizeStatus(selectedSession?.status);
  const statusVariant = status === "running" ? "running" : status === "error" ? "error" : status === "queued" ? "queued" : "default";

  const handleProviderChange = async (providerId: string) => {
    if (!selectedSessionId) return;
    const provider = providerId ? providers.find((p) => p.id === providerId) : null;
    try {
      await api.updateSession(selectedSessionId, {
        provider_id: providerId || null,
        model: provider?.model ?? null
      });
      await loadSessions();
    } catch {
      // 由 store 处理
    }
  };

  const handleModelChange = async (model: string) => {
    if (!selectedSessionId) return;
    try {
      await api.updateSession(selectedSessionId, { model: model || null });
      await loadSessions();
    } catch {
      // 由 store 处理
    }
  };

  return (
    <header className="flex items-center justify-between gap-3.5 px-4 py-3 border-b border-hairline bg-surface-canvas/50">
      <div className="min-w-0">
        <p className="text-brand-primary text-xs font-bold tracking-wide mb-1">
          LLM Linear Flow
        </p>
        <h1 className="text-lg font-semibold text-text-on-dark truncate">
          {selectedSession?.name ?? "暂无会话"}
        </h1>
        {/* 模型选择器 */}
        {selectedSessionId && (
          <div className="flex items-center gap-2 mt-2 flex-wrap">
            <select
              className="h-8 px-2 rounded-lg bg-surface-card border border-hairline text-text-on-dark text-xs focus:border-info focus:ring-2 focus:ring-info/50 min-w-[130px]"
              value={selectedSession?.provider_id ?? ""}
              onChange={(e) => handleProviderChange(e.target.value)}
              disabled={busy}
            >
              <option value="">选择 Provider</option>
              {providers.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
            <input
              className="h-8 px-2 rounded-lg bg-surface-card border border-hairline text-text-on-dark text-xs focus:border-info focus:ring-2 focus:ring-info/50 placeholder:text-text-muted min-w-[120px]"
              value={selectedSession?.model ?? selectedProvider?.model ?? ""}
              onChange={(e) => handleModelChange(e.target.value)}
              placeholder="模型名称"
              disabled={busy}
              onBlur={(e) => handleModelChange(e.target.value)}
            />
          </div>
        )}
        <div className="flex flex-wrap gap-1.5 mt-2">
          <span className="px-2 py-0.5 border border-hairline rounded-full bg-surface-elevated text-text-muted text-xs">
            账户：{selectedAccount?.name ?? "--"}
          </span>
          <span className="px-2 py-0.5 border border-hairline rounded-full bg-surface-elevated text-text-muted text-xs">
            Skill：{selectedSession?.skill_id ?? "--"}
          </span>
          <span className="px-2 py-0.5 border border-hairline rounded-full bg-surface-elevated text-text-muted text-xs">
            模式：实时
          </span>
          <Badge variant={statusVariant}>
            {statusLabel(status)}
          </Badge>
        </div>
      </div>
      <div className="flex items-center gap-2 flex-shrink-0">
        <button
          className="inline-flex items-center gap-1.5 h-9 px-3 rounded-lg border border-hairline bg-surface-card text-text-on-dark text-sm hover:bg-surface-elevated disabled:opacity-50 transition-colors"
          type="button"
          disabled={!selectedSessionId || busy || !selectedSession?.provider_id}
          onClick={() => selectedSessionId && runOnce(selectedSessionId)}
        >
          <Play size={15} />
          运行一次
        </button>
        <button
          className="inline-flex items-center gap-1.5 h-9 px-3 rounded-lg border border-hairline bg-surface-card text-text-on-dark text-sm transition-colors"
          type="button"
          disabled
          title="后端尚未提供停止当前 run 的接口"
        >
          <StopCircle size={15} />
          停止
        </button>
        <button
          className="inline-flex items-center gap-1.5 h-9 px-3 rounded-lg border border-hairline bg-surface-card text-text-on-dark text-sm transition-colors"
          type="button"
          disabled
          title="后端尚未接入触发器接口"
        >
          <Bell size={15} />
          触发器
        </button>
        <button
          className="inline-flex items-center gap-1.5 h-9 px-3 rounded-lg border border-hairline bg-surface-card text-text-on-dark text-sm transition-colors"
          type="button"
          disabled
          title="后端尚未提供 Session 配置修改接口"
        >
          <SlidersHorizontal size={15} />
          修改配置
        </button>
      </div>
    </header>
  );
}
