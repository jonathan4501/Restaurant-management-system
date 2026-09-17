/**
 * Shapes the cashier screens read. The generated OpenAPI types describe these responses as
 * free-form objects (drf-spectacular `responses={200: dict}`), so the field names here mirror
 * apps/payments/reports.py and apps/orders/serializers_read.py. Request bodies and paths still
 * come from lib/api/schema.d.ts — never hand-write those.
 *
 * Every money field is an integer number of pesewas.
 */

export type PaymentMethod = "CASH" | "MOMO_MTN" | "MOMO_TELECEL" | "MOMO_AT" | "CARD" | "BANK";

/** apps/floor/state_chip.py. `null` when a bill has nothing on it yet. */
export type BillState = "sent" | "cooking" | "food_ready" | "ready_to_pay" | "part_paid";

export type DrawerKind = "NO_SALE" | "PAID_OUT" | "PAID_IN";

export interface Shift {
  id: string;
  cashier_id: string;
  cashier_name?: string;
  opened_at?: string;
  closed_at: string | null;
  opening_float_pesewas: number;
  cash_payments_pesewas?: number;
  paid_out_pesewas?: number;
  paid_in_pesewas?: number;
  expected_cash_pesewas?: number | null;
  declared_cash_pesewas?: number | null;
  variance_pesewas?: number | null;
  totals_by_method?: Partial<Record<PaymentMethod, number>>;
  payment_count?: number;
}

export interface CurrentShiftResponse {
  shift: Shift | null;
}

export interface OpenBill {
  session_id: string;
  table_id: string;
  table_number: string;
  opened_at: string;
  order_count: number;
  bill_total_pesewas: number;
  paid_pesewas: number;
  balance_pesewas: number;
  state: BillState | null;
  /** false while any order is still SUBMITTED / PREPARING / READY — the server refuses payment. */
  payable: boolean;
}

export interface OpenBillsResponse {
  bills: OpenBill[];
  outstanding_pesewas: number;
}

export interface BillLineModifier {
  id?: string;
  name: string;
  price_pesewas: number;
}

export interface BillLine {
  item_id: string;
  menu_item_id: string;
  /** Snapshot taken when the item was ordered. Never re-priced from the menu. */
  name: string;
  unit_price_pesewas: number;
  quantity: number;
  line_total_pesewas: number;
  modifiers: BillLineModifier[];
  notes: string;
  order_id: string;
  order_number: number | null;
}

export interface BillDiscount {
  order_id: string;
  order_number: number | null;
  discount_pesewas: number;
}

export interface BillOrder {
  id: string;
  order_number: number | null;
  status: "DRAFT" | "SUBMITTED" | "PREPARING" | "READY" | "SERVED" | "CLOSED" | "VOIDED";
  total_pesewas: number;
  discount_pesewas: number;
}

export interface Bill {
  session_id: string;
  table_id: string;
  table_number: string;
  lines: BillLine[];
  discounts: BillDiscount[];
  bill_total_pesewas: number;
  paid_pesewas: number;
  balance_pesewas: number;
  orders: BillOrder[];
}

export interface PaymentResult {
  id: string;
  session_id: string;
  method: PaymentMethod;
  amount_pesewas: number;
  tendered_pesewas: number | null;
  change_pesewas: number | null;
  external_reference: string | null;
  bill_total_pesewas: number;
  paid_pesewas: number;
  balance_pesewas: number;
  settled: boolean;
}

export interface ZReportPayment {
  id: string;
  table_number: string;
  method: PaymentMethod;
  amount_pesewas: number;
  external_reference: string | null;
  recorded_at: string;
  voided_at: string | null;
}

export interface ZReportMovement {
  id: string;
  kind: DrawerKind;
  amount_pesewas: number;
  reason_code: string;
  note: string;
  recorded_at: string;
}

export interface ZReport extends Shift {
  /** Gross cash through the till. Labelled "Money taken" — never "Revenue". */
  money_taken_pesewas: number;
  payments: ZReportPayment[];
  movements: ZReportMovement[];
}
