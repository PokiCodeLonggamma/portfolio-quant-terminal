/**
 * Typed REST client for the Quant Terminal FastAPI surface.
 *
 * In dev, requests are proxied through Next.js (see next.config.mjs rewrites)
 * so /api/* hits localhost:8000 transparently — no CORS dance.
 *
 * In prod, set NEXT_PUBLIC_API_BASE to the Render URL.
 */
const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";

/** Lightweight wrapper around fetch with JSON + typed errors. */
export async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, {
    credentials: "include", // ship cookies for auth-protected endpoints
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    let detail = "";
    try {
      detail = JSON.stringify(await res.json());
    } catch {
      detail = await res.text();
    }
    throw new Error(`${res.status} ${res.statusText} on ${path}: ${detail}`);
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Types — mirror api/models.py (Pydantic v2)
// ---------------------------------------------------------------------------
export type Tier = "standard" | "mini" | "micro";

export type Contract = {
  logical: string;
  name: string;
  tier: Tier;
  root: string;
  exchange: string;
  asset_class: string;
  yfinance: string;
  alpaca: string;
  tradingview: string;
  multiplier: number;
  currency: string;
  tick_size: number;
  tick_value: number;
  option_market: boolean;
  notes: string;
};

export type AssetClass = {
  key: string;
  label: string;
  icon: string;
  order: number;
  contracts: Contract[];
};

export type Universe = {
  asset_classes: AssetClass[];
  theme_to_drivers: Record<string, Record<string, string[]>>;
};

export type Health = {
  status: "ok";
  version: string;
  redis: "up" | "down";
};

// ---------------------------------------------------------------------------
// P5a additions — typed schemas for markets cluster
// ---------------------------------------------------------------------------
export type HeatmapRow = {
  asset_class: string;
  logical: string;
  name: string;
  chg_1d_pct: number | null;
  chg_5d_pct: number | null;
};

export type MacroSnapshot = {
  vix_level: number | null;
  vix_term_structure: "contango" | "backwardation" | "flat" | null;
  dxy: number | null;
  us10y_yield: number | null;
  spy_above_200d: boolean | null;
  asof: string;
};

export type HMMRegime = {
  ticker: string;
  current_label: string;
  current_probs: Record<string, number>;
  n_states: number;
  sample_size: number;
  asof: string;
};

export type SqueezeRow = {
  ticker: string;
  short_pct_float: number | null;
  days_to_cover: number | null;
  cost_to_borrow_pct: number | null;
  utilization_pct: number | null;
  on_sho_threshold: boolean;
  composite_score: number | null;
};

export type CatalystOut = {
  event_id: string;
  ticker: string | null;
  category: string;
  title: string;
  start: string;
  end: string | null;
  notes: string | null;
  estimated_eps: number | null;
  actual_eps: number | null;
};

export type CatalystFeed = {
  horizon_days: number;
  items: CatalystOut[];
  asof: string;
};

export type NewsItem = {
  title: string;
  url: string;
  source: string;
  published_at: string | null;
  summary: string | null;
  tickers: string[];
  sentiment: "positive" | "neutral" | "negative" | null;
};

export type NewsPulse = {
  items: NewsItem[];
  asof: string;
};

// ---------------------------------------------------------------------------
// Endpoint helpers
// ---------------------------------------------------------------------------
export const getHealth = () => fetchJSON<Health>("/health");
export const getUniverse = () => fetchJSON<Universe>("/api/universe");
export const getAssetClass = (key: string) =>
  fetchJSON<AssetClass>(`/api/universe/${encodeURIComponent(key)}`);
export const getContract = (logical: string) =>
  fetchJSON<Contract>(`/api/universe/contracts/${encodeURIComponent(logical)}`);

// P5a — markets
export const getHeatmap = () => fetchJSON<HeatmapRow[]>("/api/cross-asset/heatmap");
export const getMacro = () => fetchJSON<MacroSnapshot>("/api/regime/macro");
export const getHmm = (ticker: string, n_states = 3) =>
  fetchJSON<HMMRegime>(
    `/api/regime/hmm/${encodeURIComponent(ticker)}?n_states=${n_states}`,
  );
export const getSqueeze = (limit = 20) =>
  fetchJSON<SqueezeRow[]>(`/api/scanners/squeeze?limit=${limit}`);
export const getCatalysts = (horizon_days = 30) =>
  fetchJSON<CatalystFeed>(`/api/catalysts/upcoming?horizon_days=${horizon_days}`);
export const getNews = (limit = 50) =>
  fetchJSON<NewsPulse>(`/api/news/latest?limit=${limit}`);
