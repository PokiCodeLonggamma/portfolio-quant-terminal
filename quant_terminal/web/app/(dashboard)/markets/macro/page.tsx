/** Macro snapshot — VIX + term structure + DXY + US10Y + SPY 200d. */
import { SectionHeader } from "@/components/widgets/SectionHeader";
import { StatStrip } from "@/components/widgets/StatStrip";
import { EmptyState } from "@/components/widgets/EmptyState";
import { getMacro, type MacroSnapshot } from "@/lib/api";

export const dynamic = "force-dynamic"; // hits live API at request time

export default async function Page() {
  let m: MacroSnapshot | null = null;
  let err: string | null = null;
  try {
    m = await getMacro();
  } catch (e) {
    err = e instanceof Error ? e.message : String(e);
  }

  return (
    <div className="p-6 md:p-10 mx-auto" style={{ maxWidth: 1520 }}>
      <SectionHeader
        sectionNumber="02"
        title="Macro & Regime"
        subtitle="VIX level + term structure · DXY · US10Y · SPY vs 200d MA"
        meta="MARKETS / MAC"
      />

      {err && <EmptyState title="API offline" text={err} icon="📡" />}

      {!err && m && (
        <>
          <StatStrip
            items={[
              {
                label: "VIX",
                value: m.vix_level !== null ? m.vix_level.toFixed(2) : "—",
                hint: m.vix_term_structure ? `term: ${m.vix_term_structure}` : "term: n/a",
                accent: m.vix_level !== null && m.vix_level > 25 ? "rose" : "mint",
              },
              {
                label: "DXY",
                value: m.dxy !== null ? m.dxy.toFixed(2) : "—",
                hint: "US Dollar Index",
              },
              {
                label: "US 10Y",
                value: m.us10y_yield !== null ? `${m.us10y_yield.toFixed(2)}%` : "—",
                hint: "10-year Treasury yield (^TNX)",
              },
              {
                label: "SPY vs 200d",
                value:
                  m.spy_above_200d === null
                    ? "—"
                    : m.spy_above_200d
                      ? "ABOVE"
                      : "BELOW",
                hint: "Trend regime indicator",
                accent:
                  m.spy_above_200d === null
                    ? undefined
                    : m.spy_above_200d
                      ? "mint"
                      : "rose",
              },
            ]}
          />

          <div
            className="qt-mono text-xs mt-4"
            style={{ color: "var(--color-bone-dim)" }}
          >
            Snapshot · {new Date(m.asof).toISOString().slice(0, 19).replace("T", " ")} UTC ·
            cached 5 min
          </div>
        </>
      )}
    </div>
  );
}
