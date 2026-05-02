import { Eye, LineChart, Table2, History, Activity } from "lucide-react";
import { useDataStore } from "@/stores/dataStore";
import { useTradeStore } from "@/stores/tradeStore";
import { useUIStore } from "@/stores/uiStore";
import { Metric, EmptyState, PanelHeader } from "@/components/ui/Shared";
import { formatMoney } from "@/lib/utils";

export function AccountInspectorPanel() {
  const accounts = useDataStore((s) => s.accounts);
  const sessions = useDataStore((s) => s.sessions);
  const providers = useDataStore((s) => s.providers);
  const selectedSessionId = useTradeStore((s) => s.selectedSessionId);
  const events = useTradeStore((s) => s.events);

  const selectedSession = sessions.find((s) => s.id === selectedSessionId) ?? null;
  const selectedAccount = selectedSession?.llm_account_id
    ? accounts.find((a) => a.id === selectedSession.llm_account_id) ?? null
    : null;
  const selectedProvider = selectedSession?.provider_id
    ? providers.find((p) => p.id === selectedSession.provider_id) ?? null
    : null;

  const runningCount = selectedAccount
    ? sessions.filter(
        (s) =>
          s.llm_account_id === selectedAccount.id &&
          s.status !== null &&
          s.status.includes("run")
      ).length
    : 0;

  const sessionCount = selectedAccount
    ? sessions.filter((s) => s.llm_account_id === selectedAccount.id).length
    : 0;

  return (
    <aside className="min-h-0 overflow-auto p-3 border-l border-hairline bg-surface-canvas">
      {/* Title */}
      <header className="flex items-center justify-between gap-3 mb-3">
        <div>
          <p className="text-brand-primary text-xs font-bold tracking-wide mb-1">
            账户观察
          </p>
          <h2 className="text-base font-semibold text-text-on-dark">
            {selectedAccount?.name ?? "未选择账户"}
          </h2>
        </div>
        <Eye size={17} className="text-text-muted" />
      </header>

      {!selectedAccount ? (
        <EmptyState
          title="未选择账户"
          description="选择或创建账户后显示账户上下文。"
        />
      ) : (
        <>
          {/* Context Strip */}
          <div className="grid gap-1.5 p-2.5 border border-brand-primary/20 rounded-lg bg-brand-primary/5 text-text-muted text-xs mb-3">
            <span>当前账户：{selectedAccount.name}</span>
            <span>Session ID：{selectedSession?.id ?? "--"}</span>
            <span>模型：{selectedProvider?.model ?? "--"}</span>
            <span>Skill：{selectedSession?.skill_id ?? "--"}</span>
          </div>

          {/* Metrics Grid */}
          <div className="grid grid-cols-2 gap-2 mb-3">
            <Metric
              label="初始资金"
              value={formatMoney(selectedAccount.initial_cash)}
            />
            <Metric label="Provider" value={selectedProvider?.name ?? "--"} />
            <Metric label="Session数" value={String(sessionCount)} />
            <Metric label="运行中" value={String(runningCount)} />
          </div>

          {/* 资产曲线 */}
          <section className="pt-3 border-t border-hairline mb-3">
            <PanelHeader icon={<LineChart size={16} />} title="资产曲线" />
            <EmptyState
              title="暂无数据"
              description="后端尚未接入模拟交易账本，无法展示资产曲线。"
            />
          </section>

          {/* 持仓股票 */}
          <section className="pt-3 border-t border-hairline mb-3">
            <PanelHeader icon={<Table2 size={16} />} title="持仓股票" />
            <EmptyState
              title="暂无数据"
              description="后端尚未提供持仓接口。"
            />
          </section>

          {/* 交易记录 */}
          <section className="pt-3 border-t border-hairline mb-3">
            <PanelHeader icon={<History size={16} />} title="交易记录" />
            <EmptyState
              title="暂无数据"
              description="后端尚未提供订单和成交接口。"
            />
          </section>

          {/* 实时事件 */}
          <section className="pt-3 border-t border-hairline">
            <PanelHeader icon={<Activity size={16} />} title="实时事件" />
            {events.length === 0 ? (
              <p className="text-text-muted text-sm">暂无后端 WebSocket 事件。</p>
            ) : (
              <div className="text-sm">
                {events.slice(0, 6).map((event, i) => (
                  <div
                    className="flex justify-between gap-2 py-1.5 border-b border-hairline/50"
                    key={`${event.type}-${i}`}
                  >
                    <span className="text-text-on-dark text-xs">
                      {event.type}
                    </span>
                    <small className="text-text-muted text-xs truncate max-w-[60%]">
                      {event.tool_name ?? event.status ?? event.error ?? event.run_id ?? "--"}
                    </small>
                  </div>
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </aside>
  );
}
