import { describe, expect, it } from "vitest";

import {
  ageMinutes,
  capToBalance,
  changeFor,
  formatAge,
  isSettled,
  normaliseReference,
  padPop,
  padPush,
  payBlockedReason,
  paySheetView,
  quickTenders,
  splitEvenly,
} from "./till";

describe("changeFor", () => {
  it("is exact integer arithmetic", () => {
    expect(changeFor(20000, 13300)).toBe(6700);
    expect(changeFor(13300, 13300)).toBe(0);
    expect(changeFor(10000, 2999)).toBe(7001);
  });
  it("returns null when the cash handed over does not cover the amount", () => {
    expect(changeFor(5000, 13300)).toBeNull();
  });
  it("refuses anything that is not an integer number of pesewas", () => {
    expect(() => changeFor(133.5, 100)).toThrow(TypeError);
    expect(() => changeFor(200, 13.37)).toThrow(TypeError);
  });
});

describe("capToBalance", () => {
  it("never lets a payment exceed the balance", () => {
    expect(capToBalance(20000, 13300)).toBe(13300);
    expect(capToBalance(5000, 13300)).toBe(5000);
    expect(capToBalance(13300, 13300)).toBe(13300);
  });
  it("floors at zero", () => {
    expect(capToBalance(-500, 13300)).toBe(0);
    expect(capToBalance(5000, 0)).toBe(0);
    expect(capToBalance(5000, -100)).toBe(0);
  });
});

describe("normaliseReference", () => {
  it("strips spaces and upper-cases, as the server does", () => {
    expect(normaliseReference("  mp2609 1234 5678  ")).toBe("MP260912345678");
    expect(normaliseReference("abc-123")).toBe("ABC-123");
    expect(normaliseReference("   ")).toBe("");
  });
});

describe("quickTenders", () => {
  it("offers the exact amount first, then the notes above it", () => {
    expect(quickTenders(13300)).toEqual([13300, 20000]);
    expect(quickTenders(2500)).toEqual([2500, 5000, 10000, 20000]);
  });
  it("never offers less than the amount", () => {
    expect(quickTenders(26500).every((t) => t >= 26500)).toBe(true);
    expect(quickTenders(26500)).toEqual([26500, 40000]);
  });
  it("collapses duplicates when the amount is already a note", () => {
    expect(quickTenders(20000)).toEqual([20000]);
  });
});

describe("splitEvenly", () => {
  it("never loses or invents a pesewa", () => {
    expect(splitEvenly(10001, 3)).toEqual([3334, 3334, 3333]);
    expect(splitEvenly(10001, 3).reduce((a, b) => a + b, 0)).toBe(10001);
    expect(splitEvenly(13300, 4)).toEqual([3325, 3325, 3325, 3325]);
    expect(splitEvenly(13301, 4).reduce((a, b) => a + b, 0)).toBe(13301);
  });
  it("handles the degenerate cases", () => {
    expect(splitEvenly(0, 4)).toEqual([0, 0, 0, 0]);
    expect(splitEvenly(999, 1)).toEqual([999]);
  });
  it("refuses floats and nonsense ways", () => {
    expect(() => splitEvenly(100.5, 2)).toThrow(TypeError);
    expect(() => splitEvenly(-100, 2)).toThrow(TypeError);
    expect(() => splitEvenly(100, 0)).toThrow(TypeError);
  });
});

describe("the keypad", () => {
  it("shifts digits in from the right", () => {
    let value = 0;
    for (const key of ["1", "3", "3", "0", "0"]) value = padPush(value, key);
    expect(value).toBe(13300);
  });
  it("treats 00 as two digits", () => {
    expect(padPush(133, "00")).toBe(13300);
    expect(padPush(0, "00")).toBe(0);
  });
  it("refuses to run past GH₵ 999,999.99 rather than wrap", () => {
    expect(padPush(99_999_999, "5")).toBe(99_999_999);
    expect(padPush(9_999_999, "9")).toBe(99_999_999);
  });
  it("backspaces one digit at a time and stops at zero", () => {
    expect(padPop(13300)).toBe(1330);
    expect(padPop(1)).toBe(0);
    expect(padPop(0)).toBe(0);
  });
});

describe("paySheetView", () => {
  const cash = { method: "CASH" as const, amountPesewas: 13300, tenderedPesewas: 20000, reference: "" };

  it("shows change and settles the bill when the amount clears the balance", () => {
    const view = paySheetView(cash, 13300);
    expect(view.amountPesewas).toBe(13300);
    expect(view.changePesewas).toBe(6700);
    expect(view.balanceAfterPesewas).toBe(0);
    expect(view.settles).toBe(true);
    expect(view.blockedReason).toBeNull();
  });

  it("caps the amount at the balance but lets the cash tendered exceed it", () => {
    const view = paySheetView({ ...cash, amountPesewas: 50000, tenderedPesewas: 50000 }, 13300);
    expect(view.amountPesewas).toBe(13300);
    expect(view.tenderedPesewas).toBe(50000);
    expect(view.changePesewas).toBe(36700);
  });

  it("blocks when the cash handed over is short", () => {
    const view = paySheetView({ ...cash, tenderedPesewas: 10000 }, 13300);
    expect(view.changePesewas).toBeNull();
    expect(view.blockedReason).toBe("Cash given is less than the amount.");
  });

  it("leaves a part payment open", () => {
    const view = paySheetView({ ...cash, amountPesewas: 6650, tenderedPesewas: 6650 }, 13300);
    expect(view.balanceAfterPesewas).toBe(6650);
    expect(view.settles).toBe(false);
  });

  it("normalises the reference for MoMo and ignores tendered", () => {
    const view = paySheetView(
      { method: "MOMO_MTN", amountPesewas: 6650, tenderedPesewas: 99999, reference: " mp 2609 abc " },
      13300,
    );
    expect(view.reference).toBe("MP2609ABC");
    expect(view.tenderedPesewas).toBeNull();
    expect(view.changePesewas).toBeNull();
    expect(view.blockedReason).toBeNull();
  });

  it("blocks an empty amount and a bill with nothing owing", () => {
    expect(paySheetView({ ...cash, amountPesewas: 0 }, 13300).blockedReason).toBe("Enter an amount.");
    expect(paySheetView(cash, 0).blockedReason).toBe("This bill is already paid in full.");
  });

  it("settles a four-way split exactly", () => {
    const shares = splitEvenly(13300, 4);
    let balance = 13300;
    for (const share of shares) {
      const view = paySheetView(
        { method: "MOMO_MTN", amountPesewas: share, tenderedPesewas: 0, reference: "mp1" },
        balance,
      );
      expect(view.blockedReason).toBeNull();
      balance = view.balanceAfterPesewas;
    }
    expect(balance).toBe(0);
    expect(isSettled(balance)).toBe(true);
  });
});

describe("payBlockedReason", () => {
  it("names the orders still in the kitchen", () => {
    expect(
      payBlockedReason({
        balance_pesewas: 13300,
        orders: [
          { status: "SERVED", order_number: 1046 },
          { status: "PREPARING", order_number: 1047 },
        ],
      }),
    ).toBe("Serve #1047 before taking payment.");
  });
  it("clears once everything is served", () => {
    expect(
      payBlockedReason({ balance_pesewas: 13300, orders: [{ status: "SERVED", order_number: 1046 }] }),
    ).toBeNull();
  });
  it("says so when there is nothing left to pay", () => {
    expect(payBlockedReason({ balance_pesewas: 0, orders: [] })).toBe("Paid in full.");
  });
});

describe("bill age", () => {
  it("counts whole minutes from the server timestamp", () => {
    const now = Date.parse("2026-09-14T19:42:00Z");
    expect(ageMinutes("2026-09-14T19:12:00Z", now)).toBe(30);
    expect(ageMinutes("2026-09-14T19:42:30Z", now)).toBe(0);
    expect(ageMinutes("not-a-time", now)).toBe(0);
  });
  it("reads as hours once it is past an hour", () => {
    expect(formatAge(45)).toBe("45m");
    expect(formatAge(95)).toBe("1h 35m");
  });
});
