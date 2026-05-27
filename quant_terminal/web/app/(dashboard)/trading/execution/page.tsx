import { PageScaffold } from '@/components/widgets/PageScaffold';

export default function Page() {
  return (
    <PageScaffold
      number="12"
      title="Execution"
      subtitle="Alpaca paper / live (LATCH=0 by default — submit blocked)"
      meta="TRADING / EXE"
      panels={[
        { title: 'POST /api/execution/orders (Phase 5)', endpoints: ['POST /api/execution/orders (Phase 5)'] },
        { title: 'GET /api/execution/positions (Phase 5)', endpoints: ['GET /api/execution/positions (Phase 5)'] },
      ]}
    />
  );
}
