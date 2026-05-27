import { PageScaffold } from '@/components/widgets/PageScaffold';

export default function Page() {
  return (
    <PageScaffold
      number="14"
      title="Smart Money"
      subtitle="SEC 13F filings + Form 4 insider transactions + analyst rating changes"
      meta="DECISION / SMT"
      panels={[
        { title: 'GET /api/smart-money/{ticker} (Phase 5)', endpoints: ['GET /api/smart-money/{ticker} (Phase 5)'] },
      ]}
    />
  );
}
