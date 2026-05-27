import { PageScaffold } from '@/components/widgets/PageScaffold';

export default function Page() {
  return (
    <PageScaffold
      number="10"
      title="Trading Bench"
      subtitle="Chains, GEX, vol surface, IV term, smile, trade ticket"
      meta="TRADING / TRD"
      panels={[
        { title: 'GET /api/options/{tk}/chain', endpoints: ['GET /api/options/{tk}/chain'] },
        { title: 'GET /api/options/{tk}/gex', endpoints: ['GET /api/options/{tk}/gex'] },
        { title: 'GET /api/options/{tk}/vol_surface', endpoints: ['GET /api/options/{tk}/vol_surface'] },
        { title: 'GET /api/options/{tk}/iv_term_structure', endpoints: ['GET /api/options/{tk}/iv_term_structure'] },
      ]}
    />
  );
}
