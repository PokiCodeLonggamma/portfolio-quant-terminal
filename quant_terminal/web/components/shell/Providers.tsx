"use client";
import { QueryClientProvider } from "@tanstack/react-query";
import { ReactNode } from "react";

import { getQueryClient } from "@/lib/query-client";

export function Providers({ children }: { children: ReactNode }) {
  const qc = getQueryClient();
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}
