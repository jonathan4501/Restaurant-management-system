/**
 * Response shapes for owner reporting. Paths/params come from lib/api/schema.d.ts;
 * these aliases keep components free of the generated `components["schemas"]` noise.
 */

import type { components } from "@/lib/api/schema";

export type Today = components["schemas"]["Today"];
export type Variance = components["schemas"]["Variance"];
export type Patterns = components["schemas"]["Patterns"];
export type ShiftVariance = components["schemas"]["ShiftVariance"];
export type VoidAfterAck = components["schemas"]["VoidAfterAck"];
export type DiscountsByStaff = components["schemas"]["DiscountsByStaff"];
export type ReopenedBill = components["schemas"]["ReopenedBill"];
export type OrderNumberGap = components["schemas"]["OrderNumberGap"];
export type HourlyMoney = components["schemas"]["HourlyMoney"];
export type BestSeller = components["schemas"]["BestSeller"];
export type StationTiming = components["schemas"]["StationTiming"];
export type EventLog = components["schemas"]["EventLog"];
export type EventLogRow = components["schemas"]["EventLogRow"];

export interface OwnerMe {
  id: string;
  name: string;
  email: string;
  role: "OWNER";
  restaurant_id: string;
}

/** Z-report subset the owner modal needs (same contract as cashier CloseShiftSheet). */
export interface ZReport {
  money_taken_pesewas: number;
  by_method?: Record<string, number>;
  expected_cash_pesewas?: number | null;
  declared_cash_pesewas?: number | null;
  variance_pesewas?: number | null;
  movements?: Array<{
    kind: string;
    amount_pesewas: number;
    note?: string | null;
  }>;
}

export type LogFilter = {
  actor_id?: string;
  type?: string;
  aggregate_type?: string;
  from?: string;
  to?: string;
  flagged?: boolean;
};

/** Deep-link presets from the variance panel into the event log. */
export type LogPreset =
  | { kind: "voids" }
  | { kind: "discounts"; actor_id?: string }
  | { kind: "reopens" }
  | { kind: "cash"; shift_id?: string }
  | { kind: "gaps" };
