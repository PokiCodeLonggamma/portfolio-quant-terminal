import { PageScaffold } from '@/components/widgets/PageScaffold';

export default function Page() {
  return (
    <PageScaffold
      number="09"
      title="Tax (2074-CMV)"
      subtitle="FIFO lots reconciliation + French tax 2074 form export"
      meta="PORTFOLIO / TAX"
      panels={[
        { title: 'GET /api/tax/lots (Phase 5)', endpoints: ['GET /api/tax/lots (Phase 5)'] },
        { title: 'GET /api/tax/2074 (Phase 5)', endpoints: ['GET /api/tax/2074 (Phase 5)'] },
      ]}
    />
  );
}
