"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { fetchJSON } from "@/lib/api";

export type Me = { email: string; exp: string };

async function fetchMe(): Promise<Me | null> {
  try {
    return await fetchJSON<Me>("/api/auth/me", { credentials: "include" });
  } catch {
    return null;
  }
}

export function useMe() {
  return useQuery({
    queryKey: ["auth", "me"],
    queryFn: fetchMe,
    staleTime: 5 * 60_000,
    refetchOnWindowFocus: false,
  });
}

export function useLogin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (creds: { email: string; password: string }) => {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(creds),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `Login failed (${res.status})`);
      }
      return res.json() as Promise<{ ok: boolean; email: string; exp: string }>;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["auth"] }),
  });
}

export function useLogout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      await fetch("/api/auth/logout", { method: "POST", credentials: "include" });
    },
    onSuccess: () => {
      qc.setQueryData(["auth", "me"], null);
      qc.invalidateQueries({ queryKey: ["auth"] });
    },
  });
}
