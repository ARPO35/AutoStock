import { type ReactNode, useMemo } from "react";
import {
  RefreshCw,
  Pause,
  Gauge,
  Database,
  LineChart,
  MessageSquare,
  History,
  Wallet,
  Activity
} from "lucide-react";
import { useDataStore } from "@/stores/dataStore";
import { useMarketStore } from "@/stores/marketStore";
import { useUIStore, viewTabs } from "@/stores/uiStore";
import { Metric, InfoGrid, EmptyState, PanelHeader, SubTabs } from "@/components/ui/Shared";
import { Button } from "@/components/ui/Button";
import { Input, Select } from "@/components/ui/Input";
import {
  formatMoney,
  normalizeStatus,
  statusLabel,
  humanTime,
  barClose,
  barTime,
  linePoints,
  formatValue,
  objectEntries
} from "@/lib/utils";

/* ------------------------------------------------------------------ */
/*  Page shell                                                        */
/* ------------------------------------------------------------------ */

export function ViewPage() {
  const viewTab = useUIStore((s) => s.viewTab);
  const setViewTab = useUIStore((s) => s.setViewTab);
  const accounts = useDataStore((s) => s.accounts);
  const sessions = useDataStore((s) => s.sessions);
  const providers = useDataStore((s) => s.providers);
  const refreshAll = useDataStore((s) => s.refreshAll);

  return (
    <section className="flex flex-col min-h-0 overflow-auto p-4 gap-3">
      <PageHeader
        eyebrow={`查看 - ${viewTab}`}
        title="全局观察、对比分析、行情浏览、模拟时间线控制"
        actions={
          <>
            <Button
              variant="secondary"
              size="sm"
              icon={<RefreshCw size={14} />}
              onClick={() => void refreshAll()}
            >
              刷新
            </Button>
            <Button variant="secondary" size="sm" icon={<Pause size={14} />} disabled>
              暂停同步
            </Button>
          </>
        }
      />

      <SubTabs tabs={viewTabs} active={viewTab} onChange={setViewTab} />

      {viewTab === "总览" && (
        <ViewOverview
          accounts={accounts}
          sessions={sessions}
          providers={providers}
        />
      )}
      {viewTab === "账号详情" && (
        <AccountDetailPanel
          accounts={accounts}
          sessions={sessions}
          providers={providers}
        />
      )}
      {viewTab === "股票信息" && <MarketDataPanel />}
      {!["总览", "账号详情", "股票信息"].includes(viewTab) && (
        <PlaceholderSection
          title={viewTab}
          description={viewTabDesc(viewTab)}
        />
      )}
    </section>
  );
}

/* ------------------------------------------------------------------ */
/*  PageHeader                                                        */
/* ------------------------------------------------------------------ */

function PageHeader({
  eyebrow,
  title,
  actions
}: {
  eyebrow: string;
  title: string;
  actions?: ReactNode;
}) {
  return (
    <header className="flex items-center justify-between gap-3.5 mb-1">
      <div className="min-w-0">
        <p className="text-brand-primary text-xs font-bold tracking-wide mb-1">
          {eyebrow}
        </p>
        <h1 className="text-lg font-semibold text-text-on-dark truncate">
          {title}
        </h1>
      </div>
      {actions && <div className="flex items-center gap-2 flex-shrink-0">{actions}</div>}
    </header>
  );
}

/* ------------------------------------------------------------------ */
/*  ViewOverview                                                      */
/* ------------------------------------------------------------------ */

function ViewOverview({
  accounts,
  sessions,
  providers
}: {
  accounts: import("@/api").Account[];
  sessions: import("@/api").Session[];
  providers: import("@/api").Provider[];
}) {
  const cacheRows = useMarketStore((s) => s.cacheRows);

  const runningCount = sessions.filter((s) =>
    (s.status ?? "").includes("run")
  ).length;

  const cacheBars = cacheRows.reduce(
    (sum, row) => sum + Number(row.bar_count ?? 0),
    0
  );

  return (
    <>
      {/* Account cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
        {accounts.length === 0 ? (
          <EmptyState
            title="暂无账户"
            description="创建账户后这里会展示真实账户列表。"
          />
        ) : (
          accounts.map((a) => (
            <AccountSummaryCard
              key={a.id}
              account={a}
              sessions={sessions.filter((s) => s.simulator_account_id === a.id)}
            />
          ))
        )}
      </div>

      {/* Metrics grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
        <section className="border border-hairline rounded-xl bg-surface-card p-4">
          <PanelHeader icon={<Gauge size={16} />} title="当前对象统计" />
          <div className="grid grid-cols-2 gap-2 mt-2">
            <Metric label="Provider" value={String(providers.length)} />
            <Metric label="账户" value={String(accounts.length)} />
            <Metric label="Session" value={String(sessions.length)} />
            <Metric label="运行中" value={String(runningCount)} />
          </div>
        </section>

        <section className="border border-hairline rounded-xl bg-surface-card p-4">
          <PanelHeader icon={<Database size={16} />} title="行情缓存" />
          <div className="grid grid-cols-2 gap-2 mt-2">
            <Metric label="缓存标的" value={String(cacheRows.length)} />
            <Metric label="缓存记录" value={String(cacheBars)} />
          </div>
        </section>

        <section className="border border-hairline rounded-xl bg-surface-card p-4">
          <PanelHeader icon={<LineChart size={16} />} title="资产曲线" />
          <EmptyState
            title="暂无数据"
            description="后端尚未接入模拟交易账本，无法展示资产曲线。"
          />
        </section>

        <section className="border border-hairline rounded-xl bg-surface-card p-4">
          <PanelHeader icon={<MessageSquare size={16} />} title="最近 LLM 决策" />
          <EmptyState
            title="暂无数据"
            description="后端尚未提供决策日志聚合接口。"
          />
        </section>

        <section className="border border-hairline rounded-xl bg-surface-card p-4">
          <PanelHeader icon={<History size={16} />} title="最近交易" />
          <EmptyState
            title="暂无数据"
            description="后端尚未提供交易历史接口。"
          />
        </section>
      </div>
    </>
  );
}

/* ------------------------------------------------------------------ */
/*  AccountSummaryCard                                                */
/* ------------------------------------------------------------------ */

function AccountSummaryCard({
  account,
  sessions
}: {
  account: import("@/api").Account;
  sessions: import("@/api").Session[];
}) {
  const running = sessions.filter((s) => (s.status ?? "").includes("run")).length;

  return (
    <div className="border border-hairline rounded-xl bg-surface-card p-4">
      <header className="flex items-center justify-between gap-2 mb-2">
        <span className="text-sm font-semibold text-text-on-dark truncate">
          {account.name}
        </span>
      </header>
      <strong className="block text-lg text-text-on-dark">
        {formatMoney(account.initial_cash)}
      </strong>
      <div className="flex gap-3 mt-2 text-xs text-text-muted">
        <span>Session {sessions.length}</span>
        <span>运行中 {running}</span>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  AccountDetailPanel                                                */
/* ------------------------------------------------------------------ */

function AccountDetailPanel({
  accounts,
  sessions,
  providers
}: {
  accounts: import("@/api").Account[];
  sessions: import("@/api").Session[];
  providers: import("@/api").Provider[];
}) {
  const providerName = useMemo(
    () => {
      const map = new Map(providers.map((p) => [p.id, p.name]));
      return (id: string | null | undefined) => (id ? map.get(id) ?? id : "--");
    },
    [providers]
  );

  const accountRows = useMemo(
    () =>
      accounts.map((a) => {
        const related = sessions.filter((s) => s.simulator_account_id === a.id);
        return {
          ...a,
          sessionCount: related.length,
          runningSessions: related.filter((r) =>
            (r.status ?? "").includes("run")
          ).length
        };
      }),
    [accounts, sessions]
  );

  const sessionRows = useMemo(
    () =>
      sessions.map((s) => {
        const acc = accountRows.find((a) => a.id === s.simulator_account_id);
        return {
          id: s.id,
          name: s.name,
          accountName: acc?.name ?? "--",
          model: s.model ?? "--",
          providerId: s.provider_id ?? "--",
          status: normalizeStatus(s.status),
          lastRunAt: s.updated_at
        };
      }),
    [sessions, accountRows]
  );

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
      {/* Account table */}
      <section className="border border-hairline rounded-xl bg-surface-card p-4">
        <PanelHeader icon={<Wallet size={16} />} title="账户详情" />
        {accounts.length === 0 ? (
          <EmptyState
            title="暂无账户"
            description="创建账户后展示账户与 Provider 绑定。"
          />
        ) : (
          <div className="mt-2 max-h-[400px] overflow-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-text-muted text-xs border-b border-hairline">
                  <th className="pb-2 font-medium">账户</th>
                  <th className="pb-2 font-medium">初始资金</th>
                  <th className="pb-2 font-medium">Session</th>
                  <th className="pb-2 font-medium">运行中</th>
                </tr>
              </thead>
              <tbody>
                {accountRows.map((row) => (
                  <tr key={row.id} className="border-b border-hairline/50">
                    <td className="py-2 text-text-on-dark">{row.name}</td>
                    <td className="py-2 text-text-on-dark">
                      {formatMoney(row.initial_cash)}
                    </td>
                    <td className="py-2 text-text-muted">{row.sessionCount}</td>
                    <td className="py-2 text-text-muted">{row.runningSessions}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Session table */}
      <section className="border border-hairline rounded-xl bg-surface-card p-4">
        <PanelHeader icon={<MessageSquare size={16} />} title="Session 列表" />
        {sessions.length === 0 ? (
          <EmptyState
            title="暂无 Session"
            description="创建 Session 后展示真实会话状态。"
          />
        ) : (
          <div className="mt-2 max-h-[400px] overflow-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-text-muted text-xs border-b border-hairline">
                  <th className="pb-2 font-medium">Session</th>
                  <th className="pb-2 font-medium">账户</th>
                  <th className="pb-2 font-medium">模型</th>
                  <th className="pb-2 font-medium">Provider</th>
                  <th className="pb-2 font-medium">状态</th>
                  <th className="pb-2 font-medium">更新时间</th>
                </tr>
              </thead>
              <tbody>
                {sessionRows.map((row) => (
                  <tr key={row.id} className="border-b border-hairline/50">
                    <td className="py-2 text-text-on-dark">{row.name}</td>
                    <td className="py-2 text-text-muted">{row.accountName}</td>
                    <td className="py-2 text-text-muted">{row.model}</td>
                    <td className="py-2 text-text-muted">{providerName(row.providerId)}</td>
                    <td className="py-2 text-text-muted">
                      {statusLabel(row.status)}
                    </td>
                    <td className="py-2 text-text-muted">
                      {humanTime(row.lastRunAt)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  MarketDataPanel                                                   */
/* ------------------------------------------------------------------ */

function MarketDataPanel() {
  const marketForm = useMarketStore((s) => s.marketForm);
  const setMarketForm = useMarketStore((s) => s.setMarketForm);
  const marketQuote = useMarketStore((s) => s.marketQuote);
  const marketHistory = useMarketStore((s) => s.marketHistory);
  const queryQuote = useMarketStore((s) => s.queryQuote);
  const queryHistory = useMarketStore((s) => s.queryHistory);

  const closeValues = useMemo(
    () =>
      marketHistory?.bars
        .map(barClose)
        .filter((v): v is number => v != null) ?? [],
    [marketHistory]
  );

  const handleQueryQuote = () => {
    if (!marketForm.symbol.trim()) return;
    void queryQuote(marketForm.symbol.trim());
  };

  const handleQueryHistory = (e: React.FormEvent) => {
    e.preventDefault();
    if (!marketForm.symbol.trim()) return;
    void queryHistory(
      marketForm.symbol.trim(),
      marketForm.start || undefined,
      marketForm.end || undefined,
      marketForm.adjust || undefined,
      marketForm.allowFetchMissing
    );
  };

  return (
    <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
      {/* Query Form */}
      <section className="border border-hairline rounded-xl bg-surface-card p-4 xl:col-span-2">
        <PanelHeader icon={<LineChart size={16} />} title="行情查询" />
        <form className="flex flex-wrap items-end gap-3 mt-2" onSubmit={handleQueryHistory}>
          <div className="flex-1 min-w-[120px]">
            <Input
              label="股票代码"
              value={marketForm.symbol}
              onChange={(e) =>
                setMarketForm({ ...marketForm, symbol: e.target.value })
              }
              placeholder="输入股票代码"
            />
          </div>
          <Input
            label="起始日期"
            type="date"
            value={marketForm.start}
            onChange={(e) =>
              setMarketForm({ ...marketForm, start: e.target.value })
            }
          />
          <Input
            label="结束日期"
            type="date"
            value={marketForm.end}
            onChange={(e) =>
              setMarketForm({ ...marketForm, end: e.target.value })
            }
          />
          <div className="min-w-[110px]">
            <label className="grid gap-1.5 text-xs text-text-muted">
              复权
              <Select
                value={marketForm.adjust}
                onChange={(e) =>
                  setMarketForm({ ...marketForm, adjust: e.target.value })
                }
              >
                <option value="">不复权</option>
                <option value="qfq">前复权</option>
                <option value="hfq">后复权</option>
              </Select>
            </label>
          </div>
          <label className="flex items-center gap-2 h-10 px-3 rounded-lg border border-hairline bg-surface-card text-text-on-dark text-sm cursor-pointer">
            <input
              type="checkbox"
              checked={marketForm.allowFetchMissing}
              onChange={(e) =>
                setMarketForm({
                  ...marketForm,
                  allowFetchMissing: e.target.checked
                })
              }
              className="accent-brand-primary"
            />
            允许缺失拉取
          </label>
          <div className="flex gap-2">
            <Button
              variant="secondary"
              size="sm"
              icon={<Activity size={14} />}
              type="button"
              disabled={!marketForm.symbol.trim()}
              onClick={handleQueryQuote}
            >
              查询行情
            </Button>
            <Button
              variant="primary"
              size="sm"
              icon={<LineChart size={14} />}
              type="submit"
              disabled={!marketForm.symbol.trim()}
            >
              查询历史
            </Button>
          </div>
        </form>
      </section>

      {/* Quote Snapshot */}
      <section className="border border-hairline rounded-xl bg-surface-card p-4">
        <PanelHeader icon={<Activity size={16} />} title="行情快照" />
        {marketQuote ? (
          <div className="mt-2">
            <InfoGrid items={objectEntries(marketQuote).slice(0, 10)} />
          </div>
        ) : (
          <EmptyState
            title="暂无行情"
            description="输入股票代码后调用 /api/market/quote。"
          />
        )}
      </section>

      {/* History */}
      <section className="border border-hairline rounded-xl bg-surface-card p-4">
        <PanelHeader icon={<LineChart size={16} />} title="历史行情" />
        {marketHistory ? (
          <div className="mt-2">
            <InfoGrid
              items={[
                ["股票代码", marketHistory.symbol],
                ["周期", marketHistory.interval],
                ["复权", marketHistory.adjust || "不复权"],
                ["缓存命中", String(marketHistory.cache_hit)],
                ["记录数", String(marketHistory.bars.length)]
              ]}
            />
            {closeValues.length > 1 && <MiniLineChart values={closeValues} />}
            <MarketBarsTable bars={marketHistory.bars} />
          </div>
        ) : (
          <EmptyState
            title="暂无历史"
            description="查询历史行情后展示 K 线数据。"
          />
        )}
      </section>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  MiniLineChart                                                     */
/* ------------------------------------------------------------------ */

function MiniLineChart({ values }: { values: number[] }) {
  const points = linePoints(values, 100, 52);

  return (
    <svg
      className="w-full max-w-[360px] h-[52px] mt-2"
      viewBox="0 0 100 52"
      role="img"
      aria-label="数据曲线"
    >
      <polyline
        points={points}
        fill="none"
        stroke="var(--color-trading-rise)"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/* ------------------------------------------------------------------ */
/*  MarketBarsTable                                                   */
/* ------------------------------------------------------------------ */

function MarketBarsTable({ bars }: { bars: Record<string, unknown>[] }) {
  if (bars.length === 0) return null;

  return (
    <div className="mt-3 max-h-[300px] overflow-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-text-muted text-xs border-b border-hairline">
            <th className="pb-2 font-medium sticky top-0 bg-surface-card">时间</th>
            <th className="pb-2 font-medium sticky top-0 bg-surface-card">开</th>
            <th className="pb-2 font-medium sticky top-0 bg-surface-card">高</th>
            <th className="pb-2 font-medium sticky top-0 bg-surface-card">低</th>
            <th className="pb-2 font-medium sticky top-0 bg-surface-card">收</th>
            <th className="pb-2 font-medium sticky top-0 bg-surface-card">量</th>
            <th className="pb-2 font-medium sticky top-0 bg-surface-card">额</th>
          </tr>
        </thead>
        <tbody>
          {bars.slice(0, 16).map((bar, i) => (
            <tr key={`${barTime(bar)}-${i}`} className="border-b border-hairline/50">
              <td className="py-1.5 text-text-on-dark font-mono text-xs">
                {barTime(bar)}
              </td>
              <td className="py-1.5 text-text-muted">{formatValue(bar.open)}</td>
              <td className="py-1.5 text-text-muted">{formatValue(bar.high)}</td>
              <td className="py-1.5 text-text-muted">{formatValue(bar.low)}</td>
              <td className="py-1.5 text-text-on-dark">{formatValue(bar.close)}</td>
              <td className="py-1.5 text-text-muted">{formatValue(bar.volume)}</td>
              <td className="py-1.5 text-text-muted">{formatValue(bar.amount)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  PlaceholderSection                                                */
/* ------------------------------------------------------------------ */

function PlaceholderSection({
  title,
  description
}: {
  title: string;
  description: string;
}) {
  return (
    <section className="border border-hairline rounded-xl bg-surface-card p-4">
      <PanelHeader title={title} icon={<Activity size={16} />} />
      <EmptyState title="功能占位" description={description} />
    </section>
  );
}

function viewTabDesc(tab: string): string {
  return (
    {
      交易历史: "后端尚未提供交易历史接口。",
      资产曲线: "后端尚未接入模拟交易账本和资产曲线接口。",
      决策日志: "后端尚未提供决策日志聚合接口。",
      时间线控制: "后端尚未提供模拟时间线控制接口。"
    }[tab] ?? "查看子页面"
  );
}
