import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { KpiTile } from "@/components/widgets/KpiTile";

describe("KpiTile", () => {
  it("renders label, value, delta and hint", () => {
    render(
      <KpiTile
        label="NAV"
        value="€10 432"
        delta="+1.42%"
        deltaDir="pos"
        hint="vs yesterday"
      />,
    );
    expect(screen.getByText("NAV")).toBeInTheDocument();
    expect(screen.getByText("€10 432")).toBeInTheDocument();
    expect(screen.getByText("+1.42%")).toBeInTheDocument();
    expect(screen.getByText("vs yesterday")).toBeInTheDocument();
  });

  it("does not render delta when not provided", () => {
    render(<KpiTile label="Routes" value="17" />);
    expect(screen.queryByText("+1.42%")).not.toBeInTheDocument();
  });

  it("applies the accent attribute", () => {
    const { getByTestId } = render(
      <KpiTile label="Status" value="OK" accent="mint" />,
    );
    expect(getByTestId("kpi-tile")).toBeInTheDocument();
  });
});
