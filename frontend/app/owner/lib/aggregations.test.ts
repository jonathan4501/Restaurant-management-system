import { describe, expect, it } from "vitest";

import {
  hourlyBars,
  isCashShort,
  paymentMixRows,
  sortShiftsByVariance,
  varianceHeadlines,
  varianceTileTone,
} from "./aggregations";
import type { ShiftVariance, Variance } from "./types";

const emptyVariance = (): Variance => ({
  date_from: "2026-09-10",
  date_to: "2026-09-16",
  voids_after_acknowledgement: [],
  void_value_pesewas: 0,
  discounts_by_staff: [],
  discount_pesewas: 0,
  comp_pesewas: 0,
  reopened_bills: [],
  reopened_count: 0,
  manager_reopens: 0,
  cash_variance_by_shift: [],
  cash_variance_pesewas: 0,
  order_number_gaps: [],
});

describe("variance colouring", () => {
  it("marks negative cash variance as short / late", () => {
    expect(isCashShort(-4500)).toBe(true);
    expect(isCashShort(0)).toBe(false);
    expect(isCashShort(200)).toBe(false);
    expect(isCashShort(null)).toBe(false);
    expect(varianceTileTone(true)).toBe("late");
    expect(varianceTileTone(false)).toBe("ok");
  });

  it("sorts short counts before overs and nulls", () => {
    const shifts: ShiftVariance[] = [
      {
        shift_id: "a",
        cashier: "Ama",
        cashier_id: "1",
        opened_at: "2026-09-16T10:00:00Z",
        closed_at: "2026-09-16T18:00:00Z",
        expected_cash_pesewas: 10000,
        declared_cash_pesewas: 10500,
        variance_pesewas: 500,
      },
      {
        shift_id: "b",
        cashier: "Kofi",
        cashier_id: "2",
        opened_at: "2026-09-16T10:00:00Z",
        closed_at: null,
        expected_cash_pesewas: null,
        declared_cash_pesewas: null,
        variance_pesewas: null,
      },
      {
        shift_id: "c",
        cashier: "Yaw",
        cashier_id: "3",
        opened_at: "2026-09-15T10:00:00Z",
        closed_at: "2026-09-15T18:00:00Z",
        expected_cash_pesewas: 246300,
        declared_cash_pesewas: 241800,
        variance_pesewas: -4500,
      },
    ];
    expect(sortShiftsByVariance(shifts).map((s) => s.shift_id)).toEqual(["c", "a", "b"]);
  });

  it("summarises variance headlines for the leak panel", () => {
    const v = emptyVariance();
    v.void_value_pesewas = 19500;
    v.voids_after_acknowledgement = [
      {
        order_id: null,
        order_number: 1042,
        table_number: "9",
        value_pesewas: 19500,
        status_at_void: "PREPARING",
        reason_code: "WRONG_TABLE",
        actor: "Kofi",
        actor_role: "WAITER",
        authorised_by: "Ama",
        at: "2026-09-16T19:21:00Z",
      },
    ];
    v.discount_pesewas = 5000;
    v.comp_pesewas = 3400;
    v.reopened_count = 1;
    v.cash_variance_pesewas = -4500;
    v.cash_variance_by_shift = [
      {
        shift_id: "c",
        cashier: "Yaw",
        cashier_id: "3",
        opened_at: "2026-09-15T10:00:00Z",
        closed_at: "2026-09-15T18:00:00Z",
        expected_cash_pesewas: 246300,
        declared_cash_pesewas: 241800,
        variance_pesewas: -4500,
      },
    ];
    v.order_number_gaps = [{ business_date: "2026-09-16", missing: [1040, 1045] }];
    const h = varianceHeadlines(v);
    expect(h.voidCount).toBe(1);
    expect(h.voidValuePesewas).toBe(19500);
    expect(h.discountCompPesewas).toBe(8400);
    expect(h.shortShiftCount).toBe(1);
    expect(h.gapCount).toBe(2);
  });
});

describe("pattern aggregations", () => {
  it("builds payment mix shares without floats in the money column", () => {
    const rows = paymentMixRows({ CASH: 10000, CARD: 5000, MOMO_MTN: 5000 });
    expect(rows[0]?.method).toBe("CASH");
    expect(rows[0]?.pesewas).toBe(10000);
    expect(rows[0]?.share).toBeCloseTo(0.5);
    expect(rows.every((r) => Number.isInteger(r.pesewas))).toBe(true);
  });

  it("flags the peak hour and the in-progress hour", () => {
    const bars = hourlyBars(
      [
        { hour: 12, money_taken_pesewas: 10000 },
        { hour: 13, money_taken_pesewas: 50000 },
        { hour: 14, money_taken_pesewas: 20000 },
      ],
      { currentHour: 14 },
    );
    expect(bars.find((b) => b.isPeak)?.hour).toBe(13);
    expect(bars.find((b) => b.inProgress)?.hour).toBe(14);
  });
});
