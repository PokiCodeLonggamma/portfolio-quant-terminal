import { SectionHeader } from "./SectionHeader";
import { PlaceholderPanel } from "./PlaceholderPanel";

export type PageScaffoldProps = {
  number: string;
  title: string;
  subtitle?: string;
  meta?: string;
  panels: Array<{
    title: string;
    description?: string;
    endpoints?: string[];
  }>;
};

/** Reused by every P4 route — sticks until P5 wires real data. */
export function PageScaffold({ number, title, subtitle, meta, panels }: PageScaffoldProps) {
  return (
    <div className="p-6 md:p-10 mx-auto" style={{ maxWidth: 1520 }}>
      <SectionHeader sectionNumber={number} title={title} subtitle={subtitle} meta={meta} />
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {panels.map((p, i) => (
          <PlaceholderPanel key={i} {...p} />
        ))}
      </div>
    </div>
  );
}
