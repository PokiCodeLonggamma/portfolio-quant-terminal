"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

import type { NavSection as NavSectionType } from "@/lib/nav";
import { cn } from "@/lib/cn";
import { useUIStore } from "@/store/ui";

export function NavSection({ section }: { section: NavSectionType }) {
  const pathname = usePathname();
  const collapsed = useUIStore((s) => s.collapsedSections[section.key] ?? false);
  const toggle = useUIStore((s) => s.toggleSection);

  return (
    <div className="mb-3">
      <button
        onClick={() => toggle(section.key)}
        className={cn(
          "w-full flex items-center gap-2 px-3 py-1.5 text-left",
          "font-mono text-[0.65rem] uppercase tracking-[0.18em]",
          "text-[var(--color-bone-muted)] hover:text-[var(--color-bone)]",
          "border-b border-[var(--color-border)]",
        )}
      >
        <span style={{ width: 14, display: "inline-block" }}>{collapsed ? "▸" : "▾"}</span>
        <span style={{ marginRight: 4 }}>{section.icon}</span>
        <span>{section.label}</span>
      </button>
      {!collapsed && (
        <ul className="mt-1 pl-1">
          {section.items.map((item) => {
            const active = pathname === item.href || pathname.startsWith(item.href + "/");
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  className={cn(
                    "block pl-7 pr-3 py-1.5 font-mono text-xs",
                    "border-l-2",
                    active
                      ? "border-l-[var(--color-rule)] text-[var(--color-bone)] bg-[var(--color-card-hover)]"
                      : "border-l-transparent text-[var(--color-bone-muted)] hover:text-[var(--color-bone)] hover:bg-[var(--color-card)]",
                  )}
                >
                  {item.label}
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
