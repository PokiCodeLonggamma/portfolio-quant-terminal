"use client";
import { QueryClient } from "@tanstack/react-query";

let _client: QueryClient | null = null;

/** Singleton QueryClient with sensible defaults for a dashboard.
 *
 * - staleTime 60s — most endpoints are Redis-cached server-side anyway
 * - retry 1 — surface upstream issues quickly
 * - refetchOnWindowFocus off — the user IS the window focus, don't waste calls
 */
export function getQueryClient(): QueryClient {
  if (!_client) {
    _client = new QueryClient({
      defaultOptions: {
        queries: {
          staleTime: 60_000,
          retry: 1,
          refetchOnWindowFocus: false,
          refetchOnReconnect: true,
        },
        mutations: { retry: 0 },
      },
    });
  }
  return _client;
}
