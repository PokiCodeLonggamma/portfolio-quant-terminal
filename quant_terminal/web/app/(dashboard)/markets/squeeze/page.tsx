/** Short-squeeze top-20 — sortable table from /api/scanners/squeeze. */
import { SectionHeader } from "@/components/widgets/SectionHeader";
import { EmptyState } from "@/components/widgets/EmptyState";
import { TickerLink } from "@/components/widgets/TickerLink";
import { getSqueeze, type SqueezeRow } from "@/lib/api";

export const dynamic = "force-dynamic"; // hits live API at request time

function fmtN(v: number | null, decimals = 2): string {
  if (v === null || v === undefined) return "—";
  return v.toFixed(decimals);
}

export default async function Page() {
  let rows: SqueezeRow[] = [];
  let err: string | null = null;
  try {
    rows = await getSqueeze(20);
  } catch (e) {
    err = e instanceof Error ? e.message : String(e);
  }

  const maxScore = Math.max(
    1,
    ...rows.map((r) => (r.composite_score ?? 0)).filter((n) => n > 0),
  );

  return (
    <div className="p-6 md:p-10 mx-auto" style={{ maxWidth: 1520 }}>
      <SectionHeader
        sectionNumber="04"
        title="Short Squeeze Scanner"
        subtitle="SEC SHO threshold list + Finviz short interest + composite score (cached 10 min)"
        meta="MARKETS / SQZ"
      />
      {err && <EmptyState title="API offline" text={err} icon="📡" />}
      {!err && rows.length === 0 && (
        <EmptyState
          title="No squeeze data"
          text="The scanner refresh hasn't run yet. Start the worker (arq api.workers.worker.WorkerSettings) and retry in 5 minutes."
          icon="⏳"
        />
      )}
      {!err && rows.length > 0 && (
        <table
          className="w-full qt-mono text-xs"
          style={{ borderCollapse: "collapse", background: "var(--color-card)" }}
        >
          <thead>
            <tr style={{ background: "var(--color-muted-bg)" }}>
              {["Ticker", "Score", "Short %", "Days-to-cover", "CTB %", "Util %", "SHO"].map((h, i) => (
                <th
                  key={h}
                  style={{
                    textAlign: i === 0 || i === 6 ? "left" : "right",
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
            {rows.map((r) => {
              const score = r.composite_score ?? 0;
              const w = (score / maxScore) * 100;
              return (
                <tr key={r.ticker}>
                  <td style={td}>
                    <TickerLink logical={r.ticker} />
                  </td>
                  <td style={{ ...td, textAlign: "right" }}>
                    <div style={{ display: "inline-block", width: 100 }}>
                      <div
                        style={{
                          height: 4,
                          background: "var(--color-card-hover)",
                          marginBottom: 2,
                        }}
                      >
                        <div
                          style={{
                            height: "100%",
                            width: `${w}%`,
                            background: "var(--color-amber)",
                          }}
                        />
                      </div>
                      <span style={{ color: "var(--color-amber)" }}>{fmtN(score, 1)}</span>
                    </div>
                  </td>
                  <td style={{ ...td, textAlign: "right" }}>{fmtN(r.short_pct_float)}</td>
                  <td style={{ ...td, textAlign: "right" }}>{fmtN(r.days_to_cover)}</td>
                  <td style={{ ...td, textAlign: "right" }}>{fmtN(r.cost_to_borrow_pct)}</td>
                  <td style={{ ...td, textAlign: "right" }}>{fmtN(r.utilization_pct)}</td>
                  <td style={td}>
                    {r.on_sho_threshold ? (
                      <span style={{ color: "var(--color-mercury)" }}>● ON</span>
                    ) : (
                      <span style={{ color: "var(--color-bone-dim)" }}>—</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}

const td: React.CSSProperties = {
  padding: "6px 12px",
  borderBottom: "1px solid var(--color-border)",
  color: "var(--color-bone-muted)",
  fontVariantNumeric: "tabular-nums",
};
