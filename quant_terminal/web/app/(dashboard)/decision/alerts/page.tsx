import { PageScaffold } from '@/components/widgets/PageScaffold';

export default function Page() {
  return (
    <PageScaffold
      number="16"
      title="Alerts"
      subtitle="Triggers + channels (Streamlit/Discord) + history"
      meta="DECISION / ALT"
      panels={[
        { title: 'GET /api/alerts (Phase 5)', endpoints: ['GET /api/alerts (Phase 5)'] },
        { title: 'POST /api/alerts/triggers (Phase 5)', endpoints: ['POST /api/alerts/triggers (Phase 5)'] },
      ]}
    />
  );
}
