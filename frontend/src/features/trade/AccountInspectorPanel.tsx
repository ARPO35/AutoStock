import { useEffect, useMemo, useState } from "react";
import { Activity, ChevronDown, Eye, History, LineChart, RefreshCw, Table2, Wallet } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { EmptyState, Metric, PanelHeader, Spinner } from "@/components/ui/Shared";
import { useDataStore } from "@/stores/dataStore";
import { useTradeStore } from "@/stores/tradeStore";
import { useViewStore } from "@/stores/viewStore";
import type { AccountSnapshot, AssetPoint } from "@/api";
import { formatMoney, humanTime, linePoints } from "@/lib/utils";

export function AccountInspectorPanel() {
  const accounts = useDataStore((s) => s.accounts);
  const sessions = useDataStore((s) => s.sessions);
  const providers = useDataStore((s) => s.providers);
  const selectedSessionId = useTradeStore((s) => s.selectedSessionId);
  const events = useTradeStore((s) => s.events);
  const snapshots = useViewStore((s) => s.snapshots);
  const loadSnapshot = useViewStore((s) => s.loadSnapshot);
  const loading = useViewStore((s) => s.loading);
  const [tradesOpen, setTradesOpen] = useState(true);

  const selectedSession = sessions.find((s) => s.id === selectedSessionId) ?? null;
  const accountId = selectedSession?.simulator_account_id ?? null;
  const selectedAccount = accountId ? accounts.find((a) => a.id === accountId) ?? null : null;
  const selectedProvider = selectedSession?.provider_id ? providers.find((p) => p.id === selectedSession.provider_id) ?? null : null;
  const snapshot = accountId ? snapshots[accountId] : null;

  useEffect(() => {
    if (accountId) void loadSnapshot(accountId);
  }, [accountId, loadSnapshot]);

  useEffect(() => {
    const latest = events[0];
    if (!accountId || latest?.type !== "portfolio_updated") return;
    if (!latest.account_id || latest.account_id === accountId) void loadSnapshot(accountId);
  }, [events, accountId, loadSnapshot]);

  const displayName = snapshot?.account.name ?? selectedAccount?.name ?? "未选择账户";

  return (
    <aside className="h-full min-h-0 overflow-y-auto overflow-x-hidden border-l border-hairline bg-surface-canvas">
      <header className="sticky top-0 z-10 border-b border-hairline bg-surface-canvas/95 px-3 py-3 backdrop-blur">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="mb-1 text-xs font-bold tracking-wide text-brand-primary">账户观察</p>
            <h2 className="truncate text-base font-semibold text-text-on-dark">{displayName}</h2>
            <p className="mt-1 truncate text-xs text-text-muted">
              {selectedSession ? `${selectedSession.name} / ${selectedProvider?.name ?? selectedSession.model ?? "未配置模型"}` : "请选择一个绑定模拟账户的 Session"}
            </p>
          </div>
          <Eye size={17} className="mt-1 text-text-muted" />
        </div>
      </header>

      <div className="p-3">
        {!accountId ? (
          <EmptyState title="未选择账户" description="选择一个绑定模拟账户的 Session 后显示实时账户状态。" />
        ) : loading && !snapshot ? (
          <Spinner />
        ) : snapshot ? (
          <SnapshotContent
            snapshot={snapshot}
            events={events}
            tradesOpen={tradesOpen}
            onToggleTrades={() => setTradesOpen((value) => !value)}
            onRefresh={() => void loadSnapshot(accountId)}
          />
        ) : (
          <EmptyState title="暂无账户数据" description="账户聚合接口暂未返回数据。" />
        )}
      </div>
    </aside>
  );
}

function SnapshotContent({
  snapshot,
  events,
  tradesOpen,
  onToggleTrades,
  onRefresh
}: {
  snapshot: AccountSnapshot;
  events: ReturnType<typeof useTradeStore.getState>["events"];
  tradesOpen: boolean;
  onToggleTrades: () => void;
  onRefresh: () => void;
}) {
  const metrics = snapshot.metrics;
  const pnlTone = metrics.total_pnl > 0 ? "rise" : metrics.total_pnl < 0 ? "fall" : "flat";

  return (
    <div className="grid gap-3">
      <section className="rounded-xl border border-brand-primary/20 bg-brand-primary/5 p-3">
        <div className="flex items-center justify-between gap-2">
          <div>
            <p className="text-xs text-text-muted">账户净值</p>
            <strong className="mt-1 block text-2xl text-text-on-dark">{formatMoney(metrics.total_asset)}</strong>
          </div>
          <Button variant="secondary" size="sm" icon={<RefreshCw size={13} />} onClick={onRefresh}>
            刷新
          </Button>
        </div>
        <div className="mt-2 grid grid-cols-2 gap-2">
          <Metric label="总盈亏" value={formatMoney(metrics.total_pnl)} tone={pnlTone} />
          <Metric label="收益率" value={`${metrics.total_return_pct.toFixed(2)}%`} tone={pnlTone} />
        </div>
      </section>

      <div className="grid grid-cols-2 gap-2">
        <Metric label="现金" value={formatMoney(metrics.cash)} />
        <Metric label="持仓市值" value={formatMoney(metrics.market_value)} />
        <Metric label="浮盈亏" value={formatMoney(metrics.floating_pnl)} tone={metrics.floating_pnl > 0 ? "rise" : metrics.floating_pnl < 0 ? "fall" : "flat"} />
        <Metric label="仓位" value={`${(metrics.position_ratio * 100).toFixed(1)}%`} />
        <Metric label="持仓数" value={String(metrics.position_count)} />
        <Metric label="运行中" value={String(metrics.running_sessions)} />
      </div>

      <section className="border-t border-hairline pt-3">
        <PanelHeader icon={<LineChart size={16} />} title="资产变化" />
        <AssetSparkline points={snapshot.asset_points} />
      </section>

      <section className="border-t border-hairline pt-3">
        <PanelHeader icon={<Table2 size={16} />} title="持仓" />
        {snapshot.positions.length === 0 ? <EmptyState title="暂无持仓" description="买入成交后显示股票持仓。" /> : <PositionRows snapshot={snapshot} />}
      </section>

      <section className="border-t border-hairline pt-3">
        <button
          type="button"
          className="mb-2 flex w-full items-center justify-between gap-2 text-left text-text-muted hover:text-text-on-dark"
          onClick={onToggleTrades}
        >
          <span className="inline-flex items-center gap-2 text-sm font-semibold">
            <History size={16} />
            交易记录
          </span>
          <ChevronDown size={15} className={`transition-transform ${tradesOpen ? "rotate-180" : ""}`} />
        </button>
        {tradesOpen && <TradeRows snapshot={snapshot} />}
      </section>

      <section className="border-t border-hairline pt-3">
        <PanelHeader icon={<Activity size={16} />} title="实时事件" />
        {events.length === 0 ? (
          <p className="text-sm text-text-muted">暂无 WebSocket 事件。</p>
        ) : (
          <div className="grid gap-1.5">
            {events.slice(0, 8).map((event, index) => (
              <div key={`${event.type}-${index}`} className="flex items-center justify-between gap-2 border-b border-hairline/50 py-1.5 text-xs">
                <span className="text-text-on-dark">{event.type}</span>
                <span className="truncate text-text-muted">{event.tool_name ?? event.status ?? event.error ?? event.run_id ?? "--"}</span>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function AssetSparkline({ points }: { points: AssetPoint[] }) {
  const values = useMemo(() => points.map((point) => Number(point.total_asset)).filter(Number.isFinite), [points]);
  if (values.length < 2) return <EmptyState title="曲线点不足" description="成交或估值更新后生成更多资产点。" />;
  return (
    <svg className="h-[120px] w-full" viewBox="0 0 100 52" role="img" aria-label="资产变化折线">
      <polyline points={linePoints(values, 96, 42, 2, 5)} fill="none" stroke="var(--color-brand-primary)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function PositionRows({ snapshot }: { snapshot: AccountSnapshot }) {
  return (
    <div className="grid gap-1.5">
      {snapshot.positions.map((position) => (
        <div key={position.id} className="rounded-lg border border-hairline bg-surface-card p-2">
          <div className="flex items-center justify-between gap-2">
            <strong className="text-sm text-text-on-dark">{position.symbol}</strong>
            <span className={position.unrealized_pnl > 0 ? "rise text-sm" : position.unrealized_pnl < 0 ? "fall text-sm" : "text-sm text-text-muted"}>
              {formatMoney(position.unrealized_pnl)}
            </span>
          </div>
          <div className="mt-1 grid grid-cols-3 gap-2 text-xs text-text-muted">
            <span>数量 {position.quantity}</span>
            <span>可用 {position.available_quantity}</span>
            <span>成本 {position.avg_cost}</span>
          </div>
          <div className="mt-1 text-xs text-text-muted">市值 {formatMoney(position.market_value)}</div>
        </div>
      ))}
    </div>
  );
}

function TradeRows({ snapshot }: { snapshot: AccountSnapshot }) {
  if (snapshot.recent_trades.length === 0) return <EmptyState title="暂无成交" description="成交后显示最近交易记录。" />;
  return (
    <div className="grid gap-1.5">
      {snapshot.recent_trades.slice(0, 10).map((trade) => (
        <div key={trade.id} className="flex items-center justify-between gap-2 border-b border-hairline/50 py-1.5 text-sm">
          <div>
            <strong className={trade.side === "buy" ? "rise" : "fall"}>{trade.side === "buy" ? "买入" : "卖出"} {trade.symbol}</strong>
            <p className="text-xs text-text-muted">{humanTime(trade.traded_at)}</p>
          </div>
          <span className="text-text-on-dark">{trade.quantity} @ {trade.price}</span>
        </div>
      ))}
    </div>
  );
}
