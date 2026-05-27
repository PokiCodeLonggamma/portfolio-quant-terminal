import Link from "next/link";

export function TickerLink({ logical, label }: { logical: string; label?: string }) {
  return (
    <Link
      href={`/ticker/${encodeURIComponent(logical)}`}
      className="qt-mono font-bold"
      style={{
        color: "var(--color-rule)",
        textDecoration: "none",
        borderBottom: "1px dotted transparent",
        transition: "border-color 120ms ease",
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderBottomColor = "var(--color-rule)";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderBottomColor = "transparent";
      }}
    >
      {label ?? logical}
    </Link>
  );
}
