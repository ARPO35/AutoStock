import { useEffect, useMemo } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
  Activity,
  Database,
  History,
  LineChart,
  MessageSquare,
  RefreshCw,
  Search,
  Table2,
  Wallet
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input, Select } from "@/components/ui/Input";
import { EmptyState, Metric, PanelHeader, Spinner } from "@/components/ui/Shared";
import { useDataStore } from "@/stores/dataStore";
import { useMarketStore } from "@/stores/marketStore";
import { useViewStore, type ViewSection, viewSections } from "@/stores/viewStore";
import type { AccountSnapshot, AssetPoint, TradeRow, ViewLogRow, ViewTimelineRow } from "@/api";
import { barClose, barTime, formatMoney, formatValue, humanTime, linePoints } from "@/lib/utils";

export function ViewPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const section = sectionFromPath(location.pathname);
  const filters = useViewStore((s) => s.filters);
  const loading = useViewStore((s) => s.loading);
  const error = useViewStore((s) => s.error);
  const refreshCurrent = useViewStore((s) => s.refreshCurrent);
  const loadOverview = useViewStore((s) => s.loadOverview);
  const loadAccounts = useViewStore((s) => s.loadAccounts);
  const loadTrades = useViewStore((s) => s.loadTrades);
  const loadAssets = useViewStore((s) => s.loadAssets);
  const loadLogs = useViewStore((s) => s.loadLogs);
  const loadTimeline = useViewStore((s) => s.loadTimeline);

  useEffect(() => {
    if (section === "overview") void loadOverview();
    if (section === "account-detail") void loadAccounts();
    if (section === "trades") void loadTrades();
    if (section === "assets") void loadAssets();
    if (section === "logs") void loadLogs();
    if (section === "timeline") void loadTimeline();
  }, [
    section,
    filters.account_id,
    filters.start,
    filters.end,
    filters.symbol,
    loadOverview,
    loadAccounts,
    loadTrades,
    loadAssets,
    loadLogs,
    loadTimeline
  ]);

  const active = viewSections.find((item) => item.key === section) ?? viewSections[0];

  return (
    <section className="h-full min-h-0 overflow-hidden grid grid-rows-[auto_auto_minmax(0,1fr)] bg-surface-canvas">
      <header className="px-4 pt-4 pb-2 border-b border-hairline/70">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-brand-primary text-xs font-bold tracking-wide mb-1">查看 / {active.label}</p>
            <h1 className="text-xl font-semibold text-text-on-dark">全局观察与复盘分析</h1>
            <p className="mt-1 text-sm text-text-muted">同一套账户、时间、股票筛选驱动所有查看页面，避免交易页和复盘页口径分叉。</p>
          </div>
          <Button
            variant="secondary"
            size="sm"
            icon={<RefreshCw size={14} />}
            onClick={() => void refreshCurrent(section)}
            disabled={loading || section === "stock"}
          >
            刷新
          </Button>
        </div>
      </header>

      <div className="px-4 py-3 border-b border-hairline/70">
        <ViewNav active={section} onChange={(key) => navigate(`/view/${key}`)} />
        <ViewFilters />
      </div>

      <main className="min-h-0 overflow-auto p-4">
        {error && (
          <div className="mb-3 rounded-lg border border-trading-rise/40 bg-trading-rise/10 px-3 py-2 text-sm text-trading-rise">
            {error}
          </div>
        )}
        {loading && section !== "stock" ? <Spinner /> : <ViewSectionPanel section={section} />}
      </main>
    </section>
  );
}

function ViewNav({
  active,
  onChange
}: {
  active: ViewSection;
  onChange: (key: ViewSection) => void;
}) {
  return (
    <nav className="mb-3 flex gap-1.5 overflow-x-auto">
      {viewSections.map((item) => (
        <button
          key={item.key}
          type="button"
          onClick={() => onChange(item.key)}
          className={`min-w-[112px] rounded-lg border px-3 py-2 text-left transition-colors ${
            active === item.key
              ? "border-brand-primary/60 bg-brand-primary/10 text-text-on-dark"
              : "border-hairline bg-surface-card/60 text-text-muted hover:text-text-on-dark hover:bg-surface-card"
          }`}
        >
          <strong className="block text-sm">{item.label}</strong>
          <span className="text-[11px] text-text-muted">{item.sub}</span>
        </button>
      ))}
    </nav>
  );
}

function ViewFilters() {
  const accounts = useDataStore((s) => s.accounts);
  const filters = useViewStore((s) => s.filters);
  const patchFilters = useViewStore((s) => s.patchFilters);

  return (
    <div className="grid grid-cols-1 md:grid-cols-[1.4fr_1fr_1fr_1fr_auto] gap-2 items-end">
      <label className="grid gap-1.5 text-xs text-text-muted">
        账户
        <Select value={filters.account_id ?? ""} onChange={(e) => patchFilters({ account_id: e.target.value || undefined })}>
          <option value="">全部账户</option>
          {accounts.map((account) => (
            <option key={account.id} value={account.id}>{account.name}</option>
          ))}
        </Select>
      </label>
      <Input label="开始日期" type="date" value={filters.start ?? ""} onChange={(e) => patchFilters({ start: e.target.value || undefined })} />
      <Input label="结束日期" type="date" value={filters.end ?? ""} onChange={(e) => patchFilters({ end: e.target.value || undefined })} />
      <Input
        label="股票代码"
        value={filters.symbol ?? ""}
        onChange={(e) => patchFilters({ symbol: e.target.value.trim() || undefined })}
        placeholder="000001"
        icon={<Search size={14} />}
      />
      <Button variant="secondary" size="sm" onClick={() => patchFilters({ account_id: "", start: "", end: "", symbol: "" })}>
        清空
      </Button>
    </div>
  );
}

function ViewSectionPanel({ section }: { section: ViewSection }) {
  if (section === "overview") return <OverviewPanel />;
  if (section === "account-detail") return <AccountDetailPanel />;
  if (section === "trades") return <TradesPanel />;
  if (section === "assets") return <AssetsPanel />;
  if (section === "stock") return <StockPanel />;
  if (section === "logs") return <LogsPanel />;
  return <TimelinePanel />;
}

function OverviewPanel() {
  const data = useViewStore((s) => s.overview);
  if (!data) return <EmptyState title="暂无总览数据" description="点击刷新或调整筛选后加载账户总览。" />;
  return (
    <div className="grid gap-3">
      <MetricStrip summary={data.summary} />
      <div className="grid grid-cols-1 xl:grid-cols-[1fr_420px] gap-3">
        <section className="border border-hairline rounded-xl bg-surface-card p-4">
          <PanelHeader icon={<Wallet size={16} />} title="账户矩阵" />
          <AccountSnapshotGrid snapshots={data.accounts} />
        </section>
        <section className="border border-hairline rounded-xl bg-surface-card p-4">
          <PanelHeader icon={<History size={16} />} title="最近成交" />
          <TradeList trades={data.recent_trades} compact />
        </section>
      </div>
    </div>
  );
}

function AccountDetailPanel() {
  const data = useViewStore((s) => s.accounts);
  if (!data) return <EmptyState title="暂无账号详情" description="账号详情会展示资金、持仓和绑定会话。" />;
  return (
    <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
      {data.accounts.length === 0 ? (
        <EmptyState title="暂无账户" description="创建模拟账户后这里会展示账户详情。" />
      ) : (
        data.accounts.map((snapshot) => <AccountDetailCard key={snapshot.account.id} snapshot={snapshot} />)
      )}
    </div>
  );
}

function TradesPanel() {
  const data = useViewStore((s) => s.trades);
  if (!data) return <EmptyState title="暂无交易历史" description="成交后这里会按筛选条件展示交易记录。" />;
  return (
    <div className="grid gap-3">
      <div className="grid grid-cols-3 gap-2 max-w-[680px]">
        <Metric label="成交数" value={String(data.summary.trade_count ?? 0)} />
        <Metric label="成交额" value={formatMoney(data.summary.turnover)} />
        <Metric label="费用" value={formatMoney(data.summary.fees)} />
      </div>
      <section className="border border-hairline rounded-xl bg-surface-card p-4">
        <PanelHeader icon={<Table2 size={16} />} title="成交明细" />
        <TradeTable trades={data.trades} />
      </section>
    </div>
  );
}

function AssetsPanel() {
  const data = useViewStore((s) => s.assets);
  if (!data) return <EmptyState title="暂无资产曲线" description="账户创建后会生成初始点，成交后会生成交易点。" />;
  return (
    <div className="grid gap-3">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 max-w-[860px]">
        <Metric label="账户数" value={String(data.summary.account_count ?? 0)} />
        <Metric label="最新总资产" value={formatMoney(data.summary.latest_total_asset)} />
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
        {data.series.map((series) => (
          <section key={series.account_id} className="border border-hairline rounded-xl bg-surface-card p-4">
            <PanelHeader icon={<LineChart size={16} />} title={series.account_name} />
            <AssetChart points={series.points} />
            <AssetPointTable points={series.points} />
          </section>
        ))}
      </div>
    </div>
  );
}

function StockPanel() {
  const marketForm = useMarketStore((s) => s.marketForm);
  const setMarketForm = useMarketStore((s) => s.setMarketForm);
  const marketQuote = useMarketStore((s) => s.marketQuote);
  const marketHistory = useMarketStore((s) => s.marketHistory);
  const queryQuote = useMarketStore((s) => s.queryQuote);
  const queryHistory = useMarketStore((s) => s.queryHistory);
  const values = useMemo(() => marketHistory?.bars.map(barClose).filter((v): v is number => v != null) ?? [], [marketHistory]);

  return (
    <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
      <section className="xl:col-span-2 border border-hairline rounded-xl bg-surface-card p-4">
        <PanelHeader icon={<Search size={16} />} title="行情查询" />
        <form
          className="grid grid-cols-1 md:grid-cols-[1fr_160px_160px_120px_auto_auto] gap-2 items-end"
          onSubmit={(event) => {
            event.preventDefault();
            if (marketForm.symbol.trim()) {
              void queryHistory(marketForm.symbol.trim(), marketForm.start || undefined, marketForm.end || undefined, marketForm.adjust || undefined, marketForm.allowFetchMissing);
            }
          }}
        >
          <Input label="股票代码" value={marketForm.symbol} onChange={(e) => setMarketForm({ ...marketForm, symbol: e.target.value })} placeholder="000001" />
          <Input label="开始日期" type="date" value={marketForm.start} onChange={(e) => setMarketForm({ ...marketForm, start: e.target.value })} />
          <Input label="结束日期" type="date" value={marketForm.end} onChange={(e) => setMarketForm({ ...marketForm, end: e.target.value })} />
          <label className="grid gap-1.5 text-xs text-text-muted">
            复权
            <Select value={marketForm.adjust} onChange={(e) => setMarketForm({ ...marketForm, adjust: e.target.value })}>
              <option value="">不复权</option>
              <option value="qfq">前复权</option>
              <option value="hfq">后复权</option>
            </Select>
          </label>
          <Button variant="secondary" size="sm" type="button" disabled={!marketForm.symbol.trim()} onClick={() => void queryQuote(marketForm.symbol.trim())}>
            查报价
          </Button>
          <Button variant="primary" size="sm" type="submit" disabled={!marketForm.symbol.trim()}>
            查历史
          </Button>
        </form>
      </section>
      <section className="border border-hairline rounded-xl bg-surface-card p-4">
        <PanelHeader icon={<Activity size={16} />} title="实时报价" />
        {marketQuote ? <KeyValueGrid data={marketQuote} /> : <EmptyState title="暂无报价" description="输入股票代码后查询当前行情。" />}
      </section>
      <section className="border border-hairline rounded-xl bg-surface-card p-4">
        <PanelHeader icon={<LineChart size={16} />} title="历史行情" />
        {marketHistory ? (
          <>
            <MiniChart values={values} />
            <div className="mt-3 max-h-[360px] overflow-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-text-muted border-b border-hairline">
                    <th className="py-2 font-medium">时间</th>
                    <th className="py-2 font-medium">开</th>
                    <th className="py-2 font-medium">高</th>
                    <th className="py-2 font-medium">低</th>
                    <th className="py-2 font-medium">收</th>
                    <th className="py-2 font-medium">量</th>
                  </tr>
                </thead>
                <tbody>
                  {marketHistory.bars.slice(0, 80).map((bar, index) => (
                    <tr key={`${barTime(bar)}-${index}`} className="border-b border-hairline/50">
                      <td className="py-1.5 font-mono text-xs text-text-on-dark">{barTime(bar)}</td>
                      <td className="py-1.5 text-text-muted">{formatValue(bar.open)}</td>
                      <td className="py-1.5 text-text-muted">{formatValue(bar.high)}</td>
                      <td className="py-1.5 text-text-muted">{formatValue(bar.low)}</td>
                      <td className="py-1.5 text-text-on-dark">{formatValue(bar.close)}</td>
                      <td className="py-1.5 text-text-muted">{formatValue(bar.volume)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : (
          <EmptyState title="暂无历史行情" description="查询历史后显示 K 线数据和收盘价走势。" />
        )}
      </section>
    </div>
  );
}

function LogsPanel() {
  const data = useViewStore((s) => s.logs);
  if (!data) return <EmptyState title="暂无交易理由" description="买入或卖出时传入的交易理由会在这里聚合。" />;
  return (
    <section className="border border-hairline rounded-xl bg-surface-card p-4">
      <PanelHeader icon={<MessageSquare size={16} />} title="交易决策日志" />
      {data.logs.length === 0 ? <EmptyState title="没有匹配交易理由" description="只有 order.buy / order.sell 工具调用会进入决策日志。" /> : <LogList logs={data.logs} />}
    </section>
  );
}

function TimelinePanel() {
  const data = useViewStore((s) => s.timeline);
  if (!data) return <EmptyState title="暂无时间线" description="消息、运行、工具和成交会合并为全局事件流。" />;
  return (
    <section className="border border-hairline rounded-xl bg-surface-card p-4">
      <PanelHeader icon={<Activity size={16} />} title="全局时间线" />
      {data.items.length === 0 ? <EmptyState title="没有匹配事件" description="调整筛选条件后重试。" /> : <TimelineList items={data.items} />}
    </section>
  );
}

function MetricStrip({ summary }: { summary: Record<string, number> }) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-7 gap-2">
      <Metric label="现金" value={formatMoney(summary.cash)} />
      <Metric label="总资产" value={formatMoney(summary.total_asset)} />
      <Metric label="持仓市值" value={formatMoney(summary.market_value)} />
      <Metric label="浮盈亏" value={formatMoney(summary.floating_pnl)} tone={tone(summary.floating_pnl)} />
      <Metric label="总盈亏" value={formatMoney(summary.total_pnl)} tone={tone(summary.total_pnl)} />
      <Metric label="持仓数" value={String(summary.position_count ?? 0)} />
      <Metric label="运行中" value={String(summary.running_sessions ?? 0)} />
    </div>
  );
}

function AccountSnapshotGrid({ snapshots }: { snapshots: AccountSnapshot[] }) {
  if (snapshots.length === 0) return <EmptyState title="暂无账户" description="创建模拟账户后这里会出现账户矩阵。" />;
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
      {snapshots.map((snapshot) => (
        <AccountMini key={snapshot.account.id} snapshot={snapshot} />
      ))}
    </div>
  );
}

function AccountMini({ snapshot }: { snapshot: AccountSnapshot }) {
  return (
    <div className="rounded-xl border border-hairline bg-surface-canvas/50 p-3">
      <div className="flex items-center justify-between gap-2">
        <strong className="text-text-on-dark">{snapshot.account.name}</strong>
        <span className="text-xs text-text-muted">{snapshot.metrics.session_count} Session</span>
      </div>
      <AssetChart points={snapshot.asset_points} compact />
      <div className="grid grid-cols-3 gap-2 mt-2">
        <Metric label="现金" value={formatMoney(snapshot.metrics.cash)} />
        <Metric label="总资产" value={formatMoney(snapshot.metrics.total_asset)} />
        <Metric label="仓位" value={`${(snapshot.metrics.position_ratio * 100).toFixed(1)}%`} />
      </div>
    </div>
  );
}

function AccountDetailCard({ snapshot }: { snapshot: AccountSnapshot }) {
  return (
    <section className="border border-hairline rounded-xl bg-surface-card p-4">
      <PanelHeader icon={<Wallet size={16} />} title={snapshot.account.name} />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3">
        <Metric label="现金" value={formatMoney(snapshot.metrics.cash)} />
        <Metric label="总资产" value={formatMoney(snapshot.metrics.total_asset)} />
        <Metric label="浮盈亏" value={formatMoney(snapshot.metrics.floating_pnl)} tone={tone(snapshot.metrics.floating_pnl)} />
        <Metric label="仓位" value={`${(snapshot.metrics.position_ratio * 100).toFixed(1)}%`} />
      </div>
      <AssetChart points={snapshot.asset_points} />
      <PositionTable positions={snapshot.positions} />
      <div className="mt-3 border-t border-hairline pt-3">
        <PanelHeader icon={<MessageSquare size={15} />} title="绑定会话" />
        {snapshot.sessions.length === 0 ? (
          <p className="text-sm text-text-muted">暂无绑定 Session。</p>
        ) : (
          <div className="grid gap-1.5 text-sm">
            {snapshot.sessions.map((session) => (
              <div key={session.id} className="flex items-center justify-between gap-3 border-b border-hairline/50 py-1.5">
                <span className="text-text-on-dark truncate">{session.name}</span>
                <span className="text-xs text-text-muted">{session.model ?? session.provider_name ?? "--"}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

function PositionTable({ positions }: { positions: AccountSnapshot["positions"] }) {
  if (positions.length === 0) return <EmptyState title="暂无持仓" description="成交买入后显示持仓。" />;
  return (
    <div className="mt-3 max-h-[220px] overflow-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs text-text-muted border-b border-hairline">
            <th className="py-2 font-medium">代码</th>
            <th className="py-2 font-medium">数量</th>
            <th className="py-2 font-medium">可用</th>
            <th className="py-2 font-medium">成本</th>
            <th className="py-2 font-medium">市值</th>
            <th className="py-2 font-medium">浮盈亏</th>
          </tr>
        </thead>
        <tbody>
          {positions.map((row) => (
            <tr key={row.id} className="border-b border-hairline/50">
              <td className="py-1.5 text-text-on-dark">{row.symbol}</td>
              <td className="py-1.5 text-text-muted">{row.quantity}</td>
              <td className="py-1.5 text-text-muted">{row.available_quantity}</td>
              <td className="py-1.5 text-text-muted">{row.avg_cost}</td>
              <td className="py-1.5 text-text-on-dark">{formatMoney(row.market_value)}</td>
              <td className={`py-1.5 ${toneClass(row.unrealized_pnl)}`}>{formatMoney(row.unrealized_pnl)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TradeList({ trades, compact = false }: { trades: TradeRow[]; compact?: boolean }) {
  if (trades.length === 0) return <EmptyState title="暂无成交" description="成交后会显示最近记录。" />;
  return (
    <div className="grid gap-2">
      {trades.slice(0, compact ? 8 : 20).map((trade) => (
        <div key={trade.id} className="flex items-center justify-between gap-3 border-b border-hairline/60 pb-2">
          <div>
            <strong className="block text-sm text-text-on-dark">{trade.side === "buy" ? "买入" : "卖出"} {trade.symbol}</strong>
            <span className="text-xs text-text-muted">{humanTime(trade.traded_at)} / {trade.account_name ?? "--"}</span>
          </div>
          <span className="text-sm text-text-on-dark">{trade.quantity} @ {trade.price}</span>
        </div>
      ))}
    </div>
  );
}

function TradeTable({ trades }: { trades: TradeRow[] }) {
  if (trades.length === 0) return <EmptyState title="暂无成交" description="没有匹配当前筛选条件的成交。" />;
  return (
    <div className="max-h-[560px] overflow-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs text-text-muted border-b border-hairline">
            <th className="py-2 font-medium">时间</th>
            <th className="py-2 font-medium">账户</th>
            <th className="py-2 font-medium">代码</th>
            <th className="py-2 font-medium">方向</th>
            <th className="py-2 font-medium">价格</th>
            <th className="py-2 font-medium">数量</th>
            <th className="py-2 font-medium">成交额</th>
            <th className="py-2 font-medium">费用</th>
            <th className="py-2 font-medium">Session</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((trade) => (
            <tr key={trade.id} className="border-b border-hairline/50">
              <td className="py-1.5 text-text-muted">{humanTime(trade.traded_at)}</td>
              <td className="py-1.5 text-text-on-dark">{trade.account_name ?? "--"}</td>
              <td className="py-1.5 font-mono text-text-on-dark">{trade.symbol}</td>
              <td className={`py-1.5 ${trade.side === "buy" ? "rise" : "fall"}`}>{trade.side === "buy" ? "买入" : "卖出"}</td>
              <td className="py-1.5 text-text-muted">{trade.price}</td>
              <td className="py-1.5 text-text-muted">{trade.quantity}</td>
              <td className="py-1.5 text-text-on-dark">{formatMoney(trade.turnover)}</td>
              <td className="py-1.5 text-text-muted">{formatMoney(trade.total_fee)}</td>
              <td className="py-1.5 text-text-muted">{trade.session_name ?? "--"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AssetChart({ points, compact = false }: { points: AssetPoint[]; compact?: boolean }) {
  if (points.length < 2) return <EmptyState title="曲线点不足" description="至少需要两个资产点。" />;
  const values = points.map((point) => Number(point.total_asset)).filter(Number.isFinite);
  return (
    <svg className={`w-full ${compact ? "h-[72px]" : "h-[150px]"} mt-2`} viewBox="0 0 100 60" role="img" aria-label="资产曲线">
      <defs>
        <linearGradient id="assetLine" x1="0" x2="1" y1="0" y2="0">
          <stop offset="0%" stopColor="var(--color-brand-primary)" />
          <stop offset="100%" stopColor="var(--color-accent-turquoise)" />
        </linearGradient>
      </defs>
      <polyline points={linePoints(values, 96, 46, 2, 7)} fill="none" stroke="url(#assetLine)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function AssetPointTable({ points }: { points: AssetPoint[] }) {
  if (points.length === 0) return null;
  return (
    <div className="mt-3 max-h-[260px] overflow-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs text-text-muted border-b border-hairline">
            <th className="py-2 font-medium">时间</th>
            <th className="py-2 font-medium">现金</th>
            <th className="py-2 font-medium">持仓市值</th>
            <th className="py-2 font-medium">总资产</th>
            <th className="py-2 font-medium">来源</th>
          </tr>
        </thead>
        <tbody>
          {points.slice().reverse().map((point, index) => (
            <tr key={`${point.time}-${index}`} className="border-b border-hairline/50">
              <td className="py-1.5 text-text-muted">{humanTime(point.time)}</td>
              <td className="py-1.5 text-text-muted">{formatMoney(point.cash)}</td>
              <td className="py-1.5 text-text-muted">{formatMoney(point.market_value)}</td>
              <td className="py-1.5 text-text-on-dark">{formatMoney(point.total_asset)}</td>
              <td className="py-1.5 text-text-muted">{point.source}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function MiniChart({ values }: { values: number[] }) {
  if (values.length < 2) return null;
  return (
    <svg className="w-full h-[120px]" viewBox="0 0 100 52" role="img" aria-label="收盘价走势">
      <polyline points={linePoints(values, 96, 42, 2, 5)} fill="none" stroke="var(--color-trading-rise)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function KeyValueGrid({ data }: { data: Record<string, unknown> }) {
  return (
    <div className="grid grid-cols-2 gap-2">
      {Object.entries(data).slice(0, 12).map(([key, value]) => (
        <div key={key} className="rounded-lg border border-hairline bg-surface-canvas/50 p-2">
          <span className="block text-xs text-text-muted">{key}</span>
          <strong className="block mt-1 truncate text-text-on-dark">{formatValue(value)}</strong>
        </div>
      ))}
    </div>
  );
}

function LogList({ logs }: { logs: ViewLogRow[] }) {
  return (
    <div className="grid gap-2">
      {logs.map((log) => (
        <article key={log.id} className="rounded-lg border border-hairline bg-surface-canvas/50 p-3">
          <div className="flex items-center justify-between gap-3 text-xs text-text-muted">
            <span>{log.account_name ?? "未绑定账户"} / {log.session_name ?? log.session_id}</span>
            <span>{humanTime(log.created_at)}</span>
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-semibold text-text-on-dark">
              {log.side === "buy" ? "买入" : "卖出"} {log.symbol ?? "--"}
            </h3>
            <span className="rounded-full border border-hairline px-2 py-0.5 text-xs text-text-muted">
              {log.quantity ?? "--"} 股
            </span>
            <span className="rounded-full border border-hairline px-2 py-0.5 text-xs text-text-muted">
              {log.price ? `成交价 ${log.price}` : log.status ?? "--"}
            </span>
          </div>
          <p className="mt-2 text-sm leading-relaxed text-text-body">{log.trade_reason || "未记录交易理由"}</p>
          {log.error && <p className="mt-2 text-xs text-trading-rise">{log.error}</p>}
        </article>
      ))}
    </div>
  );
}

function TimelineList({ items }: { items: ViewTimelineRow[] }) {
  return (
    <div className="relative grid gap-2 pl-4 before:absolute before:left-1 before:top-1 before:bottom-1 before:w-px before:bg-hairline">
      {items.map((item) => (
        <article key={`${item.type}-${item.id}`} className="relative rounded-lg border border-hairline bg-surface-canvas/50 p-3 before:absolute before:-left-[15px] before:top-4 before:w-2 before:h-2 before:rounded-full before:bg-brand-primary">
          <div className="flex items-center justify-between gap-3 text-xs text-text-muted">
            <span>{item.type} / {item.account_name ?? "未绑定账户"}</span>
            <span>{humanTime(item.time)}</span>
          </div>
          <h3 className="mt-1 text-sm font-semibold text-text-on-dark">{item.title}</h3>
          <p className="mt-1 text-sm text-text-body">{item.summary || "--"}</p>
        </article>
      ))}
    </div>
  );
}

function sectionFromPath(pathname: string): ViewSection {
  const value = pathname.split("/").filter(Boolean)[1] as ViewSection | undefined;
  return viewSections.some((item) => item.key === value) ? value as ViewSection : "overview";
}

function tone(value: number | undefined): "rise" | "fall" | "flat" {
  const num = Number(value ?? 0);
  if (num > 0) return "rise";
  if (num < 0) return "fall";
  return "flat";
}

function toneClass(value: number | undefined): string {
  const t = tone(value);
  return t === "rise" ? "rise" : t === "fall" ? "fall" : "text-text-muted";
}
