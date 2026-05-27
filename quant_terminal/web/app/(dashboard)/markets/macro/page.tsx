import { PageScaffold } from "@/components/widgets/PageScaffold";

export default function Page() {
  return (
    <PageScaffold
      number="02"
      title="Macro & Regime"
      subtitle="Cross-asset regime snapshot · VIX term · correlations · liquidity"
      meta="MARKETS / MAC"
      panels={[
        { title: "Macro snapshot", endpoints: ["GET /api/regime/macro (Phase 5)"] },
        { title: "VIX term structure", endpoints: ["yfinance live (Phase 5)"] },
        { title: "Correlation matrix", endpoints: ["lazy ECharts heatmap (Phase 5)"] },
      ]}
    />
  );
}
