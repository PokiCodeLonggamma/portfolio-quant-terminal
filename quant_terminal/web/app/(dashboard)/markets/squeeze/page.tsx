import { PageScaffold } from "@/components/widgets/PageScaffold";

export default function Page() {
  return (
    <PageScaffold
      number="04"
      title="Short Squeeze Scanner"
      subtitle="SEC SHO threshold list + Finviz short interest + 4-pillar composite score"
      meta="MARKETS / SQZ"
      panels={[
        { title: "Top-20 candidates", endpoints: ["GET /api/scanners/squeeze?limit=20"] },
        { title: "SHO threshold list", endpoints: ["worker job — every hour"] },
        { title: "Composite scoring", endpoints: ["short_pct × DTC × CTB × util"] },
      ]}
    />
  );
}
