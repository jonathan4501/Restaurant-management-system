import { describe, expect, it } from "vitest";

import { formatPesewas, parsePesewasInput } from "./money";

describe("formatPesewas", () => {
  it("formats cedis and pesewas", () => {
    expect(formatPesewas(7500)).toBe("GH₵ 75.00");
    expect(formatPesewas(5)).toBe("GH₵ 0.05");
    expect(formatPesewas(1234567)).toBe("GH₵ 12,345.67");
    expect(formatPesewas(0)).toBe("GH₵ 0.00");
  });
  it("handles negatives (variance) and no-symbol", () => {
    expect(formatPesewas(-2000)).toBe("-GH₵ 20.00");
    expect(formatPesewas(2000, { symbol: false })).toBe("20.00");
  });
  it("refuses non-integers", () => {
    expect(() => formatPesewas(75.5)).toThrow(TypeError);
  });
});

describe("parsePesewasInput", () => {
  it("parses cashier input as integers", () => {
    expect(parsePesewasInput("30")).toBe(3000);
    expect(parsePesewasInput("30.5")).toBe(3050);
    expect(parsePesewasInput("30.05")).toBe(3005);
    expect(parsePesewasInput("1,250.00")).toBe(125000);
    expect(parsePesewasInput("GH₵ 12")).toBe(1200);
    expect(parsePesewasInput(".5")).toBe(50);
  });
  it("rejects garbage", () => {
    expect(parsePesewasInput("")).toBeNull();
    expect(parsePesewasInput("-5")).toBeNull();
    expect(parsePesewasInput("1.234")).toBeNull();
    expect(parsePesewasInput("abc")).toBeNull();
  });
  it("never loses a pesewa to floating point", () => {
    // 0.1 + 0.2 territory: string arithmetic only
    expect(parsePesewasInput("0.29")).toBe(29);
    expect(parsePesewasInput("1.13")).toBe(113);
  });
});
