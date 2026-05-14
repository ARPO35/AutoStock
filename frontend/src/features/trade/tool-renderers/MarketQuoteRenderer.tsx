import { RawJson } from "@/components/ui/Shared";
import { formatValue } from "@/lib/utils";

export function MarketQuoteRenderer({ data }: { data: Record<string, unknown> }) {
  const name = formatValue(data.name ?? data["名称"] ?? data.symbol ?? "--");
  const symbol = formatValue(data.symbol ?? "--");
  const stockLabel = name !== "--" && name !== symbol ? `${name}（${symbol}）` : symbol;
  const price = Number(data.price ?? data["最新价"]);
  const change = Number(data.change ?? data["涨跌额"]);
  const pctChange = Number(data.pct_change ?? data.change_percent ?? data["涨跌幅"]);
  const open = Number(data.open ?? data["开盘价"]);
  const high = Number(data.high ?? data["最高价"]);
  const low = Number(data.low ?? data["最低价"]);
  const amount = Number(data.amount ?? data["成交额"]);

  const changeSign = change > 0 ? "+" : change < 0 ? "" : "";
  const pctSign = pctChange > 0 ? "+" : pctChange < 0 ? "" : "";

  const toneClass =
    change > 0 ? "rise" : change < 0 ? "fall" : "flat";

  return (
    <div className="mt-2 p-2.5 border border-hairline rounded-lg bg-surface-canvas/40">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
        <strong className="text-text-on-dark">
          {stockLabel}
        </strong>
        <span className="text-text-on-dark">
          ¥{Number.isFinite(price) ? price.toFixed(2) : "--"}
        </span>
        <span className={toneClass}>
          {Number.isFinite(change) ? `${changeSign}${change.toFixed(2)}` : "--"}
        </span>
        <span className={toneClass}>
          {Number.isFinite(pctChange)
            ? `${pctSign}${pctChange.toFixed(2)}%`
            : "--"}
        </span>
        <span className="text-text-muted">
          今开 {Number.isFinite(open) ? open.toFixed(2) : "--"}
        </span>
        <span className="text-text-muted">
          最高 {Number.isFinite(high) ? high.toFixed(2) : "--"}
        </span>
        <span className="text-text-muted">
          最低 {Number.isFinite(low) ? low.toFixed(2) : "--"}
        </span>
        <span className="text-text-muted">
          成交额{" "}
          {Number.isFinite(amount)
            ? amount >= 1e8
              ? `${(amount / 1e8).toFixed(2)}亿`
              : amount.toFixed(0)
            : "--"}
        </span>
      </div>
      <RawJson data={data} />
    </div>
  );
}
