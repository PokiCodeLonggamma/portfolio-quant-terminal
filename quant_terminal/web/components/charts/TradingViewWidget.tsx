"use client";
import { useEffect, useRef } from "react";

/**
 * TradingView Advanced Chart embed (free iframe widget).
 *
 * Port of src/viz/tv_chart.py: resolves logical → TV symbol heuristically
 * (CME_MINI:ES1!, NYMEX:CL1!, COMEX:GC1!, …) when not provided directly.
 */
const _YF_FUTURES_TO_TV: Record<string, string> = {
  ES: "CME_MINI:ES1!", NQ: "CME_MINI:NQ1!", YM: "CBOT_MINI:YM1!",
  RTY: "CME_MINI:RTY1!", MES: "CME_MINI:MES1!", MNQ: "CME_MINI:MNQ1!",
  VX: "CBOE:VX1!", VIX: "CBOE:VIX",
  CL: "NYMEX:CL1!", MCL: "NYMEX:MCL1!", NG: "NYMEX:NG1!",
  GC: "COMEX:GC1!", SI: "COMEX:SI1!", HG: "COMEX:HG1!",
  BTC: "CME:BTC1!", ETH: "CME:ETH1!",
  FDAX: "EUREX:FDAX1!", FESX: "EUREX:FESX1!", FCE: "MATIF:FCE1!",
  SPY: "AMEX:SPY", QQQ: "NASDAQ:QQQ", IWM: "AMEX:IWM", DIA: "AMEX:DIA",
};

export function resolveTvSymbol(logicalOrSymbol: string): string {
  const upper = logicalOrSymbol.toUpperCase();
  if (_YF_FUTURES_TO_TV[upper]) return _YF_FUTURES_TO_TV[upper];
  // crypto pair fallback
  if (upper.endsWith("-USD")) {
    return `COINBASE:${upper.replace("-", "")}`;
  }
  // bare ticker → assume US listing
  return upper;
}

export type TradingViewWidgetProps = {
  /** Either a logical key ("ES") or a full TV symbol ("CME_MINI:ES1!"). */
  symbol: string;
  /** D | W | M | 1 | 5 | 15 | 60 | 240 */
  interval?: string;
  height?: number;
  studies?: string[];
};

export function TradingViewWidget({
  symbol,
  interval = "D",
  height = 600,
  studies = ["STD;VWAP", "STD;EMA", "STD;RSI"],
}: TradingViewWidgetProps) {
  const ref = useRef<HTMLDivElement | null>(null);
  const containerId = useRef(`tv_${Math.random().toString(36).slice(2, 10)}`);

  useEffect(() => {
    if (!ref.current) return;
    const resolved = symbol.includes(":") ? symbol : resolveTvSymbol(symbol);
    // Inject the TV loader script once
    const SCRIPT_SRC = "https://s3.tradingview.com/tv.js";
    let script: HTMLScriptElement | null = document.querySelector(
      `script[src="${SCRIPT_SRC}"]`,
    );
    const mount = () => {
      // @ts-expect-error TradingView injects this global
      if (typeof TradingView === "undefined" || !ref.current) return;
      // @ts-expect-error
      new TradingView.widget({
        autosize: true,
        symbol: resolved,
        interval,
        timezone: "Etc/UTC",
        theme: "dark",
        style: "1",
        locale: "en",
        enable_publishing: false,
        withdateranges: true,
        hide_side_toolbar: false,
        allow_symbol_change: true,
        container_id: containerId.current,
        studies,
        toolbar_bg: "#0F1525",
        backgroundColor: "#0A0E1A",
        gridColor: "#1F2B45",
      });
    };
    if (script) {
      mount();
    } else {
      script = document.createElement("script");
      script.src = SCRIPT_SRC;
      script.async = true;
      script.onload = mount;
      document.head.appendChild(script);
    }
    return () => {
      if (ref.current) ref.current.innerHTML = "";
    };
  }, [symbol, interval, studies]);

  return (
    <div
      className="tradingview-widget-container"
      style={{ height, width: "100%" }}
    >
      <div ref={ref} id={containerId.current} style={{ height: "100%", width: "100%" }} />
    </div>
  );
}
