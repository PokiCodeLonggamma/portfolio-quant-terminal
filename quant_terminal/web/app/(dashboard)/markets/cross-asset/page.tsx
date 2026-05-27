/** Cross-Asset overview — live heatmap + top movers, click → /ticker/{logical}. */
import { SectionHeader } from "@/components/widgets/SectionHeader";
import { StatStrip } from "@/components/widgets/StatStrip";
import { EmptyState } from "@/components/widgets/EmptyState";
import { TickerLink } from "@/components/widgets/TickerLink";
import { getHeatmap, type HeatmapRow } from "@/lib/api";
import { fmtPct, colorPct } from "@/lib/format";

export const dynamic = "force-dynamic"; // hits live API at request time

export default async function Page() {
  let rows: HeatmapRow[] = [];
  let err: string | null = null;
  try {
    rows = await getHeatmap();
  } catch (e) {
    err = e instanceof Error ? e.message : String(e);
  }

  // Sort desc by 1d for "top movers" lookup
  const sorted = [...rows].sort((a, b) => (b.chg_1d_pct ?? 0) - (a.chg_1d_pct ?? 0));
  const gainers = sorted.slice(0, 3);
  const losers = sorted.slice(-3).reverse();

  return (
    <div className="p-6 md:p-10 mx-auto" style={{ maxWidth: 1520 }}>
      <SectionHeader
        sectionNumber="01"
        title="Cross-Asset Universe"
        subtitle="CDC §1 · 99 contracts × 10 asset classes · click any ticker → /ticker/<logical>"
        meta="MARKETS / CRS"
      />

      {err && (
        <EmptyState title="API offline" text={err} icon="📡" />
      )}

      {!err && rows.length > 0 && (
        <>
          <StatStrip
            items={[
              ...gainers.map((r) => ({
                label: `↑ ${r.logical}`,
                value: r.chg_1d_pct !== null ? `${(r.chg_1d_pct).toFixed(2)}%` : "—",
                hint: r.name,
                accent: "mint" as const,
              })),
              ...losers.map((r) => ({
                label: `↓ ${r.logical}`,
                value: r.chg_1d_pct !== null ? `${(r.chg_1d_pct).toFixed(2)}%` : "—",
                hint: r.name,
                accent: "rose" as const,
              })),
            ]}
          />

          <table
            className="w-full qt-mono text-xs"
            style={{
              borderCollapse: "collapse",
              background: "var(--color-card)",
              marginTop: 16,
            }}
          >
            <thead>
              <tr style={{ background: "var(--color-muted-bg)" }}>
                {["Class", "Logical", "Name", "1d %", "5d %"].map((h, i) => (
                  <th
                    key={h}
                    style={{
                      textAlign: i >= 3 ? "right" : "left",
                      padding: "8px 12px",
                      borderBottom: "1px solid var(--color-border)",
                      textTransform: "uppercase",
                      letterSpacing: "0.06em",
                      fontSize: "0.7rem",
                      color: "var(--color-bone)",
                    }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.logical}>
                  <td style={td}>{r.asset_class}</td>
                  <td style={td}>
                    <TickerLink logical={r.logical} />
                  </td>
                  <td style={{ ...td, color: "var(--color-bone-muted)" }}>{r.name}</td>
                  <td
                    style={{
                      ...td,
                      textAlign: "right",
                      color: colorPct((r.chg_1d_pct ?? 0) / 100),
                    }}
                  >
                    {r.chg_1d_pct !== null ? fmtPct((r.chg_1d_pct) / 100) : "—"}
                  </td>
                  <td
                    style={{
                      ...td,
                      textAlign: "right",
                      color: colorPct((r.chg_5d_pct ?? 0) / 100),
                    }}
                  >
                    {r.chg_5d_pct !== null ? fmtPct((r.chg_5d_pct) / 100) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {!err && rows.length === 0 && (
        <EmptyState
          title="No quotes yet"
          text="The heatmap warms up on first request and is then cached 5 minutes."
          icon="⏳"
        />
      )}
    </div>
  );
}

const td: React.CSSProperties = {
  padding: "6px 12px",
  borderBottom: "1px solid var(--color-border)",
  fontVariantNumeric: "tabular-nums",
};
