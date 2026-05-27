"use client";
import { useEffect, useState } from "react";

import { useLogout, useMe } from "@/lib/auth";
import { Button } from "@/components/ui/button";

function useNow() {
  const [now, setNow] = useState<string>("");
  useEffect(() => {
    const tick = () => setNow(new Date().toISOString().slice(0, 19).replace("T", " ") + " UTC");
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);
  return now;
}

export function TopBar() {
  const now = useNow();
  const { data: me } = useMe();
  const logout = useLogout();
  return (
    <header
      className="flex items-center justify-between border-b border-[var(--color-border)] px-6"
      style={{ height: 48, background: "var(--color-elev)" }}
    >
      <div className="qt-mono text-xs" style={{ color: "var(--color-bone-muted)" }}>
        <span style={{ color: "var(--color-rule)" }}>●</span>{" "}
        <span style={{ marginLeft: 4 }}>{now}</span>
      </div>
      <div className="flex items-center gap-3">
        <span
          className="qt-mono text-[0.7rem] uppercase tracking-widest"
          style={{ color: "var(--color-bone-dim)" }}
        >
          {me?.email ?? "—"}
        </span>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => logout.mutate(undefined, { onSuccess: () => (window.location.href = "/login") })}
        >
          Logout
        </Button>
      </div>
    </header>
  );
}
