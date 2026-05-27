import { PageScaffold } from "@/components/widgets/PageScaffold";

export default function Page() {
  return (
    <PageScaffold
      number="07"
      title="Portfolio Greeks"
      subtitle="Aggregate Δ Γ Θ Vega across all open option positions"
      meta="PORTFOLIO / GRK"
      panels={[
        { title: "Greeks roll-up", endpoints: ["GET /api/portfolio/greeks (Phase 5)"] },
        { title: "Per-position breakdown", endpoints: ["Phase 5"] },
        { title: "Greek sensitivity heatmap", endpoints: ["Phase 5 (ECharts)"] },
      ]}
    />
  );
}
