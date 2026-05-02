import { Metric, InfoGrid } from "@/components/ui/Shared";
import { formatValue, objectEntries } from "@/lib/utils";

export function PortfolioStateRenderer({ data }: { data: Record<string, unknown> }) {
  const totalAssets = formatValue(
    data.total_assets ?? data.totalAssets ?? data["总资产"]
  );
  const cash = formatValue(data.cash ?? data.available ?? data["现金"] ?? data["可用资金"]);
  const marketValue = formatValue(
    data.market_value ?? data.marketValue ?? data.holdings_value ?? data["持仓市值"]
  );
  const todayPnl = formatValue(
    data.today_pnl ?? data.todayPnl ?? data["今日收益"]
  );
  const totalPnl = formatValue(
    data.total_pnl ?? data.totalPnl ?? data["累计收益"]
  );
  const floatingPnl = formatValue(
    data.floating_pnl ?? data.floatingPnl ?? data.unrealized_pnl ?? data["浮动盈亏"]
  );
  const available = formatValue(
    data.available ?? data.available_cash ?? data["可用资金"]
  );
  const frozen = formatValue(
    data.frozen ?? data.frozen_cash ?? data["冻结资金"]
  );

  const hasKnownKeys = Object.keys(data).some((k) =>
    [
      "total_assets", "totalAssets", "总资产",
      "cash", "available", "现金",
      "market_value", "marketValue", "holdings_value", "持仓市值",
      "today_pnl", "todayPnl", "今日收益",
      "total_pnl", "totalPnl", "累计收益",
      "floating_pnl", "floatingPnl", "unrealized_pnl", "浮动盈亏",
      "available_cash", "可用资金",
      "frozen", "frozen_cash", "冻结资金"
    ].includes(k)
  );

  if (!hasKnownKeys) {
    return (
      <div className="mt-2">
        <InfoGrid items={objectEntries(data)} />
      </div>
    );
  }

  return (
    <div className="mt-2 grid grid-cols-2 gap-2">
      <Metric label="总资产" value={totalAssets} />
      <Metric label="现金" value={cash} />
      <Metric label="持仓市值" value={marketValue} />
      <Metric label="今日收益" value={todayPnl} />
      <Metric label="累计收益" value={totalPnl} />
      <Metric label="浮动盈亏" value={floatingPnl} />
      <Metric label="可用资金" value={available} />
      <Metric label="冻结资金" value={frozen} />
    </div>
  );
}
