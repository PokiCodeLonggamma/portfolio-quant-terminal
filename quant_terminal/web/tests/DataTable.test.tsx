import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DataTable, type Column } from "@/components/widgets/DataTable";

type Row = { ticker: string; pct: number };

const cols: Column<Row>[] = [
  { key: "ticker", header: "Ticker", sortable: true },
  { key: "pct", header: "1d %", align: "right", sortable: true },
];
const rows: Row[] = [
  { ticker: "ES", pct: 0.5 },
  { ticker: "NQ", pct: 1.2 },
  { ticker: "CL", pct: -0.8 },
];

describe("DataTable", () => {
  it("renders all rows", () => {
    render(<DataTable<Row> rows={rows} columns={cols} />);
    expect(screen.getByText("ES")).toBeInTheDocument();
    expect(screen.getByText("NQ")).toBeInTheDocument();
    expect(screen.getByText("CL")).toBeInTheDocument();
  });

  it("renders empty message when rows is []", () => {
    render(<DataTable<Row> rows={[]} columns={cols} emptyMessage="Nothing." />);
    expect(screen.getByText("Nothing.")).toBeInTheDocument();
  });

  it("calls onRowClick with the clicked row", () => {
    const onClick = vi.fn();
    render(<DataTable<Row> rows={rows} columns={cols} onRowClick={onClick} />);
    fireEvent.click(screen.getByText("NQ"));
    expect(onClick).toHaveBeenCalledTimes(1);
    expect(onClick.mock.calls[0][0]).toEqual({ ticker: "NQ", pct: 1.2 });
  });

  it("sorts when header is clicked", () => {
    render(<DataTable<Row> rows={rows} columns={cols} />);
    // Click "1d %" header → desc by default
    fireEvent.click(screen.getByText("1d %"));
    const cells = screen.getAllByText(/^(ES|NQ|CL)$/);
    // Desc order: NQ (1.2), ES (0.5), CL (-0.8)
    expect(cells[0].textContent).toBe("NQ");
    expect(cells[2].textContent).toBe("CL");
  });
});
