/** Catalysts & News — upcoming events on the left + news pulse on the right. */
import { SectionHeader } from "@/components/widgets/SectionHeader";
import { EmptyState } from "@/components/widgets/EmptyState";
import { TickerLink } from "@/components/widgets/TickerLink";
import {
  getCatalysts, getNews,
  type CatalystFeed, type NewsPulse,
} from "@/lib/api";

export const dynamic = "force-dynamic"; // hits live API at request time

function timeAgo(iso: string | null): string {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  const sec = Math.max(0, Math.floor((Date.now() - t) / 1000));
  if (sec < 60) return `${sec}s ago`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m ago`;
  if (sec < 86400) return `${Math.floor(sec / 3600)}h ago`;
  return `${Math.floor(sec / 86400)}d ago`;
}

function sentimentColor(s: string | null): string {
  if (s === "positive") return "var(--color-mint)";
  if (s === "negative") return "var(--color-mercury)";
  return "var(--color-bone-dim)";
}

export default async function Page() {
  let cats: CatalystFeed | null = null;
  let news: NewsPulse | null = null;
  let err: string | null = null;
  try {
    [cats, news] = await Promise.all([getCatalysts(30), getNews(50)]);
  } catch (e) {
    err = e instanceof Error ? e.message : String(e);
  }

  return (
    <div className="p-6 md:p-10 mx-auto" style={{ maxWidth: 1520 }}>
      <SectionHeader
        sectionNumber="05"
        title="Catalysts & News"
        subtitle="Upcoming earnings + macro events (30d) · live news pulse (cached 5 min)"
        meta="MARKETS / CAT"
      />

      {err && <EmptyState title="API offline" text={err} icon="📡" />}

      {!err && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* CATALYSTS */}
          <section>
            <h3 className="qt-display mb-3" style={{ fontSize: "1.15rem" }}>
              Upcoming events
              <span
                className="qt-mono text-[0.7rem] uppercase ml-2"
                style={{ color: "var(--color-bone-dim)", letterSpacing: "0.08em" }}
              >
                {cats?.items.length ?? 0} in {cats?.horizon_days ?? 30}d
              </span>
            </h3>
            {!cats?.items.length && (
              <EmptyState title="No catalysts" text="Calendar fetch returned empty." icon="📭" />
            )}
            <ul style={{ listStyle: "none", padding: 0 }}>
              {cats?.items.map((c) => (
                <li
                  key={c.event_id}
                  style={{
                    padding: "8px 0",
                    borderBottom: "1px solid var(--color-border)",
                    display: "grid",
                    gridTemplateColumns: "80px 1fr",
                    gap: 10,
                  }}
                >
                  <div
                    className="qt-mono text-xs"
                    style={{ color: "var(--color-rule)" }}
                  >
                    {new Date(c.start).toISOString().slice(5, 10)}
                  </div>
                  <div>
                    <div className="qt-mono text-xs" style={{ color: "var(--color-bone)" }}>
                      {c.ticker ? <TickerLink logical={c.ticker} /> : "—"}{" "}
                      <span style={{ color: "var(--color-bone-muted)" }}>· {c.title}</span>
                    </div>
                    <div
                      className="qt-mono text-[0.65rem] uppercase mt-0.5"
                      style={{ color: "var(--color-bone-dim)", letterSpacing: "0.08em" }}
                    >
                      {c.category}
                      {c.estimated_eps !== null && (
                        <> · EPS est. {c.estimated_eps.toFixed(2)}</>
                      )}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          </section>

          {/* NEWS */}
          <section>
            <h3 className="qt-display mb-3" style={{ fontSize: "1.15rem" }}>
              News pulse
              <span
                className="qt-mono text-[0.7rem] uppercase ml-2"
                style={{ color: "var(--color-bone-dim)", letterSpacing: "0.08em" }}
              >
                {news?.items.length ?? 0} items · last 6h
              </span>
            </h3>
            {!news?.items.length && (
              <EmptyState title="No fresh news" text="Try again in a minute." icon="📡" />
            )}
            <ul style={{ listStyle: "none", padding: 0 }}>
              {news?.items.slice(0, 25).map((n, i) => (
                <li
                  key={n.url + i}
                  style={{
                    padding: "8px 0",
                    borderBottom: "1px solid var(--color-border)",
                  }}
                >
                  <a
                    href={n.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="qt-mono text-xs"
                    style={{ color: "var(--color-bone)", textDecoration: "none" }}
                  >
                    {n.title}
                  </a>
                  <div
                    className="qt-mono text-[0.65rem] uppercase mt-0.5"
                    style={{ color: "var(--color-bone-dim)", letterSpacing: "0.08em" }}
                  >
                    <span style={{ color: sentimentColor(n.sentiment) }}>
                      {n.sentiment ?? "neutral"}
                    </span>
                    {" · "}
                    {n.tickers.length > 0 && (
                      <>
                        {n.tickers.slice(0, 2).map((t, idx) => (
                          <span key={t}>
                            {idx > 0 && ","} <TickerLink logical={t} />
                          </span>
                        ))}
                        {" · "}
                      </>
                    )}
                    {n.source} · {timeAgo(n.published_at)}
                  </div>
                </li>
              ))}
            </ul>
          </section>
        </div>
      )}
    </div>
  );
}
