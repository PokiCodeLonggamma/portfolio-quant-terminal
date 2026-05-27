/** Home — KPI strip placeholders + nav cards.
 * The real Cross-Asset overview lives at /markets/cross-asset (wired in P5).
 */
import { SectionHeader } from "@/components/widgets/SectionHeader";
import { StatStrip } from "@/components/widgets/StatStrip";
import { PlaceholderPanel } from "@/components/widgets/PlaceholderPanel";

export default function Home() {
  return (
    <div className="p-6 md:p-10 mx-auto" style={{ maxWidth: 1520 }}>
      <SectionHeader
        sectionNumber="00"
        title="Quant Terminal"
        subtitle="Institutional cross-asset cockpit · Next.js + FastAPI · 17 routes · auth + cache + live ticks"
        meta="P4 shell"
      />

      <StatStrip
        items={[
          { label: "Status",  value: "OPERATIONAL",  hint: "All systems nominal",        accent: "mint" },
          { label: "Routes",  value: "17",           hint: "MARKETS · PORTFOLIO · TRADING · DECISION · LAB" },
          { label: "Endpoints", value: "19",         hint: "REST + 1 WS /ws/prices" },
          { label: "Build",   value: "P4 shell",     hint: "wired in P5 (tab-by-tab)", accent: "amber" },
        ]}
      />

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        <PlaceholderPanel
          title="Cross-Asset Overview"
          description="Heatmap + flagship contracts (ES, NQ, CL, GC, BTC, FDAX, …)"
          endpoints={["GET /api/cross-asset/heatmap", "GET /api/universe"]}
        />
        <PlaceholderPanel
          title="Portfolio Summary"
          description="NAV + Greeks + risk roll-up"
          endpoints={["GET /api/portfolio/summary"]}
        />
        <PlaceholderPanel
          title="Live Prices"
          description="WebSocket subscription to qt:prices Redis channel"
          endpoints={["WS /ws/prices  (subscribe / tick)"]}
        />
        <PlaceholderPanel
          title="Today's Catalysts"
          description="Earnings + macro events in the next 7 days"
          endpoints={["GET /api/catalysts/upcoming?horizon_days=7"]}
        />
        <PlaceholderPanel
          title="News Pulse"
          description="RSS aggregation + sentiment scoring"
          endpoints={["GET /api/news/latest"]}
        />
        <PlaceholderPanel
          title="HMM Regime — SPY"
          description="3-state Gaussian HMM on log-returns"
          endpoints={["GET /api/regime/hmm/SPY"]}
        />
      </div>
    </div>
  );
}
