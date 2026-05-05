import { useMemo } from "react";
import {
  ChevronDown,
  Plus,
  Search,
  Trash2,
  Wallet
} from "lucide-react";
import { useDataStore } from "@/stores/dataStore";
import { useTradeStore } from "@/stores/tradeStore";
import { useUIStore } from "@/stores/uiStore";
import { EmptyState } from "@/components/ui/Shared";
import { normalizeStatus, formatMoney } from "@/lib/utils";
import { useState } from "react";

export function AccountSessionSidebar() {
  const accounts = useDataStore((s) => s.accounts);
  const sessions = useDataStore((s) => s.sessions);
  const selectedSessionId = useTradeStore((s) => s.selectedSessionId);
  const setSelectedSessionId = useTradeStore((s) => s.setSelectedSessionId);
  const leftCollapsed = useUIStore((s) => s.leftCollapsed);
  const setLeftCollapsed = useUIStore((s) => s.setLeftCollapsed);

  const createSession = useDataStore((s) => s.createSession);
  const deleteSession = useDataStore((s) => s.deleteSession);

  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);

  const grouped = useMemo(() => {
    return accounts.map((account) => ({
      ...account,
      sessions: sessions
        .filter((s) => s.simulator_account_id === account.id)
        .map((s) => ({
          ...s,
          status: normalizeStatus(s.status)
        }))
    }));
  }, [accounts, sessions]);

  if (leftCollapsed) {
    return (
      <aside className="flex flex-col items-center gap-2.5 py-3 px-2 border-r border-hairline bg-surface-canvas">
        <button
          className="w-9 h-9 grid place-items-center rounded-lg border border-hairline bg-surface-card hover:bg-surface-elevated"
          onClick={() => setLeftCollapsed(false)}
          title="展开账户栏"
        >
          <ChevronDown size={16} className="rotate-[-90deg]" />
        </button>
        {grouped.map((a) => (
          <button
            key={a.id}
            className="w-9 h-9 grid place-items-center rounded-lg border border-hairline bg-surface-card text-text-muted text-sm"
            disabled
          >
            {a.name.slice(0, 1)}
          </button>
        ))}
      </aside>
    );
  }

  return (
    <aside className="flex flex-col gap-2.5 p-3 border-r border-hairline bg-surface-canvas min-w-0 overflow-hidden relative">
      {/* Header */}
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold text-brand-primary tracking-wide mb-1">账户与会话</p>
          <h2 className="text-base font-semibold text-text-on-dark">Account Tree</h2>
        </div>
        <button
          className="w-8 h-8 grid place-items-center rounded-lg border border-hairline hover:bg-surface-elevated"
          onClick={() => setLeftCollapsed(true)}
          title="折叠"
        >
          <ChevronDown size={15} className="rotate-90" />
        </button>
      </div>

      {/* Search */}
      <div className="relative">
        <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-text-muted" />
        <input
          className="w-full h-8 pl-8 pr-3 rounded-lg bg-surface-card border border-hairline text-text-on-dark text-sm placeholder:text-text-muted"
          placeholder="搜索"
          disabled
        />
      </div>

      {/* Account Tree */}
      <div className="flex-1 min-h-0 overflow-auto">
        {grouped.length === 0 ? (
          <EmptyState title="暂无账户" description="请先在管理页配置 Provider，然后在修改页创建账户。" />
        ) : (
          grouped.map((account) => (
            <details className="border-t border-hairline py-2.5" key={account.id} open>
              <summary className="flex items-center justify-between gap-2 cursor-pointer list-none">
                <span className="inline-flex items-center gap-1.5 text-text-on-dark font-semibold text-sm">
                  <Wallet size={14} />
                  {account.name}
                </span>
                <span className="inline-flex items-center gap-1.5 text-text-muted text-xs">
                  {account.sessions.length} 会话
                  <button
                    type="button"
                    className="grid place-items-center w-5 h-5 rounded border border-hairline text-text-muted hover:text-brand-primary hover:border-brand-primary/30 transition-colors"
                    title="新建 Session"
                    onClick={async (e) => {
                      e.preventDefault();
                      try {
                        const created = await createSession({ name: "新会话", llm_account_id: account.id });
                        setSelectedSessionId(created.id as string);
                      } catch { /* store 处理 */ }
                    }}
                  >
                    <Plus size={11} />
                  </button>
                </span>
              </summary>
              <div className="text-text-muted text-[11px] my-1.5">
                初始 {formatMoney(account.initial_cash)}
              </div>
              <div className="grid gap-1.5">
                {account.sessions.length === 0 ? (
                  <p className="text-text-muted text-xs">暂无 Session。</p>
                ) : (
                  account.sessions.map((s) => (
                    <button
                      key={s.id}
                      className={`grid grid-cols-[8px_minmax(0,1fr)_14px_18px] items-center gap-2 p-2 rounded-lg border text-left text-sm transition-colors group ${
                        s.id === selectedSessionId
                          ? "border-brand-primary/40 bg-brand-primary/10"
                          : "border-transparent hover:border-hairline hover:bg-surface-card"
                      }`}
                      onClick={() => setSelectedSessionId(s.id)}
                      type="button"
                    >
                      <StatusDot status={s.status} />
                      <span>
                        <strong className="block text-text-on-dark truncate text-sm">{s.name}</strong>
                        <small className="block text-text-muted text-xs truncate">{s.model ?? "--"}</small>
                      </span>
                      <span className="text-[10px] text-text-muted font-mono">
                        {s.status === "running" ? "⏳" : s.status === "error" ? "⚠" : ""}
                      </span>
                      <button
                        type="button"
                        className="opacity-0 group-hover:opacity-100 transition-opacity text-text-muted hover:text-trading-rise"
                        title="删除 Session"
                        onClick={(e) => {
                          e.stopPropagation();
                          setConfirmDeleteId(s.id);
                        }}
                      >
                        <Trash2 size={13} />
                      </button>
                    </button>
                  ))
                )}
              </div>
            </details>
          ))
        )}
      </div>

      {/* 删除确认弹窗 */}
      {confirmDeleteId && (
        <div className="absolute inset-0 z-20 flex items-center justify-center bg-surface-canvas/80 backdrop-blur-sm">
          <div className="w-[260px] rounded-xl border border-hairline bg-surface-card p-4 shadow-lg">
            <p className="text-sm text-text-on-dark mb-1 font-semibold">确认删除</p>
            <p className="text-xs text-text-muted mb-4">确定要删除此 Session 吗？关联消息和执行记录将被一并清理。</p>
            <div className="flex justify-end gap-2">
              <button
                className="px-3 py-1.5 text-xs rounded-lg border border-hairline text-text-muted hover:text-text-on-dark hover:bg-surface-elevated transition-colors"
                type="button"
                onClick={() => setConfirmDeleteId(null)}
              >
                取消
              </button>
              <button
                className="px-3 py-1.5 text-xs rounded-lg bg-trading-rise text-white hover:bg-trading-rise/80 transition-colors"
                type="button"
                onClick={async () => {
                  if (!confirmDeleteId) return;
                  try {
                    await deleteSession(confirmDeleteId);
                  } catch { /* 由 store 处理 */ }
                  setConfirmDeleteId(null);
                }}
              >
                删除
              </button>
            </div>
          </div>
        </div>
      )}
    </aside>
  );
}

function StatusDot({ status }: { status: string }) {
  const color =
    status === "running"
      ? "bg-accent-turquoise shadow-[0_0_8px_rgba(45,189,182,0.6)]"
      : status === "queued"
        ? "bg-brand-primary"
        : status === "error"
          ? "bg-trading-rise"
          : "bg-text-muted";
  return <span className={`w-2 h-2 rounded-full ${color}`} />;
}
