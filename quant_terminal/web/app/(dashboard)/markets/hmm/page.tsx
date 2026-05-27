import { PageScaffold } from "@/components/widgets/PageScaffold";

export default function Page() {
  return (
    <PageScaffold
      number="03"
      title="HMM Regime"
      subtitle="3-state Gaussian HMM on log-returns — current regime + transition matrix"
      meta="MARKETS / HMM"
      panels={[
        { title: "Current regime — SPY", endpoints: ["GET /api/regime/hmm/SPY"] },
        { title: "Current regime — QQQ", endpoints: ["GET /api/regime/hmm/QQQ"] },
        { title: "Current regime — IWM", endpoints: ["GET /api/regime/hmm/IWM"] },
      ]}
    />
  );
}
