import { PageScaffold } from "@/components/widgets/PageScaffold";

export default function Page() {
  return (
    <PageScaffold
      number="01"
      title="Cross-Asset Universe"
      subtitle="CDC §1 · 99 contracts × 10 asset classes · clickable drilldown to TradingView"
      meta="MARKETS / CRS"
      panels={[
        { title: "Asset class grid", description: "10 classes × N contracts", endpoints: ["GET /api/universe"] },
        { title: "Daily heatmap", description: "1d/5d % across the universe", endpoints: ["GET /api/cross-asset/heatmap"] },
        { title: "Flagship board", description: "ES, NQ, CL, GC, BTC, FDAX, …", endpoints: ["POST /api/cross-asset/quotes"] },
      ]}
    />
  );
}
