import { PageScaffold } from '@/components/widgets/PageScaffold';

export default function Page() {
  return (
    <PageScaffold
      number="08"
      title="Daily Snapshot"
      subtitle="Capture daily NAV / replay any past day"
      meta="PORTFOLIO / SNP"
      panels={[
        { title: 'GET /api/snapshot/{date} (Phase 5)', endpoints: ['GET /api/snapshot/{date} (Phase 5)'] },
      ]}
    />
  );
}
