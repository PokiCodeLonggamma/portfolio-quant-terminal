import { PageScaffold } from '@/components/widgets/PageScaffold';

export default function Page() {
  return (
    <PageScaffold
      number="13"
      title="Conviction Matrix"
      subtitle="Per-position conviction score · thesis · downside · liquidity · catalyst"
      meta="DECISION / CNV"
      panels={[
        { title: 'GET /api/decision/conviction (Phase 5)', endpoints: ['GET /api/decision/conviction (Phase 5)'] },
      ]}
    />
  );
}
