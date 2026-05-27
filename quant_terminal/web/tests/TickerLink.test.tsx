import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TickerLink } from "@/components/widgets/TickerLink";

describe("TickerLink", () => {
  it("renders a link to /ticker/{logical}", () => {
    render(<TickerLink logical="ES" />);
    const link = screen.getByRole("link", { name: "ES" });
    expect(link).toHaveAttribute("href", "/ticker/ES");
  });

  it("uses label when provided", () => {
    render(<TickerLink logical="ES" label="S&P E-mini" />);
    expect(screen.getByRole("link", { name: "S&P E-mini" })).toBeInTheDocument();
  });

  it("URL-encodes special characters", () => {
    render(<TickerLink logical="BTC-USD" />);
    expect(screen.getByRole("link")).toHaveAttribute(
      "href",
      "/ticker/BTC-USD",
    );
  });
});
