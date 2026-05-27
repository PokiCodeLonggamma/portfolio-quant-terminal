/**
 * Home page — first live hit on the FastAPI surface.
 *
 * Server-rendered (RSC). Fetches /api/universe at request time, caches for
 * 5 minutes (ISR). If the API is down, shows a brutalist offline notice.
 */
import { getUniverse, type Universe } from "@/lib/api";

export const revalidate = 300; // 5 min ISR

export default async function Home() {
  let universe: Universe | null = null;
  let apiError: string | null = null;
  try {
    universe = await getUniverse();
  } catch (e) {
    apiError = e instanceof Error ? e.message : String(e);
  }

  if (apiError || !universe) {
    return (
      <main className="p-8 max-w-5xl mx-auto">
        <Hero number="00" title="Quant Terminal" subtitle="API offline" />
        <div className="qt-tile mt-4" style={{ borderLeftColor: "var(--color-mercury)" }}>
          <div className="qt-tile-label" style={{ color: "var(--color-mercury)" }}>
            UPSTREAM UNAVAILABLE
          </div>
          <p className="qt-mono text-sm mt-2 text-stone-300">
            Could not reach the FastAPI backend at{" "}
            <code style={{ color: "var(--color-rule)" }}>localhost:8000</code>.
          </p>
          <p className="qt-mono text-xs mt-3 text-stone-500">
            Start it with{" "}
            <code style={{ color: "var(--color-bone)" }}>
              uvicorn api.main:app --reload
            </code>{" "}
            or{" "}
            <code style={{ color: "var(--color-bone)" }}>
              docker compose -f docker-compose.dev.yml up
            </code>
            .
          </p>
          {apiError && (
            <pre className="qt-mono text-xs mt-4 text-stone-600 whitespace-pre-wrap">
              {apiError}
            </pre>
          )}
        </div>
      </main>
    );
  }

  const totalContracts = universe.asset_classes.reduce(
    (sum, ac) => sum + ac.contracts.length,
    0,
  );
  const totalOptionMarkets = universe.asset_classes.reduce(
    (sum, ac) => sum + ac.contracts.filter((c) => c.option_market).length,
    0,
  );

  return (
    <main className="p-6 md:p-10 max-w-7xl mx-auto">
      <Hero
        number="00"
        title="Quant Terminal"
        subtitle={`Cross-asset cockpit — Next.js + FastAPI · ${universe.asset_classes.length} asset classes · ${totalContracts} contracts · ${totalOptionMarkets} option markets`}
      />

      {/* Asset class grid */}
      <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-3">
        {universe.asset_classes.map((ac) => (
          <article key={ac.key} className="qt-tile">
            <div className="qt-tile-label">
              <span style={{ marginRight: "6px" }}>{ac.icon}</span>
              {ac.label}
            </div>
            <div className="qt-tile-value">{ac.contracts.length}</div>
            <div className="qt-tile-hint">
              {ac.contracts.slice(0, 5).map((c) => c.logical).join(" · ")}
              {ac.contracts.length > 5 ? " · …" : ""}
            </div>
          </article>
        ))}
      </section>

      <hr style={{ border: 0, borderTop: "1px solid var(--color-rule)", opacity: 0.4, margin: "32px 0" }} />

      {/* Sample contract grid — flagship CDC §1 contracts */}
      <h2 className="qt-display text-2xl mb-4">
        <span style={{ color: "var(--color-rule)", marginRight: "10px" }}>§</span>
        CDC §1 — Flagship contracts
      </h2>
      <section className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6 gap-2">
        {["ES", "MES", "NQ", "MNQ", "VX", "CL", "MCL", "GC", "MGC", "BTC", "ETH", "FDAX"].map(
          (logical) => {
            const spec = universe!.asset_classes
              .flatMap((ac) => ac.contracts)
              .find((c) => c.logical === logical);
            if (!spec) return null;
            return (
              <article
                key={logical}
                className="qt-tile"
                style={{ borderLeftColor: "var(--color-mint)" }}
              >
                <div className="qt-tile-label">{spec.exchange}</div>
                <div className="qt-tile-value">{spec.logical}</div>
                <div className="qt-tile-hint">
                  {spec.name} · ×{spec.multiplier}
                </div>
              </article>
            );
          },
        )}
      </section>

      <footer
        className="qt-mono mt-12 text-xs uppercase tracking-widest text-center"
        style={{ color: "var(--color-bone-dim)" }}
      >
        Quant Terminal v3 · Wall Street Brutalist · Phase 0 portage · Next.js {process.env.NEXT_PUBLIC_BUILD_ID ?? "dev"}
      </footer>
    </main>
  );
}

// ---------------------------------------------------------------------------
// Local components
// ---------------------------------------------------------------------------
function Hero({
  number,
  title,
  subtitle,
}: {
  number: string;
  title: string;
  subtitle: string;
}) {
  return (
    <header className="qt-hero">
      <span className="qt-hero-number">§ {number}</span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <h1 className="qt-hero-title">{title}</h1>
        <p className="qt-hero-subtitle">{subtitle}</p>
      </div>
    </header>
  );
}
