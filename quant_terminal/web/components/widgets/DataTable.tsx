"use client";
import { useMemo, useState } from "react";

import { cn } from "@/lib/cn";

export type Column<T> = {
  key: string;
  header: string;
  align?: "left" | "right" | "center";
  width?: number | string;
  /** Renderer for the cell. Default: String(row[key]). */
  render?: (row: T) => React.ReactNode;
  /** Function returning the value to sort by. Default: row[key] cast to number/string. */
  sortValue?: (row: T) => number | string | null;
  sortable?: boolean;
};

export type DataTableProps<T> = {
  rows: T[];
  columns: Column<T>[];
  /** Click handler — receives the row. Adds hover state if set. */
  onRowClick?: (row: T) => void;
  /** Default sort: { key, dir }. */
  initialSort?: { key: string; dir: "asc" | "desc" };
  emptyMessage?: string;
  testId?: string;
};

export function DataTable<T extends Record<string, unknown>>({
  rows,
  columns,
  onRowClick,
  initialSort,
  emptyMessage = "No rows.",
  testId,
}: DataTableProps<T>) {
  const [sort, setSort] = useState<{ key: string; dir: "asc" | "desc" } | null>(
    initialSort ?? null,
  );

  const sortedRows = useMemo(() => {
    if (!sort) return rows;
    const col = columns.find((c) => c.key === sort.key);
    if (!col) return rows;
    const getter =
      col.sortValue ??
      ((r: T) => {
        const v = r[sort.key];
        return typeof v === "number" || typeof v === "string" ? v : null;
      });
    const dir = sort.dir === "asc" ? 1 : -1;
    return [...rows].sort((a, b) => {
      const va = getter(a);
      const vb = getter(b);
      if (va === null || va === undefined) return 1;
      if (vb === null || vb === undefined) return -1;
      if (typeof va === "number" && typeof vb === "number") return (va - vb) * dir;
      return String(va).localeCompare(String(vb)) * dir;
    });
  }, [rows, columns, sort]);

  if (rows.length === 0) {
    return (
      <div
        className="qt-mono text-sm p-6 text-center"
        style={{ color: "var(--color-bone-muted)", border: "1px solid var(--color-border)" }}
      >
        {emptyMessage}
      </div>
    );
  }

  return (
    <table
      data-testid={testId}
      className="w-full qt-mono text-xs"
      style={{ borderCollapse: "collapse", background: "var(--color-card)" }}
    >
      <thead>
        <tr style={{ background: "var(--color-muted-bg)" }}>
          {columns.map((col) => {
            const isSorted = sort?.key === col.key;
            return (
              <th
                key={col.key}
                style={{
                  textAlign: col.align ?? "left",
                  padding: "8px 10px",
                  borderBottom: "1px solid var(--color-border)",
                  width: col.width,
                  textTransform: "uppercase",
                  letterSpacing: "0.06em",
                  fontSize: "0.7rem",
                  color: "var(--color-bone)",
                  cursor: col.sortable ? "pointer" : "default",
                  userSelect: "none",
                }}
                onClick={() => {
                  if (!col.sortable) return;
                  setSort((cur) => {
                    if (cur?.key !== col.key) return { key: col.key, dir: "desc" };
                    return { key: col.key, dir: cur.dir === "desc" ? "asc" : "desc" };
                  });
                }}
              >
                {col.header}
                {col.sortable && (
                  <span style={{ marginLeft: 4, color: "var(--color-rule)" }}>
                    {isSorted ? (sort?.dir === "desc" ? "▼" : "▲") : "↕"}
                  </span>
                )}
              </th>
            );
          })}
        </tr>
      </thead>
      <tbody>
        {sortedRows.map((row, i) => (
          <tr
            key={i}
            onClick={onRowClick ? () => onRowClick(row) : undefined}
            className={cn(onRowClick && "cursor-pointer")}
            style={{ background: "transparent" }}
            onMouseEnter={(e) => {
              if (onRowClick) e.currentTarget.style.background = "var(--color-card-hover)";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = "transparent";
            }}
          >
            {columns.map((col) => (
              <td
                key={col.key}
                style={{
                  textAlign: col.align ?? "left",
                  padding: "6px 10px",
                  borderBottom: "1px solid var(--color-border)",
                  color: "var(--color-bone-muted)",
                  fontVariantNumeric: "tabular-nums",
                }}
              >
                {col.render ? col.render(row) : String(row[col.key] ?? "—")}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
