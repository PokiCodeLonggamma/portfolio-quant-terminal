import { PageScaffold } from '@/components/widgets/PageScaffold';

export default function Page() {
  return (
    <PageScaffold
      number="18"
      title="Event Trading"
      subtitle="Pre-event wizard + earnings IV crush simulator"
      meta="LAB / EVT"
      panels={[
        { title: 'POST /api/event/wizard (Phase 5)', endpoints: ['POST /api/event/wizard (Phase 5)'] },
        { title: 'POST /api/options/{tk}/iv_crush', endpoints: ['POST /api/options/{tk}/iv_crush'] },
      ]}
    />
  );
}
