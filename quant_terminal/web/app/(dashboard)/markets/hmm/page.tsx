"use client";
import { useQuery } from "@tanstack/react-query";

import { SectionHeader } from "@/components/widgets/SectionHeader";
import { EmptyState } from "@/components/widgets/EmptyState";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getHmm, type HMMRegime } from "@/lib/api";

const TICKERS = ["SPY", "QQQ", "IWM"];

function regimeColor(label: string): string {
  const l = label.toUpperCase();
  if (l.includes("PANIC") || l.includes("HIGH")) return "var(--color-mercury)";
  if (l.includes("MID")) return "var(--color-amber)";
  if (l.includes("LOW") || l.includes("CALM")) return "var(--color-mint)";
  return "var(--color-cyan)";
}

function RegimeCard({ ticker }: { ticker: string }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["hmm", ticker],
    queryFn: () => getHmm(ticker, 3),
    staleTime: 60 * 60_000, // server cache TTL = 1h
  });

  return (
    <Card style={{ borderLeftColor: "var(--color-rule)" }}>
      <CardHeader>
        <CardTitle>{ticker}</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading && (
          <div className="qt-mono text-sm" style={{ color: "var(--color-bone-muted)" }}>
            Fitting HMM…
          </div>
        )}
        {error && (
          <EmptyState
            title="Unavailable"
            text={error instanceof Error ? error.message : String(error)}
            icon="⚠️"
          />
        )}
        {data && <RegimeInner data={data} />}
      </CardContent>
    </Card>
  );
}

function RegimeInner({ data }: { data: HMMRegime }) {
  const color = regimeColor(data.current_label);
  // Sort probabilities desc
  const entries = Object.entries(data.current_probs).sort((a, b) => b[1] - a[1]);
  return (
    <>
      <div
        className="qt-display"
        style={{
          fontWeight: 700,
          fontSize: "1.8rem",
          color,
          letterSpacing: "-0.01em",
          marginBottom: 12,
        }}
      >
        {data.current_label}
      </div>
      <div style={{ marginBottom: 12 }}>
        {entries.map(([label, p]) => (
          <div key={label} style={{ marginBottom: 4 }}>
            <div
              className="qt-mono text-[0.7rem] uppercase"
              style={{ color: "var(--color-bone-muted)", letterSpacing: "0.06em" }}
            >
              {label} · {(p * 100).toFixed(1)}%
            </div>
            <div
              style={{
                height: 6,
                background: "var(--color-card-hover)",
                marginTop: 2,
              }}
            >
              <div
                style={{
                  height: "100%",
                  width: `${p * 100}%`,
                  background: regimeColor(label),
                  transition: "width 200ms ease",
                }}
              />
            </div>
          </div>
        ))}
      </div>
      <div
        className="qt-mono text-[0.7rem]"
        style={{
          color: "var(--color-bone-dim)",
          borderTop: "1px solid var(--color-border)",
          paddingTop: 6,
        }}
      >
        n={data.sample_size} · {new Date(data.asof).toISOString().slice(0, 10)}
      </div>
    </>
  );
}

export default function Page() {
  return (
    <div className="p-6 md:p-10 mx-auto" style={{ maxWidth: 1520 }}>
      <SectionHeader
        sectionNumber="03"
        title="HMM Regime"
        subtitle="3-state Gaussian HMM on log-returns — refit every hour by the worker, cached 1h"
        meta="MARKETS / HMM"
      />
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {TICKERS.map((tk) => (
          <RegimeCard key={tk} ticker={tk} />
        ))}
      </div>
    </div>
  );
}
