import { PageScaffold } from "@/components/widgets/PageScaffold";

export default function Page() {
  return (
    <PageScaffold
      number="05"
      title="Catalysts & News"
      subtitle="Upcoming earnings + macro events + real-time news pulse"
      meta="MARKETS / CAT"
      panels={[
        { title: "Upcoming events (30d)", endpoints: ["GET /api/catalysts/upcoming?horizon_days=30"] },
        { title: "News pulse (6h)", endpoints: ["GET /api/news/latest"] },
        { title: "Sentiment timeline", endpoints: ["Phase 5: aggregate by hour"] },
      ]}
    />
  );
}
