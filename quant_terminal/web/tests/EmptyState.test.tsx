import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EmptyState } from "@/components/widgets/EmptyState";

describe("EmptyState", () => {
  it("renders default", () => {
    render(<EmptyState />);
    expect(screen.getByText("No data")).toBeInTheDocument();
    expect(screen.getByText("📭")).toBeInTheDocument();
  });

  it("renders custom title + text + icon", () => {
    render(<EmptyState title="Try again" text="Upload first" icon="📥" />);
    expect(screen.getByText("Try again")).toBeInTheDocument();
    expect(screen.getByText("Upload first")).toBeInTheDocument();
    expect(screen.getByText("📥")).toBeInTheDocument();
  });
});
