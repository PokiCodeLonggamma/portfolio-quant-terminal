import { cn } from "@/lib/cn";

export type KpiTileProps = {
  label: string;
  value: string;
  delta?: string;
  deltaDir?: "pos" | "neg" | "neutral";
  hint?: string;
  accent?: "mint" | "rose" | "amber" | "cyan";
  className?: string;
};

export function KpiTile({ label, value, delta, deltaDir = "neutral", hint, accent, className }: KpiTileProps) {
  const accentColor =
    accent === "mint"   ? "var(--color-mint)" :
    accent === "rose"   ? "var(--color-mercury)" :
    accent === "amber"  ? "var(--color-amber)" :
    accent === "cyan"   ? "var(--color-cyan)" :
    "var(--color-rule)";
  const deltaColor =
    deltaDir === "pos" ? "var(--color-mint)" :
    deltaDir === "neg" ? "var(--color-mercury)" :
    "var(--color-bone-dim)";

  return (
    <article
      className={cn(
        "border border-[var(--color-border)] rounded-none p-4 transition-colors",
        "bg-[var(--color-card)] hover:bg-[var(--color-card-hover)]",
        className,
      )}
      style={{ borderLeftWidth: 3, borderLeftColor: accentColor, minHeight: 92 }}
      data-testid="kpi-tile"
    >
      <div
        className="qt-mono text-[0.7rem] uppercase mb-1.5"
        style={{ letterSpacing: "0.12em", color: "var(--color-bone-muted)" }}
      >
        {label}
      </div>
      <div
        className="qt-display font-bold"
        style={{
          fontSize: "1.65rem",
          color: "var(--color-bone)",
          fontVariantNumeric: "tabular-nums",
          lineHeight: 1,
          fontVariationSettings: '"opsz" 32',
        }}
      >
        {value}
      </div>
      {delta && (
        <div
          className="qt-mono text-xs mt-1"
          style={{ color: deltaColor, fontVariantNumeric: "tabular-nums" }}
        >
          {delta}
        </div>
      )}
      {hint && (
        <div
          className="qt-mono text-[0.7rem] mt-1.5 pt-1.5"
          style={{ color: "var(--color-bone-dim)", borderTop: "1px solid var(--color-border)" }}
        >
          {hint}
        </div>
      )}
    </article>
  );
}
