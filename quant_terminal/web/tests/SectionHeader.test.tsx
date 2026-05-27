import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SectionHeader } from "@/components/widgets/SectionHeader";

describe("SectionHeader", () => {
  it("renders title + subtitle + meta + § number", () => {
    render(
      <SectionHeader
        sectionNumber="01"
        title="Cross-Asset"
        subtitle="99 contracts × 10 classes"
        meta="MARKETS / CRS"
      />,
    );
    expect(screen.getByText("Cross-Asset")).toBeInTheDocument();
    expect(screen.getByText("99 contracts × 10 classes")).toBeInTheDocument();
    expect(screen.getByText("MARKETS / CRS")).toBeInTheDocument();
    expect(screen.getByText(/01/)).toBeInTheDocument();
  });

  it("works without optional fields", () => {
    render(<SectionHeader title="Standalone" />);
    expect(screen.getByText("Standalone")).toBeInTheDocument();
  });
});
