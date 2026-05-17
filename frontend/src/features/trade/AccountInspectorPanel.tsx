import { useEffect, useMemo, useRef, useState } from "react";
import { Activity, ChevronDown, Eye, History, LineChart, RefreshCw, Table2, Wallet } from "lucide-react";
import { AssetValueChart } from "@/components/charts/AssetValueChart";
import { Button } from "@/components/ui/Button";
import { EmptyState, Metric, PanelHeader, Spinner } from "@/components/ui/Shared";
import { api } from "@/api";
import { useDataStore } from "@/stores/dataStore";
import { useTradeStore } from "@/stores/tradeStore";
import { useViewStore } from "@/stores/viewStore";
import type { AccountSnapshot, AssetPoint, ReplayClockState, RuntimeEvent } from "@/api";
import { formatMoney, humanTime } from "@/lib/utils";
import { resolveModelSelection } from "@/lib/providerModels";

export function AccountInspectorPanel() {
  const accounts = useDataStore((s) => s.accounts);
  const sessions = useDataStore((s) => s.sessions);
  const providers = useDataStore((s) => s.providers);
  const selectedSessionId = useTradeStore((s) => s.selectedSessionId);
  const events = useTradeStore((s) => s.events);
  const pushEvent = useTradeStore((s) => s.pushEvent);
  const busy = useTradeStore((s) => s.busy);
  const focusToolCall = useTradeStore((s) => s.focusToolCall);
  const replayClocks = useTradeStore((s) => s.replayClocks);
  const loadReplayClock = useTradeStore((s) => s.loadReplayClock);
  const syncReplayClock = useTradeStore((s) => s.syncReplayClock);
  const snapshots = useViewStore((s) => s.snapshots);
  const loadSnapshot = useViewStore((s) => s.loadSnapshot);
  const loading = useViewStore((s) => s.loading);
  const [tradesOpen, setTradesOpen] = useState(true);
  const [manualRefreshing, setManualRefreshing] = useState(false);
  const refreshTimerRef = useRef<number | null>(null);

  const selectedSession = sessions.find((s) => s.id === selectedSessionId) ?? null;
  const accountId = selectedSession?.simulator_account_id ?? null;
  const selectedAccount = accountId ? accounts.find((a) => a.id === accountId) ?? null : null;
  const selectedProvider = selectedSession?.provider_id ? providers.find((p) => p.id === selectedSession.provider_id) ?? null : null;
  const selectedModelOption = selectedSession
    ? resolveModelSelection(providers, selectedSession.model, selectedSession.provider_id)
    : null;
  const snapshot = accountId ? snapshots[accountId] : null;
  const clock = accountId ? replayClocks[accountId] ?? null : null;

  useEffect(() => {
    if (!accountId) return;
    void loadSnapshot(accountId);
    void loadReplayClock(accountId);
  }, [accountId, loadSnapshot, loadReplayClock]);

  useEffect(() => {
    if (!accountId) return;
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${protocol}//${window.location.host}/ws/accounts/${accountId}`);
    ws.onmessage = (evt) => {
      let event: RuntimeEvent;
      try {
        event = JSON.parse(evt.data as string) as RuntimeEvent;
      } catch {
        return;
      }
      if (event.type !== "portfolio_updated" || event.account_id !== accountId) return;
      pushEvent(event);
      if (event.clock) syncReplayClock(event.clock);
      if (refreshTimerRef.current) window.clearTimeout(refreshTimerRef.current);
      refreshTimerRef.current = window.setTimeout(() => {
        void loadSnapshot(accountId);
      }, 250);
    };
    return () => {
      ws.onmessage = null;
      try { ws.close(); } catch { /* ignore */ }
    };
  }, [accountId, loadSnapshot, pushEvent, syncReplayClock]);

  useEffect(() => {
    const latest = events[0];
    if (!accountId || !latest) return;
    const refreshEvents = new Set(["portfolio_updated", "order_created", "trade_created", "tool_call_finished", "run_finished"]);
    if (!refreshEvents.has(latest.type)) return;
    if (latest.account_id && latest.account_id !== accountId) return;
    if (latest.type === "tool_call_finished" && !String(latest.tool_name ?? "").match(/^(order_|portfolio_)/)) return;
    if (refreshTimerRef.current) window.clearTimeout(refreshTimerRef.current);
    refreshTimerRef.current = window.setTimeout(() => {
      void loadSnapshot(accountId);
    }, 350);
  }, [events, accountId, loadSnapshot]);

  useEffect(() => {
    if (!accountId || !busy) return;
    const timer = window.setInterval(() => {
      void loadSnapshot(accountId);
    }, 15000);
    return () => window.clearInterval(timer);
  }, [accountId, busy, loadSnapshot]);

  const displayName = snapshot?.account.name ?? selectedAccount?.name ?? "未选择账户";
  const handleRefresh = async () => {
    if (!accountId) return;
    setManualRefreshing(true);
    try {
      const result = await api.accountValuationRefresh(accountId);
      syncReplayClock(result.clock);
      await loadSnapshot(accountId);
    } finally {
      setManualRefreshing(false);
    }
  };

  return (
    <aside className="h-full min-h-0 overflow-y-auto overflow-x-hidden border-l border-hairline bg-surface-canvas">
      <header className="sticky top-0 z-10 border-b border-hairline bg-surface-canvas/95 px-3 py-3 backdrop-blur">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="mb-1 text-xs font-bold tracking-wide text-brand-primary">账户观察</p>
            <h2 className="truncate text-base font-semibold text-text-on-dark">{displayName}</h2>
            <p className="mt-1 truncate text-xs text-text-muted">
              {selectedSession ? `${selectedSession.name} / ${selectedProvider?.name ?? selectedModelOption?.providerName ?? selectedSession.model ?? "未配置模型"}` : "请选择一个绑定模拟账户的 Session"}
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
            clock={clock}
            events={events}
            tradesOpen={tradesOpen}
            onToggleTrades={() => setTradesOpen((value) => !value)}
            refreshing={manualRefreshing}
            onRefresh={() => void handleRefresh()}
            onFocusToolCall={(toolCallId, sessionId) => focusToolCall(toolCallId, sessionId)}
          />
        ) : (
          <EmptyState title="暂无账户数据" description="账户聚合接口暂未返回数据。" />
        )}
      </div>
    </aside>
  );
}

function formatStockCode(symbol: string): string {
  return symbol.match(/\d{6}/)?.[0] ?? symbol;
}

function SnapshotContent({
  snapshot,
  clock,
  events,
  tradesOpen,
  onToggleTrades,
  refreshing,
  onRefresh,
  onFocusToolCall
}: {
  snapshot: AccountSnapshot;
  clock: ReplayClockState | null;
  events: ReturnType<typeof useTradeStore.getState>["events"];
  tradesOpen: boolean;
  onToggleTrades: () => void;
  refreshing: boolean;
  onRefresh: () => void;
  onFocusToolCall: (toolCallId: string, sessionId?: string | null) => void;
}) {
  const metrics = snapshot.metrics;
  const pnlTone = metrics.total_pnl > 0 ? "rise" : metrics.total_pnl < 0 ? "fall" : "flat";
  const latestValuationTime = useMemo(() => latestValuationPoint(snapshot.asset_points)?.time ?? snapshot.account.updated_at, [snapshot]);
  const accountEvents = useMemo(
    () => events.filter((event) => !event.account_id || event.account_id === snapshot.account.id),
    [events, snapshot.account.id]
  );
  const clockDisplay = clockSummary(clock);
  const tradeStats = useMemo(() => {
    const trades = snapshot.recent_trades;
    const turnover = trades.reduce((sum, row) => sum + Number(row.turnover ?? Number(row.price) * Number(row.quantity)), 0);
    const fees = trades.reduce((sum, row) => sum + Number(row.total_fee ?? Number(row.fee ?? 0) + Number(row.tax ?? 0)), 0);
    return {
      buyCount: trades.filter((row) => row.side === "buy").length,
      sellCount: trades.filter((row) => row.side === "sell").length,
      turnover,
      fees,
    };
  }, [snapshot.recent_trades]);

  return (
    <div className="grid gap-3">
      <section className="rounded-xl border border-brand-primary/20 bg-brand-primary/5 p-3">
        <div className="flex items-center justify-between gap-2">
          <div>
            <p className="text-xs text-text-muted">账户净值</p>
            <strong className="mt-1 block text-2xl text-text-on-dark">{formatMoney(metrics.total_asset)}</strong>
          </div>
          <Button variant="secondary" size="sm" icon={<RefreshCw size={13} className={refreshing ? "animate-spin" : ""} />} onClick={onRefresh} disabled={refreshing}>
            {refreshing ? "刷新中" : "刷新"}
          </Button>
        </div>
        <div className="mt-2 grid grid-cols-2 gap-2">
          <Metric label="总盈亏" value={formatMoney(metrics.total_pnl)} tone={pnlTone} />
          <Metric label="收益率" value={`${metrics.total_return_pct.toFixed(2)}%`} tone={pnlTone} />
        </div>
      </section>

      <section className="rounded-lg border border-hairline bg-surface-card p-2">
        <div className="grid grid-cols-2 gap-2">
          <Metric label="最近估值" value={humanTime(latestValuationTime)} />
          <Metric label="Clock" value={clockDisplay.mode} />
          <Metric label="刷新状态" value={clockDisplay.status} />
          <Metric label="账户时间" value={humanTime(clock?.effective_time)} />
        </div>
      </section>

      <div className="grid grid-cols-2 gap-2">
        <Metric label="初始资金" value={formatMoney(metrics.initial_cash)} />
        <Metric label="现金" value={formatMoney(metrics.cash)} />
        <Metric label="冻结资金" value={formatMoney(metrics.frozen_cash)} />
        <Metric label="持仓市值" value={formatMoney(metrics.market_value)} />
        <Metric label="浮盈亏" value={formatMoney(metrics.floating_pnl)} tone={metrics.floating_pnl > 0 ? "rise" : metrics.floating_pnl < 0 ? "fall" : "flat"} />
        <Metric label="仓位" value={`${(metrics.position_ratio * 100).toFixed(1)}%`} />
        <Metric label="持仓数" value={String(metrics.position_count)} />
        <Metric label="运行中" value={String(metrics.running_sessions)} />
      </div>

      <section className="border-t border-hairline pt-3">
        <PanelHeader icon={<Wallet size={16} />} title="交易统计" />
        <div className="grid grid-cols-2 gap-2">
          <Metric label="买入次数" value={String(tradeStats.buyCount)} />
          <Metric label="卖出次数" value={String(tradeStats.sellCount)} />
          <Metric label="最近成交额" value={formatMoney(tradeStats.turnover)} />
          <Metric label="最近费用" value={formatMoney(tradeStats.fees)} />
        </div>
      </section>

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
        {tradesOpen && <TradeRows snapshot={snapshot} onFocusToolCall={onFocusToolCall} />}
      </section>

      <section className="border-t border-hairline pt-3">
        <PanelHeader icon={<Activity size={16} />} title="实时事件" />
        {accountEvents.length === 0 ? (
          <p className="text-sm text-text-muted">暂无 WebSocket 事件。</p>
        ) : (
          <div className="grid gap-1.5">
            {accountEvents.slice(0, 8).map((event, index) => (
              <div key={`${event.type}-${index}`} className="flex items-center justify-between gap-2 border-b border-hairline/50 py-1.5 text-xs">
                <span className="text-text-on-dark">{eventLabel(event)}</span>
                <span className="truncate text-text-muted">{eventDetail(event)}</span>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function latestValuationPoint(points: AssetPoint[]): AssetPoint | null {
  for (let index = points.length - 1; index >= 0; index -= 1) {
    if (points[index].source === "valuation") return points[index];
  }
  return null;
}

function clockSummary(clock: ReplayClockState | null): { mode: string; status: string } {
  if (!clock || clock.mode === "live") return { mode: "Live", status: "live" };
  if (clock.speed <= 0) return { mode: "Replay", status: "replay paused" };
  return { mode: "Replay", status: "replay running" };
}

function eventLabel(event: RuntimeEvent): string {
  if (event.type === "portfolio_updated") return "估值更新";
  if (event.type === "order_created") return "订单";
  if (event.type === "trade_created") return "成交";
  if (event.type === "tool_call_finished") return "工具完成";
  if (event.type === "run_finished") return "运行结束";
  return event.type;
}

function eventDetail(event: RuntimeEvent): string {
  if (event.type === "portfolio_updated") {
    const total = typeof event.total_asset === "number" ? formatMoney(event.total_asset) : "--";
    const symbols = event.symbols?.length ? event.symbols.join(", ") : event.source ?? "valuation";
    const eventTime = event.valuation_point?.time ?? event.clock?.effective_time ?? event.generated_at;
    return `${total} / ${symbols} / ${humanTime(eventTime)}`;
  }
  return event.tool_name ?? event.status ?? event.error ?? event.run_id ?? "--";
}

function AssetSparkline({ points }: { points: AssetPoint[] }) {
  return (
    <AssetValueChart
      series={[{ account_id: "inspector", account_name: "账户资产", points }]}
      valueMode="asset"
      height={260}
      showLegend={false}
      emptyDescription="成交或估值更新后生成更多资产点。"
    />
  );
}

function PositionRows({ snapshot }: { snapshot: AccountSnapshot }) {
  return (
    <div className="grid gap-1.5">
      {snapshot.positions.map((position) => (
        <div key={position.id} className="rounded-lg border border-hairline bg-surface-card p-2">
          <div className="flex items-center justify-between gap-2">
            <strong className="text-sm text-text-on-dark">{position.name ? `${position.name}（${formatStockCode(position.symbol)}）` : position.symbol}</strong>
            <span className={position.unrealized_pnl > 0 ? "rise text-sm" : position.unrealized_pnl < 0 ? "fall text-sm" : "text-sm text-text-muted"}>
              {formatMoney(position.unrealized_pnl)}
            </span>
          </div>
          <div className="mt-1 grid grid-cols-3 gap-2 text-xs text-text-muted">
            <span>数量 {position.quantity}</span>
            <span>可用 {position.available_quantity}</span>
            <span>成本 {position.avg_cost}</span>
          </div>
          <div className="mt-1 grid grid-cols-3 gap-2 text-xs text-text-muted">
            <span>现价 {currentPrice(position)}</span>
            <span>市值 {formatMoney(position.market_value)}</span>
            <span className={position.unrealized_pnl > 0 ? "rise" : position.unrealized_pnl < 0 ? "fall" : ""}>
              盈亏率 {pnlPct(position)}
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}

function TradeRows({
  snapshot,
  onFocusToolCall
}: {
  snapshot: AccountSnapshot;
  onFocusToolCall: (toolCallId: string, sessionId?: string | null) => void;
}) {
  if (snapshot.recent_trades.length === 0) return <EmptyState title="暂无成交" description="成交后显示最近交易记录。" />;
  return (
    <div className="grid gap-1.5">
      {snapshot.recent_trades.slice(0, 10).map((tradeRow) => {
        const stockCode = formatStockCode(tradeRow.symbol);
        const stockLabel = tradeRow.name ? `${tradeRow.name}（${stockCode}）` : stockCode;
        const trade = { ...tradeRow, symbol: stockLabel };

        return (
          <button
            key={trade.id}
            type="button"
            disabled={!trade.tool_call_id}
            onClick={() => trade.tool_call_id && onFocusToolCall(trade.tool_call_id, trade.session_id)}
            className="flex w-full items-center justify-between gap-2 border-b border-hairline/50 py-1.5 text-left text-sm hover:bg-surface-card/70 disabled:hover:bg-transparent"
            title={trade.tool_call_id ? "定位到对应工具调用" : "此成交没有工具调用归因"}
          >
            <div className="min-w-0">
              <strong className={`${trade.side === "buy" ? "rise" : "fall"} block truncate`}>
                {trade.side === "buy" ? "买入" : "卖出"} {trade.symbol}
              </strong>
              <p className="text-xs text-text-muted">{humanTime(trade.traded_at)} / {trade.session_name ?? "未绑定 Session"}</p>
            </div>
            <span className="shrink-0 text-text-on-dark">{trade.quantity} 股 @ ¥{trade.price.toFixed(2)}/股</span>
          </button>
        );
      })}
    </div>
  );
}

function currentPrice(position: AccountSnapshot["positions"][number]): string {
  const quantity = Number(position.quantity);
  const marketValue = Number(position.market_value);
  if (!Number.isFinite(quantity) || quantity <= 0 || !Number.isFinite(marketValue)) return "--";
  return `¥${(marketValue / quantity).toFixed(2)}`;
}

function pnlPct(position: AccountSnapshot["positions"][number]): string {
  const cost = Number(position.avg_cost) * Number(position.quantity);
  const pnl = Number(position.unrealized_pnl);
  if (!Number.isFinite(cost) || cost <= 0 || !Number.isFinite(pnl)) return "--";
  return `${(pnl / cost * 100).toFixed(2)}%`;
}
