/** Sidebar nav config — 5 domain groups × N routes. */

export type NavItem = {
  href: string;
  label: string;
  short?: string; // Bloomberg-style 3-letter code (future use)
  description?: string;
};

export type NavSection = {
  key: string;
  label: string;
  icon: string;
  items: NavItem[];
};

export const NAV_SECTIONS: NavSection[] = [
  {
    key: "markets",
    label: "Markets",
    icon: "🌍",
    items: [
      { href: "/markets/cross-asset", label: "Cross-Asset", short: "CRS", description: "Universe heatmap + flagship contracts" },
      { href: "/markets/macro", label: "Macro & Regime", short: "MAC" },
      { href: "/markets/hmm", label: "HMM Regime", short: "HMM" },
      { href: "/markets/squeeze", label: "Short Squeeze", short: "SQZ" },
      { href: "/markets/catalysts", label: "Catalysts & News", short: "CAT" },
    ],
  },
  {
    key: "portfolio",
    label: "Portfolio",
    icon: "📈",
    items: [
      { href: "/portfolio/holdings", label: "Holdings", short: "HLD" },
      { href: "/portfolio/greeks", label: "Greeks", short: "GRK" },
      { href: "/portfolio/snapshot", label: "Snapshot", short: "SNP" },
      { href: "/portfolio/tax", label: "Tax (2074)", short: "TAX" },
    ],
  },
  {
    key: "trading",
    label: "Trading",
    icon: "🎯",
    items: [
      { href: "/trading/bench", label: "Trading Bench", short: "TRD" },
      { href: "/trading/watchlists", label: "Watchlists", short: "WCH" },
      { href: "/trading/execution", label: "Execution", short: "EXE" },
    ],
  },
  {
    key: "decision",
    label: "Decision",
    icon: "🧠",
    items: [
      { href: "/decision/conviction", label: "Conviction", short: "CNV" },
      { href: "/decision/smart-money", label: "Smart Money", short: "SMT" },
      { href: "/decision/daily-brief", label: "Daily Brief", short: "BRF" },
      { href: "/decision/alerts", label: "Alerts", short: "ALT" },
    ],
  },
  {
    key: "lab",
    label: "Lab",
    icon: "🧪",
    items: [
      { href: "/lab/backtest", label: "Backtest", short: "BKT" },
      { href: "/lab/event-trading", label: "Event Trading", short: "EVT" },
      { href: "/lab/kalman", label: "Kalman", short: "KAL" },
    ],
  },
];

/** Find the active section/item for a pathname. */
export function findActiveNav(pathname: string): { section: NavSection | null; item: NavItem | null } {
  for (const s of NAV_SECTIONS) {
    const item = s.items.find((i) => pathname.startsWith(i.href));
    if (item) return { section: s, item };
  }
  return { section: null, item: null };
}
