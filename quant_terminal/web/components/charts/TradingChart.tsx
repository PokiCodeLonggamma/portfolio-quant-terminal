"use client";
import { useEffect, useRef } from "react";

import type { CandlestickData, Time } from "lightweight-charts";

export type CandleSeries = Array<{
  time: string; // ISO date "2026-05-27"
  open: number;
  high: number;
  low: number;
  close: number;
}>;

export function TradingChart({ candles, height = 380 }: { candles: CandleSeries; height?: number }) {
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    let chart: { remove: () => void } | null = null;
    let resizeObserver: ResizeObserver | null = null;
    // Dynamic import so the lib only loads client-side.
    (async () => {
      const lwc = await import("lightweight-charts");
      const c = lwc.createChart(ref.current!, {
        layout: {
          background: { type: lwc.ColorType.Solid, color: "#0A0A0F" },
          textColor: "#B8B5AC",
          fontFamily: '"JetBrains Mono", monospace',
        },
        grid: {
          horzLines: { color: "#2A2A38" },
          vertLines: { color: "#2A2A38" },
        },
        width: ref.current!.clientWidth,
        height,
        rightPriceScale: { borderColor: "#4A4A60" },
        timeScale: { borderColor: "#4A4A60", timeVisible: true },
      });
      // lightweight-charts v5 API: addSeries(SeriesType, options)
      const series = c.addSeries(lwc.CandlestickSeries, {
        upColor: "#2EE89E",
        downColor: "#FF3838",
        borderUpColor: "#2EE89E",
        borderDownColor: "#FF3838",
        wickUpColor: "#2EE89E",
        wickDownColor: "#FF3838",
      });
      series.setData(candles as unknown as CandlestickData<Time>[]);
      c.timeScale().fitContent();
      chart = c;
      resizeObserver = new ResizeObserver(() => {
        if (ref.current) c.applyOptions({ width: ref.current.clientWidth });
      });
      resizeObserver.observe(ref.current!);
    })();
    return () => {
      try {
        resizeObserver?.disconnect();
        chart?.remove();
      } catch {
        // noop
      }
    };
  }, [candles, height]);

  return <div ref={ref} style={{ width: "100%", height }} />;
}
