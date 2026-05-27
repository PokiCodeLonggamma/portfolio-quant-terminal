import { ReactNode } from "react";

export type SectionHeaderProps = {
  title: string;
  sectionNumber?: string;
  subtitle?: string;
  meta?: string;
  icon?: ReactNode;
};

export function SectionHeader({ title, sectionNumber, subtitle, meta, icon }: SectionHeaderProps) {
  return (
    <header
      className="flex items-baseline gap-4 py-5 mb-5"
      style={{ borderBottom: "1px solid var(--color-rule)" }}
    >
      {sectionNumber && (
        <span
          className="qt-display"
          style={{
            fontVariationSettings: '"opsz" 144',
            fontWeight: 900,
            fontSize: "3rem",
            color: "var(--color-rule)",
            lineHeight: 0.85,
            opacity: 0.95,
          }}
        >
          § {sectionNumber}
        </span>
      )}
      {icon && <span style={{ fontSize: "1.6rem" }}>{icon}</span>}
      <div style={{ flex: 1, minWidth: 0 }}>
        <h2
          className="qt-display"
          style={{
            fontWeight: 700,
            fontSize: "1.75rem",
            color: "var(--color-bone)",
            letterSpacing: "-0.01em",
            lineHeight: 1.1,
          }}
        >
          {title}
        </h2>
        {subtitle && (
          <p
            className="qt-mono text-sm mt-1"
            style={{ color: "var(--color-bone-muted)", lineHeight: 1.5 }}
          >
            {subtitle}
          </p>
        )}
      </div>
      {meta && (
        <div
          className="qt-mono text-xs uppercase"
          style={{
            color: "var(--color-bone-dim)",
            letterSpacing: "0.08em",
          }}
        >
          {meta}
        </div>
      )}
    </header>
  );
}
