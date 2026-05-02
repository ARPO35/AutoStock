import { useEffect, useRef } from "react";
import { createChart, ColorType, CandlestickSeries, HistogramSeries } from "lightweight-charts";
import { InfoGrid, RawJson } from "@/components/ui/Shared";
import { formatValue } from "@/lib/utils";

export function MarketHistoryChartRenderer({
  data,
  bars
}: {
  data: Record<string, unknown>;
  bars: Record<string, unknown>[];
}) {
  const chartRef = useRef<HTMLDivElement>(null);
  const symbol = formatValue(data.symbol ?? "--");
  const interval = formatValue(data.interval ?? "--");
  const adjust = formatValue(data.adjust ?? "--");

  useEffect(() => {
    if (!chartRef.current || bars.length === 0) return;

    const chart = createChart(chartRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#707a8a"
      },
      grid: {
        vertLines: { color: "rgba(43, 49, 57, 0.5)" },
        horzLines: { color: "rgba(43, 49, 57, 0.5)" }
      },
      width: chartRef.current.clientWidth,
      height: 280,
      timeScale: {
        borderColor: "#2b3139",
        timeVisible: true
      },
      rightPriceScale: {
        borderColor: "#2b3139"
      },
      crosshair: {
        vertLine: { color: "#fcd53533" },
        horzLine: { color: "#fcd53533" }
      }
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#0ecb81",
      downColor: "#f6465d",
      borderUpColor: "#0ecb81",
      borderDownColor: "#f6465d",
      wickUpColor: "#0ecb81",
      wickDownColor: "#f6465d"
    });

    const candleData = bars
      .map((bar) => {
        const time = bar.datetime ?? bar.date ?? bar.time ?? bar["日期"];
        const open = Number(bar.open ?? bar["开盘"]);
        const high = Number(bar.high ?? bar["最高"]);
        const low = Number(bar.low ?? bar["最低"]);
        const close = Number(bar.close ?? bar["收盘"]);
        if (
          !time ||
          !Number.isFinite(open) ||
          !Number.isFinite(high) ||
          !Number.isFinite(low) ||
          !Number.isFinite(close)
        )
          return null;
        return {
          time: String(time),
          open,
          high,
          low,
          close
        };
      })
      .filter((d): d is NonNullable<typeof d> => d !== null)
      .sort(
        (a, b) =>
          new Date(a.time).getTime() - new Date(b.time).getTime()
      );

    candleSeries.setData(candleData);

    const volumeSeries = chart.addSeries(HistogramSeries, {
      color: "rgba(252, 213, 53, 0.35)",
      priceFormat: { type: "volume" },
      priceScaleId: "volume"
    });

    const volumeData = bars
      .map((bar) => {
        const time = bar.datetime ?? bar.date ?? bar.time ?? bar["日期"];
        const volume = Number(bar.volume ?? bar["成交量"]);
        if (!time || !Number.isFinite(volume)) return null;
        return { time: String(time), value: volume };
      })
      .filter((d): d is NonNullable<typeof d> => d !== null);

    volumeSeries.setData(volumeData);
    chart.priceScale("volume").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });

    const handleResize = () => {
      if (chartRef.current) {
        chart.applyOptions({ width: chartRef.current.clientWidth });
      }
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
    };
  }, [bars]);

  return (
    <div className="mt-2 p-2.5 border border-hairline rounded-lg bg-surface-canvas/40">
      <div className="mb-2">
        <InfoGrid
          items={[
            ["股票代码", symbol],
            ["周期", interval],
            ["复权", adjust],
            ["记录数", String(bars.length)]
          ]}
        />
      </div>
      {bars.length > 0 ? (
        <div ref={chartRef} className="w-full" />
      ) : (
        <p className="text-text-muted text-sm">暂无行情数据</p>
      )}
      <RawJson data={data} />
    </div>
  );
}
