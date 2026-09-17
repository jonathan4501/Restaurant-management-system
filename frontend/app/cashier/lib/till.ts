/**
 * The cashier's arithmetic. Everything here is integer pesewas in and integer pesewas out —
 * no floats, no `/ 100`. Formatting happens in the components via formatPesewas.
 *
 * These functions mirror guard rails the server already enforces (apps/payments/commands.py):
 * the UI refuses early so the cashier sees why, the server refuses finally so it is true.
 */

import type { PaymentMethod } from "./types";

export const PAYMENT_METHODS: readonly PaymentMethod[] = [
  "CASH",
  "MOMO_MTN",
  "MOMO_TELECEL",
  "MOMO_AT",
  "CARD",
  "BANK",
] as const;

const METHOD_LABELS: Record<PaymentMethod, string> = {
  CASH: "Cash",
  MOMO_MTN: "MTN MoMo",
  MOMO_TELECEL: "Telecel Cash",
  MOMO_AT: "AirtelTigo",
  CARD: "Card",
  BANK: "Bank",
};

export function methodLabel(method: PaymentMethod): string {
  return METHOD_LABELS[method];
}

/** Every method but cash is settled elsewhere and carries a reference the cashier keys in. */
export function needsReference(method: PaymentMethod): boolean {
  return method !== "CASH";
}

/**
 * MoMo ids get read off a phone screen by a tired cashier: strip every space, upper-case.
 * Mirrors normalise_reference() in apps/payments/commands.py so what is shown is what is stored.
 */
export function normaliseReference(raw: string): string {
  return raw.replace(/\s+/g, "").toUpperCase();
}

/** Never let the UI send more than is owed — the server answers 422 `overpayment`. */
export function capToBalance(amountPesewas: number, balancePesewas: number): number {
  if (amountPesewas < 0) return 0;
  return Math.min(amountPesewas, Math.max(balancePesewas, 0));
}

/**
 * Change owed on a cash payment. Cash tendered may exceed the amount being paid (that is the
 * whole point); tendering less than the amount is not a payment, it is a mistake.
 */
export function changeFor(tenderedPesewas: number, amountPesewas: number): number | null {
  if (!Number.isInteger(tenderedPesewas) || !Number.isInteger(amountPesewas)) {
    throw new TypeError("changeFor works in integer pesewas only");
  }
  if (tenderedPesewas < amountPesewas) return null;
  return tenderedPesewas - amountPesewas;
}

/** The notes a Ghanaian till actually holds, in pesewas. */
const NOTES_PESEWAS = [5000, 10000, 20000] as const;

/**
 * Quick-tender buttons: the exact amount first, then the notes a guest would realistically hand
 * over. Nothing below the amount (it would not cover it) and nothing duplicated.
 */
export function quickTenders(amountPesewas: number): number[] {
  const out = [amountPesewas];
  for (const note of NOTES_PESEWAS) {
    if (note > amountPesewas) out.push(note);
  }
  // Round up to the next whole note above the amount so a big bill still gets one sensible option.
  const roundUp = Math.ceil(amountPesewas / 20000) * 20000;
  if (roundUp > amountPesewas && !out.includes(roundUp)) out.push(roundUp);
  return [...new Set(out)].sort((a, b) => a - b);
}

/**
 * Split a bill n ways without losing a pesewa: the remainder goes to the first payers, so
 * 10001 split 3 ways is 3334 + 3334 + 3333, not 3333.67 three times.
 */
export function splitEvenly(totalPesewas: number, ways: number): number[] {
  if (!Number.isInteger(totalPesewas) || totalPesewas < 0) {
    throw new TypeError("splitEvenly works on a non-negative integer number of pesewas");
  }
  if (!Number.isInteger(ways) || ways < 1) throw new TypeError("ways must be a positive integer");
  const base = Math.floor(totalPesewas / ways);
  const remainder = totalPesewas - base * ways;
  return Array.from({ length: ways }, (_, i) => base + (i < remainder ? 1 : 0));
}

/** A bill is settled the moment nothing is owed. There is no rounding step to disagree about. */
export function isSettled(balancePesewas: number): boolean {
  return balancePesewas <= 0;
}

/** GH₵ 999,999.99. A bill past this is a typo, not a party. */
const PAD_MAX_PESEWAS = 99_999_999;

/**
 * The till keypad: digits shift in from the right, the way every card machine in Accra behaves.
 * Tapping 1, 3, 3, 0, 0 gives GH₵ 133.00. There is no decimal point to get wrong.
 */
export function padPush(currentPesewas: number, key: string): number {
  if (!/^\d{1,2}$/.test(key)) return currentPesewas;
  const next = currentPesewas * (key.length === 2 ? 100 : 10) + Number(key);
  return next > PAD_MAX_PESEWAS ? currentPesewas : next;
}

export function padPop(currentPesewas: number): number {
  return Math.floor(currentPesewas / 10);
}

export interface PaySheetState {
  method: PaymentMethod;
  /** What the guest is paying now, already capped to the balance. */
  amountPesewas: number;
  /** Cash handed over. Ignored for every other method. */
  tenderedPesewas: number;
  reference: string;
}

export interface PaySheetView {
  amountPesewas: number;
  tenderedPesewas: number | null;
  changePesewas: number | null;
  reference: string | null;
  /** Balance once this payment lands, if the server accepts it. */
  balanceAfterPesewas: number;
  settles: boolean;
  blockedReason: string | null;
}

/**
 * One place that decides what the pay sheet shows and whether Submit is live. The components
 * render this; the tests assert on it.
 */
export function paySheetView(state: PaySheetState, balancePesewas: number): PaySheetView {
  const amountPesewas = capToBalance(state.amountPesewas, balancePesewas);
  const cash = state.method === "CASH";
  const tenderedPesewas = cash ? Math.max(state.tenderedPesewas, 0) : null;
  const changePesewas = cash ? changeFor(tenderedPesewas ?? 0, amountPesewas) : null;
  const reference = needsReference(state.method) ? normaliseReference(state.reference) || null : null;
  const balanceAfterPesewas = balancePesewas - amountPesewas;

  let blockedReason: string | null = null;
  if (balancePesewas <= 0) blockedReason = "This bill is already paid in full.";
  else if (amountPesewas <= 0) blockedReason = "Enter an amount.";
  else if (cash && changePesewas === null) blockedReason = "Cash given is less than the amount.";

  return {
    amountPesewas,
    tenderedPesewas,
    changePesewas,
    reference,
    balanceAfterPesewas,
    settles: balanceAfterPesewas === 0 && amountPesewas > 0,
    blockedReason,
  };
}

/**
 * Why the pay button is dead, in words the cashier can act on. The server returns 409
 * `unserved_orders` for the same case; saying it up front saves the round trip and the confusion.
 */
export function payBlockedReason(bill: {
  balance_pesewas: number;
  orders: { status: string; order_number: number | null }[];
}): string | null {
  if (bill.balance_pesewas <= 0) return "Paid in full.";
  const unserved = bill.orders.filter((o) =>
    ["SUBMITTED", "PREPARING", "READY"].includes(o.status),
  );
  if (unserved.length === 0) return null;
  const numbers = unserved.map((o) => (o.order_number ? `#${o.order_number}` : "an order")).join(", ");
  return `Serve ${numbers} before taking payment.`;
}

/** Minutes since the bill was opened — the cashier's "how long have they been sitting there". */
export function ageMinutes(openedAt: string, now: number = Date.now()): number {
  const opened = Date.parse(openedAt);
  if (Number.isNaN(opened)) return 0;
  return Math.max(0, Math.floor((now - opened) / 60_000));
}

export function formatAge(minutes: number): string {
  if (minutes < 60) return `${minutes}m`;
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
}

const STATE_LABELS: Record<string, string> = {
  sent: "Sent",
  cooking: "Cooking",
  food_ready: "Food ready",
  ready_to_pay: "Ready to pay",
  part_paid: "Part paid",
};

export function stateLabel(state: string | null): string {
  return state ? STATE_LABELS[state] ?? state : "Seated";
}
