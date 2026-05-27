import { PageScaffold } from "@/components/widgets/PageScaffold";

export default function Page() {
  return (
    <PageScaffold
      number="06"
      title="Holdings"
      subtitle="DEGIRO-uploaded portfolio · NAV · per-position breakdown by theme/region"
      meta="PORTFOLIO / HLD"
      panels={[
        { title: "NAV + position count", endpoints: ["GET /api/portfolio/summary"] },
        { title: "Holdings table", endpoints: ["GET /api/portfolio/summary"] },
        { title: "Upload DEGIRO CSV", endpoints: ["POST /api/portfolio/upload (Phase 5)"] },
      ]}
    />
  );
}
