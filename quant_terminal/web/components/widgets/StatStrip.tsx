import { KpiTile, type KpiTileProps } from "./KpiTile";

export type StatStripProps = { items: KpiTileProps[]; className?: string };

export function StatStrip({ items, className }: StatStripProps) {
  return (
    <div
      className={className}
      style={{
        display: "grid",
        gridTemplateColumns: `repeat(${Math.max(1, items.length)}, minmax(0, 1fr))`,
        gap: 12,
        marginBottom: 16,
      }}
    >
      {items.map((it, i) => (
        <KpiTile key={i} {...it} />
      ))}
    </div>
  );
}
