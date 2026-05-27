import { PageScaffold } from '@/components/widgets/PageScaffold';

export default function Page() {
  return (
    <PageScaffold
      number="17"
      title="Backtest"
      subtitle="Strategy backtest runner + equity/drawdown curves + metrics"
      meta="LAB / BKT"
      panels={[
        { title: 'POST /api/backtest/run (Phase 5)', endpoints: ['POST /api/backtest/run (Phase 5)'] },
      ]}
    />
  );
}
