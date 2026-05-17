import { useEffect, useMemo, useRef, useState } from "react";
import { Maximize2, Minimize2 } from "lucide-react";
import {
  ColorType,
  CrosshairMode,
  LineSeries,
  createChart,
  createSeriesMarkers,
  type IChartApi,
  type LineData,
  type Time
} from "lightweight-charts";
import type { AssetPoint } from "@/api";
import { EmptyState } from "@/components/ui/Shared";
import { formatMoney, humanTime } from "@/lib/utils";

export type AssetChartValueMode = "asset" | "pnl_pct";

export interface AssetChartSeries {
  account_id: string;
  account_name: string;
  points: AssetPoint[];
  color?: string;
}

interface AssetValueChartProps {
  series: AssetChartSeries[];
  valueMode?: AssetChartValueMode;
  height?: number;
  compact?: boolean;
  showLegend?: boolean;
  emptyTitle?: string;
  emptyDescription?: string;
}

interface PreparedPoint {
  time: Time;
  point: AssetPoint;
  value: number;
}

interface PreparedSeries extends AssetChartSeries {
  color: string;
  data: LineData<Time>[];
  pointsByTime: Map<string, AssetPoint>;
}

interface TooltipState {
  x: number;
  y: number;
  rows: Array<{ series: PreparedSeries; point: AssetPoint; value: number }>;
}

const PALETTE = ["#fcd535", "#2dbdb6", "#3b82f6", "#f6465d", "#0ecb81", "#c084fc"];

export function AssetValueChart({
  series,
  valueMode = "asset",
  height = 320,
  compact = false,
  showLegend = true,
  emptyTitle = "曲线点不足",
  emptyDescription = "至少需要两个资产点。"
}: AssetValueChartProps) {
  const rootRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<HTMLDivElement>(null);
  const chartApiRef = useRef<IChartApi | null>(null);
  const hoverTimerRef = useRef<number | null>(null);
  const [tooltip, setTooltip] = useState<TooltipState | null>(null);
  const [fallbackFullscreen, setFallbackFullscreen] = useState(false);
  const [nativeFullscreen, setNativeFullscreen] = useState(false);

  const prepared = useMemo(
    () =>
      series
        .map((item, index) => prepareSeries(item, valueMode, item.color ?? PALETTE[index % PALETTE.length]))
        .filter((item) => item.data.length >= 2),
    [series, valueMode]
  );

  const fullscreen = nativeFullscreen || fallbackFullscreen;
  const chartHeight = fullscreen ? "calc(100vh - 84px)" : `${height}px`;

  useEffect(() => {
    const onFullscreenChange = () => {
      setNativeFullscreen(document.fullscreenElement === rootRef.current);
    };
    document.addEventListener("fullscreenchange", onFullscreenChange);
    return () => document.removeEventListener("fullscreenchange", onFullscreenChange);
  }, []);

  useEffect(() => {
    const container = chartRef.current;
    if (!container || prepared.length === 0) return;
    const clearHoverTimer = () => {
      if (hoverTimerRef.current) {
        window.clearTimeout(hoverTimerRef.current);
        hoverTimerRef.current = null;
      }
    };

    const chart = createChart(container, {
      width: container.clientWidth,
      height: container.clientHeight,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#929aa5"
      },
      grid: {
        vertLines: { color: "rgba(43, 49, 57, 0.65)" },
        horzLines: { color: "rgba(43, 49, 57, 0.65)" }
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: "rgba(252, 213, 53, 0.35)", labelBackgroundColor: "#2b3139" },
        horzLine: { color: "rgba(252, 213, 53, 0.35)", labelBackgroundColor: "#2b3139" }
      },
      rightPriceScale: {
        borderColor: "#2b3139",
        scaleMargins: { top: 0.12, bottom: 0.12 }
      },
      timeScale: {
        borderColor: "#2b3139",
        timeVisible: true,
        secondsVisible: false
      },
      handleScale: true,
      handleScroll: true
    });
    chartApiRef.current = chart;

    for (const item of prepared) {
      const line = chart.addSeries(LineSeries, {
        color: item.color,
        lineWidth: 1,
        crosshairMarkerVisible: true,
        crosshairMarkerRadius: 4,
        lastValueVisible: !compact,
        priceLineVisible: false,
        priceFormat:
          valueMode === "pnl_pct"
            ? { type: "custom", formatter: (value: number) => `${value.toFixed(2)}%` }
            : { type: "price", precision: 2, minMove: 0.01 }
      });
      line.setData(item.data);
      const markers = Array.from(item.pointsByTime.entries())
        .filter(([, point]) => point.source === "trade" && point.trade)
        .map(([time, point]) => ({
          time: Number(time) as Time,
          position: "inBar" as const,
          color: point.trade?.side === "sell" ? "#0ecb81" : "#f6465d",
          shape: "circle" as const,
          text: point.trade?.side === "sell" ? "卖" : "买"
        }));
      if (markers.length > 0) createSeriesMarkers(line, markers);
    }

    chart.timeScale().fitContent();

    const resize = () => {
      chart.applyOptions({
        width: container.clientWidth,
        height: container.clientHeight
      });
    };
    const observer = new ResizeObserver(resize);
    observer.observe(container);

    chart.subscribeCrosshairMove((param) => {
      if (!param.time || !param.point || param.point.x < 0 || param.point.y < 0) {
        clearHoverTimer();
        setTooltip(null);
        return;
      }
      const timeKey = String(param.time);
      const rows = prepared
        .map((item) => {
          const point = item.pointsByTime.get(timeKey);
          if (!point) return null;
          return { series: item, point, value: pointValue(point, valueMode) };
        })
        .filter((item): item is NonNullable<typeof item> => item !== null);
      if (rows.length === 0) {
        clearHoverTimer();
        setTooltip(null);
        return;
      }
      clearHoverTimer();
      hoverTimerRef.current = window.setTimeout(() => {
        setTooltip({ x: param.point?.x ?? 0, y: param.point?.y ?? 0, rows });
      }, 200);
    });

    return () => {
      clearHoverTimer();
      observer.disconnect();
      chart.remove();
      chartApiRef.current = null;
    };
  }, [compact, prepared, valueMode]);

  useEffect(() => {
    chartApiRef.current?.applyOptions({ height: chartRef.current?.clientHeight ?? height });
  }, [fullscreen, height]);

  const toggleFullscreen = async () => {
    if (fullscreen) {
      if (document.fullscreenElement === rootRef.current) {
        await document.exitFullscreen();
      }
      setFallbackFullscreen(false);
      return;
    }
    try {
      if (!rootRef.current?.requestFullscreen) throw new Error("fullscreen unsupported");
      await rootRef.current.requestFullscreen();
    } catch {
      setFallbackFullscreen(true);
    }
  };

  if (prepared.length === 0) return <EmptyState title={emptyTitle} description={emptyDescription} />;

  return (
    <div
      ref={rootRef}
      className={
        fallbackFullscreen
          ? "fixed inset-0 z-50 bg-surface-canvas p-4"
          : "relative min-w-0"
      }
    >
      <div className="mb-2 flex items-center justify-end">
        <button
          type="button"
          onClick={() => void toggleFullscreen()}
          className="grid h-8 w-8 place-items-center rounded-md border border-hairline bg-surface-canvas/80 text-text-muted transition-colors hover:border-brand-primary/50 hover:text-brand-primary"
          title={fullscreen ? "退出全屏" : "全屏查看"}
          aria-label={fullscreen ? "退出全屏" : "全屏查看"}
        >
          {fullscreen ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
        </button>
      </div>
      <div
        ref={chartRef}
        className="w-full min-w-0"
        style={{ height: chartHeight, minHeight: compact ? 180 : 240 }}
      />
      {tooltip && <AssetTooltip tooltip={tooltip} valueMode={valueMode} compact={compact} />}
      {showLegend && (
        <div className="mt-2 flex flex-wrap gap-3 text-xs text-text-muted">
          {prepared.map((item) => (
            <span key={item.account_id} className="inline-flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full" style={{ background: item.color }} />
              {item.account_name}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function AssetTooltip({
  tooltip,
  valueMode,
  compact
}: {
  tooltip: TooltipState;
  valueMode: AssetChartValueMode;
  compact: boolean;
}) {
  const anchor = tooltip.rows[0]?.point;
  const left = Math.min(Math.max(tooltip.x + 14, 8), window.innerWidth - 340);
  const top = Math.max(tooltip.y + 14, 8);
  const detailPoint = tooltip.rows.find((row) => row.point.trade || row.point.positions_recorded === false)?.point ?? anchor;
  return (
    <div
      className="pointer-events-none absolute z-20 w-[320px] max-w-[calc(100%-16px)] rounded-lg border border-hairline bg-surface-elevated/95 p-3 text-xs shadow-2xl shadow-black/30 backdrop-blur"
      style={{ left, top }}
    >
      <div className="mb-2 flex items-center justify-between gap-2 border-b border-hairline/70 pb-2">
        <strong className="text-text-on-dark">{humanTime(anchor?.time)}</strong>
        <span className="text-text-muted">{sourceLabel(anchor?.source)}</span>
      </div>
      <div className="grid gap-1.5">
        {tooltip.rows.map((row) => (
          <div key={row.series.account_id} className="grid grid-cols-[1fr_auto] gap-3">
            <span className="truncate text-text-muted">
              <span className="mr-1.5 inline-block h-2 w-2 rounded-full" style={{ background: row.series.color }} />
              {row.series.account_name}
            </span>
            <span className={toneClass(row.point.pnl ?? 0)}>
              {valueMode === "pnl_pct" ? `${row.value.toFixed(2)}%` : formatMoney(row.value)}
            </span>
          </div>
        ))}
      </div>
      {!compact && detailPoint && (
        <div className="mt-2 grid gap-2 border-t border-hairline/70 pt-2 text-text-muted">
          <div className="grid grid-cols-2 gap-x-3 gap-y-1">
            <span>总资产 {formatMoney(detailPoint.total_asset)}</span>
            <span className={toneClass(detailPoint.pnl ?? 0)}>盈亏 {formatMoney(detailPoint.pnl)}</span>
            <span>现金 {formatMoney(detailPoint.cash)}</span>
            <span>收益率 {formatPercent(detailPoint.pnl_pct)}</span>
          </div>
          {detailPoint.trade && (
            <div className="rounded-md bg-surface-canvas/70 p-2">
              <div className={detailPoint.trade.side === "sell" ? "fall" : "rise"}>
                {detailPoint.trade.side === "sell" ? "卖出" : "买入"} {stockLabel(detailPoint.trade.symbol, detailPoint.trade.name)}
              </div>
              <div className="mt-1 text-text-muted">
                {detailPoint.trade.quantity} 股 @ {detailPoint.trade.price} / 成交额 {formatMoney(detailPoint.trade.turnover)} / 费用 {formatMoney(detailPoint.trade.fee)}
              </div>
              <div className="mt-1 truncate text-text-muted">
                {detailPoint.trade.session_name ?? "未绑定 Session"} / {detailPoint.trade.model ?? detailPoint.trade.provider_name ?? "--"}
              </div>
            </div>
          )}
          <PositionsSummary point={detailPoint} />
        </div>
      )}
    </div>
  );
}

function PositionsSummary({ point }: { point: AssetPoint }) {
  if (point.positions_recorded === false) {
    return <div className="rounded-md bg-surface-canvas/70 p-2 text-text-muted">历史持仓明细未记录</div>;
  }
  if (!point.positions || point.positions.length === 0) {
    return <div className="rounded-md bg-surface-canvas/70 p-2 text-text-muted">无持仓</div>;
  }
  return (
    <div className="rounded-md bg-surface-canvas/70 p-2">
      <div className="mb-1 text-text-muted">历史持仓</div>
      <div className="grid gap-1">
        {point.positions.slice(0, 4).map((position) => (
          <div key={position.symbol} className="grid grid-cols-[1fr_auto] gap-2">
            <span className="truncate text-text-on-dark">{stockLabel(position.symbol, position.name)} x {position.quantity}</span>
            <span className={toneClass(position.unrealized_pnl)}>
              {formatMoney(position.unrealized_pnl)} / {formatPercent(position.unrealized_pnl_pct)}
            </span>
          </div>
        ))}
      </div>
      {point.positions.length > 4 && <div className="mt-1 text-text-muted">另有 {point.positions.length - 4} 只持仓</div>}
    </div>
  );
}

function prepareSeries(series: AssetChartSeries, valueMode: AssetChartValueMode, color: string): PreparedSeries {
  const seen = new Set<number>();
  const preparedPoints: PreparedPoint[] = series.points
    .map((point, index) => {
      const value = pointValue(point, valueMode);
      const baseTime = pointToSeconds(point.time);
      if (!Number.isFinite(value) || !Number.isFinite(baseTime)) return null;
      let time = baseTime;
      while (seen.has(time)) time += 1;
      seen.add(time);
      return {
        time: time as Time,
        point,
        value
      };
    })
    .filter((point): point is PreparedPoint => point !== null)
    .sort((a, b) => Number(a.time) - Number(b.time));
  const pointsByTime = new Map(preparedPoints.map((item) => [String(item.time), item.point]));
  return {
    ...series,
    color,
    data: preparedPoints.map((item) => ({ time: item.time, value: item.value })),
    pointsByTime
  };
}

function pointToSeconds(time: string): number {
  const parsed = new Date(time).getTime();
  return Number.isFinite(parsed) ? Math.floor(parsed / 1000) : 0;
}

function pointValue(point: AssetPoint, valueMode: AssetChartValueMode): number {
  return valueMode === "pnl_pct" ? Number(point.pnl_pct ?? 0) : Number(point.total_asset);
}

function formatPercent(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(Number(value))) return "--";
  return `${Number(value).toFixed(2)}%`;
}

function sourceLabel(source: string | undefined): string {
  if (source === "initial") return "初始";
  if (source === "trade") return "成交";
  if (source === "current") return "当前";
  if (source === "valuation") return "估值";
  return source ?? "--";
}

function toneClass(value: number): string {
  return value > 0 ? "rise" : value < 0 ? "fall" : "text-text-muted";
}

function stockLabel(symbol: string, name?: string | null): string {
  const code = symbol.match(/\d{6}/)?.[0] ?? symbol;
  const cleanName = name?.trim();
  return cleanName ? `${cleanName}（${code}）` : code;
}
