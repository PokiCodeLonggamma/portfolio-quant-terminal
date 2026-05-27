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
// Endpoint helpers
// ---------------------------------------------------------------------------
export const getHealth = () => fetchJSON<Health>("/health");
export const getUniverse = () => fetchJSON<Universe>("/api/universe");
export const getAssetClass = (key: string) =>
  fetchJSON<AssetClass>(`/api/universe/${encodeURIComponent(key)}`);
export const getContract = (logical: string) =>
  fetchJSON<Contract>(`/api/universe/contracts/${encodeURIComponent(logical)}`);
