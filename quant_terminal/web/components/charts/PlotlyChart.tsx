"use client";
import dynamic from "next/dynamic";
import type { Data, Layout } from "plotly.js";

// Plotly is heavy (~500KB). Lazy-load + no SSR.
const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

export function PlotlyChart({
  data,
  layout,
  height = 380,
}: {
  data: Data[];
  layout?: Partial<Layout>;
  height?: number;
}) {
  return (
    <Plot
      data={data}
      layout={{
        autosize: true,
        paper_bgcolor: "var(--color-ink)",
        plot_bgcolor: "var(--color-ink)",
        font: { family: '"JetBrains Mono", monospace', color: "var(--color-bone-muted)", size: 11 },
        margin: { l: 50, r: 30, t: 40, b: 50 },
        ...layout,
      }}
      style={{ width: "100%", height }}
      config={{ displayModeBar: false, responsive: true }}
    />
  );
}
