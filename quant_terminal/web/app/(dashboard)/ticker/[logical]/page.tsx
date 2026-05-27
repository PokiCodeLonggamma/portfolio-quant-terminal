/** /ticker/{logical} — dedicated full-screen TradingView chart + ticker meta.
 *
 * Server fetches the contract spec at request time. Falls back to a generic
 * card if the logical isn't in the universe (still renders TV with the
 * raw symbol).
 */
import Link from "next/link";

import { TradingViewWidget } from "@/components/charts/TradingViewWidget";
import { SectionHeader } from "@/components/widgets/SectionHeader";
import { StatStrip } from "@/components/widgets/StatStrip";
import { getContract, type Contract } from "@/lib/api";

export const dynamic = "force-dynamic"; // hits live API at request time

export default async function Page({ params }: { params: Promise<{ logical: string }> }) {
  const { logical } = await params;
  const decoded = decodeURIComponent(logical);

  let contract: Contract | null = null;
  try {
    contract = await getContract(decoded);
  } catch {
    contract = null;
  }

  return (
    <div className="p-6 md:p-10 mx-auto" style={{ maxWidth: 1520 }}>
      <Link
        href="/markets/cross-asset"
        className="qt-mono text-xs uppercase mb-3 inline-block"
        style={{
          color: "var(--color-rule)",
          letterSpacing: "0.08em",
          textDecoration: "none",
        }}
      >
        ← Back to Cross-Asset
      </Link>

      <SectionHeader
        sectionNumber="↘"
        title={contract ? `${contract.logical} — ${contract.name}` : decoded}
        subtitle={
          contract
            ? `${contract.exchange} · ${contract.tier} · ${contract.currency} · ×${contract.multiplier}`
            : "Ticker not in universe — TradingView widget will use the raw symbol"
        }
        meta={contract?.asset_class.toUpperCase()}
      />

      {contract && (
        <StatStrip
          items={[
            { label: "Exchange", value: contract.exchange },
            { label: "Tier", value: contract.tier.toUpperCase() },
            { label: "Tick value", value: `${contract.currency} ${contract.tick_value}` },
            { label: "Multiplier", value: `×${contract.multiplier}` },
            { label: "Options", value: contract.option_market ? "✅ Listed" : "—" },
          ]}
        />
      )}

      <div
        style={{
          border: "1px solid var(--color-border)",
          borderLeft: "3px solid var(--color-rule)",
          background: "var(--color-card)",
          padding: 12,
          marginTop: 16,
        }}
      >
        <TradingViewWidget
          symbol={contract?.tradingview || decoded}
          interval="D"
          height={620}
        />
      </div>

      {contract?.notes && (
        <p
          className="qt-mono text-xs mt-3"
          style={{ color: "var(--color-bone-muted)" }}
        >
          {contract.notes}
        </p>
      )}
    </div>
  );
}
