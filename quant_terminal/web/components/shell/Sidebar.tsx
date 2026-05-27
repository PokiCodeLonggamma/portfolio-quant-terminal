"use client";
import Link from "next/link";

import { NAV_SECTIONS } from "@/lib/nav";

import { NavSection } from "./NavSection";

export function Sidebar() {
  return (
    <aside
      className="border-r border-[var(--color-border)] h-screen overflow-y-auto"
      style={{
        background: "var(--color-elev)",
        width: 240,
        position: "sticky",
        top: 0,
      }}
    >
      {/* Logo + § badge */}
      <Link href="/" className="block">
        <div
          className="flex items-baseline gap-2 px-4 py-5 border-b border-[var(--color-rule)]"
        >
          <span
            className="qt-display"
            style={{
              fontVariationSettings: '"opsz" 96',
              fontWeight: 900,
              fontSize: "2rem",
              color: "var(--color-rule)",
              lineHeight: 0.9,
            }}
          >
            §
          </span>
          <div>
            <div
              className="qt-display font-bold"
              style={{ fontSize: "1rem", letterSpacing: "-0.02em" }}
            >
              QUANT
            </div>
            <div
              className="qt-mono text-[0.65rem] uppercase tracking-widest"
              style={{ color: "var(--color-bone-muted)" }}
            >
              terminal v3
            </div>
          </div>
        </div>
      </Link>

      {/* Nav sections */}
      <nav className="py-3">
        {NAV_SECTIONS.map((s) => (
          <NavSection key={s.key} section={s} />
        ))}
      </nav>
    </aside>
  );
}
