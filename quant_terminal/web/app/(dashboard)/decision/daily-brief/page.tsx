import { PageScaffold } from '@/components/widgets/PageScaffold';

export default function Page() {
  return (
    <PageScaffold
      number="15"
      title="Daily Brief"
      subtitle="LLM-generated morning summary · positions · catalysts · news · regime"
      meta="DECISION / BRF"
      panels={[
        { title: 'GET /api/daily-brief (Phase 5)', endpoints: ['GET /api/daily-brief (Phase 5)'] },
      ]}
    />
  );
}
