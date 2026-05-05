import type { ToolResultPayload } from "@/types";
import { InfoGrid } from "@/components/ui/Shared";
import { objectEntries } from "@/lib/utils";
import { MarketQuoteRenderer } from "@/features/trade/tool-renderers/MarketQuoteRenderer";
import { MarketHistoryChartRenderer } from "@/features/trade/tool-renderers/MarketHistoryChartRenderer";
import { TavilySearchRenderer } from "@/features/trade/tool-renderers/TavilySearchRenderer";
import { PortfolioStateRenderer } from "@/features/trade/tool-renderers/PortfolioStateRenderer";
import { OrderResultRenderer } from "@/features/trade/tool-renderers/OrderResultRenderer";

export function ToolResultRenderer({
  payload,
  toolName
}: {
  payload: ToolResultPayload;
  toolName?: string | null;
}) {
  if (payload.kind === "quote") {
    return <MarketQuoteRenderer data={payload.quote} />;
  }

  if (payload.kind === "history") {
    return (
      <MarketHistoryChartRenderer
        data={payload.history}
        bars={payload.bars}
      />
    );
  }

  if (payload.kind === "fetch-history") {
    return (
      <div className="p-2.5 border border-hairline rounded-lg bg-surface-canvas/40">
        <strong className="block text-text-on-dark text-sm mb-2">
          数据拉取结果
        </strong>
        <InfoGrid items={objectEntries(payload.stats)} />
      </div>
    );
  }

  if (payload.kind === "order-result") {
    return <OrderResultRenderer data={payload.data} />;
  }

  if (
    payload.kind === "portfolio-state" ||
    payload.kind === "portfolio-positions" ||
    payload.kind === "portfolio-orders" ||
    payload.kind === "portfolio-trades"
  ) {
    return <PortfolioStateRenderer data={payload.data} />;
  }

  if (payload.kind === "tavily") {
    return <TavilySearchRenderer data={payload.data} />;
  }

  const name = (toolName ?? "").toLowerCase();

  if (name === "tavily_search" || name.includes("tavily")) {
    return <TavilySearchRenderer data={payload.data} />;
  }

  if (
    name.includes("portfolio") ||
    name.includes("account") ||
    name.includes("balance") ||
    name.includes("position")
  ) {
    return <PortfolioStateRenderer data={payload.data} />;
  }

  if (
    name.includes("order") ||
    name.includes("trade") ||
    name.includes("下单") ||
    name.includes("买入") ||
    name.includes("卖出")
  ) {
    return <OrderResultRenderer data={payload.data} />;
  }

  return (
    <div className="mt-2 p-2.5 border border-hairline rounded-lg bg-surface-canvas/40">
      <strong className="block text-text-on-dark text-sm mb-2">
        {payload.title}
      </strong>
      <InfoGrid items={objectEntries(payload.data ?? {}).slice(0, 8)} />
    </div>
  );
}
