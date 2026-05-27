"use client";
import dynamic from "next/dynamic";
import type { EChartsOption } from "echarts";

// echarts ~1MB. Lazy-load + no SSR.
const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });

export function EChart({ option, height = 420 }: { option: EChartsOption; height?: number }) {
  return (
    <ReactECharts
      option={option}
      style={{ width: "100%", height }}
      theme="dark"
      opts={{ renderer: "canvas" }}
    />
  );
}
