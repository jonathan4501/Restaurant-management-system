import type { DiscountsByStaff, HourlyMoney, ShiftVariance, Variance } from "./types";
import { paymentMethodLabel } from "./labels";

/** Negative (short) cash counts are the problem rows — paint them late/danger. */
export function isCashShort(variancePesewas: number | null | undefined): boolean {
  return typeof variancePesewas === "number" && variancePesewas < 0;
}

export function varianceTileTone(problem: boolean): "ok" | "late" {
  return problem ? "late" : "ok";
}

/** Sort shifts so the worst shortfalls surface first; nulls last. */
export function sortShiftsByVariance(shifts: ShiftVariance[]): ShiftVariance[] {
  return [...shifts].sort((a, b) => {
    const av = a.variance_pesewas;
    const bv = b.variance_pesewas;
    if (av === null && bv === null) return 0;
    if (av === null) return 1;
    if (bv === null) return -1;
    return av - bv;
  });
}

export function discountStaffTotal(row: DiscountsByStaff): number {
  return row.value_pesewas;
}

export interface MixRow {
  method: string;
  label: string;
  pesewas: number;
  share: number;
}

/** Payment mix as labelled bars (design: not a pie). Share is 0–1 of the total. */
export function paymentMixRows(mix: Record<string, number>): MixRow[] {
  const entries = Object.entries(mix).filter(([, v]) => Number.isInteger(v) && v !== 0);
  const total = entries.reduce((sum, [, v]) => sum + v, 0);
  return entries
    .map(([method, pesewas]) => ({
      method,
      label: paymentMethodLabel(method),
      pesewas,
      share: total > 0 ? pesewas / total : 0,
    }))
    .sort((a, b) => b.pesewas - a.pesewas);
}

export interface HourBar {
  hour: number;
  label: string;
  money_taken_pesewas: number;
  isPeak: boolean;
  /** Final (current) hour rendered dimmer when still in progress. */
  inProgress: boolean;
}

export function hourlyBars(
  rows: HourlyMoney[],
  opts: { currentHour?: number | null } = {},
): HourBar[] {
  if (rows.length === 0) return [];
  let peak = -1;
  let peakValue = -1;
  for (const row of rows) {
    if (row.money_taken_pesewas > peakValue) {
      peakValue = row.money_taken_pesewas;
      peak = row.hour;
    }
  }
  const current = opts.currentHour ?? null;
  return rows.map((row) => ({
    hour: row.hour,
    label: `${row.hour.toString().padStart(2, "0")}:00`,
    money_taken_pesewas: row.money_taken_pesewas,
    isPeak: row.hour === peak && peakValue > 0,
    inProgress: current !== null && row.hour === current,
  }));
}

/** Headline numbers for the four variance tiles. */
export function varianceHeadlines(v: Variance) {
  const shortShifts = v.cash_variance_by_shift.filter((s) => isCashShort(s.variance_pesewas));
  const gapCount = v.order_number_gaps.reduce((n, g) => n + g.missing.length, 0);
  return {
    cashVariancePesewas: v.cash_variance_pesewas,
    shortShiftCount: shortShifts.length,
    voidCount: v.voids_after_acknowledgement.length,
    voidValuePesewas: v.void_value_pesewas,
    discountCompPesewas: v.discount_pesewas + v.comp_pesewas,
    discountStaffCount: v.discounts_by_staff.length,
    reopenedCount: v.reopened_count,
    gapCount,
  };
}
