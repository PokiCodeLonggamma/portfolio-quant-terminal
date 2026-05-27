import { describe, expect, it } from "vitest";

import { colorPct, fmtEur, fmtPct } from "@/lib/format";

describe("fmtEur", () => {
  it("formats with thin-space separator", () => {
    expect(fmtEur(10432)).toBe("€10 432");
  });
  it("handles negative", () => {
    expect(fmtEur(-1234)).toBe("-€1 234");
  });
  it("returns — for nullish/NaN", () => {
    expect(fmtEur(null)).toBe("—");
    expect(fmtEur(undefined)).toBe("—");
    expect(fmtEur(NaN)).toBe("—");
  });
});

describe("fmtPct", () => {
  it("formats positive with +", () => {
    expect(fmtPct(0.0142)).toBe("+1.42%");
  });
  it("formats negative", () => {
    expect(fmtPct(-0.005)).toBe("-0.50%");
  });
});

describe("colorPct", () => {
  it("returns mint for positive, mercury for negative", () => {
    expect(colorPct(0.01)).toContain("mint");
    expect(colorPct(-0.01)).toContain("mercury");
    expect(colorPct(0)).toContain("muted");
    expect(colorPct(null)).toContain("muted");
  });
});
