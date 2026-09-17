/**
 * Every call the cashier screens make. Paths and request bodies come from the generated
 * lib/api/schema.d.ts; the response bodies are documented as free-form objects by
 * drf-spectacular, so they are narrowed to ./types here at the single point they arrive.
 *
 * The API client puts a fresh UUIDv7 Idempotency-Key and X-Client-Time on every POST
 * (lib/api/client.ts), so nothing here has to remember to.
 */

import { api, IDEMPOTENCY_HEADER, isProblem, type Problem } from "@/lib/api/client";

import type {
  Bill,
  CurrentShiftResponse,
  DrawerKind,
  OpenBillsResponse,
  PaymentMethod,
  PaymentResult,
  Shift,
  ZReport,
} from "./types";

/** The manager-authorisation block (docs/09-api-contract.md §1). Not in the generated body types. */
export interface Authorisation {
  token: string;
  reason_code: string;
  note?: string;
}

/**
 * openapi-fetch types request bodies exactly, and `authorisation` is read off the raw body by
 * CommandView rather than declared on each input serializer. This is the one place that joins them.
 */
function withAuthorisation<T extends object>(body: T, authorisation?: Authorisation): T {
  return (authorisation ? { ...body, authorisation } : body) as T;
}

/**
 * For a command that carries the new entity's id, that id IS the idempotency key. The client
 * middleware would otherwise mint a fresh one per attempt, so a double-tap would reach the server
 * as a second command with the same payment id and come back 409 instead of the original response.
 */
function keyedBy(id: string): { headers: Record<string, string> } {
  return { headers: { [IDEMPOTENCY_HEADER]: id } };
}

export function problemMessage(err: unknown, fallback: string): string {
  if (isProblem(err)) return err.detail || err.title;
  if (err instanceof Error && err.message) return err.message;
  return fallback;
}

export function problemCode(err: unknown): string | null {
  return isProblem(err) ? (err as Problem).code : null;
}

function unwrap<T>(result: { data?: unknown; error?: unknown }): T {
  if (result.error) throw result.error;
  return result.data as T;
}

// ------------------------------------------------------------------ shifts

export async function fetchCurrentShift(): Promise<Shift | null> {
  const body = unwrap<CurrentShiftResponse>(await api.GET("/api/v1/shifts/current"));
  return body?.shift ?? null;
}

export async function openShift(id: string, openingFloatPesewas: number): Promise<Shift> {
  return unwrap<Shift>(
    await api.POST("/api/v1/shifts", {
      body: { id, opening_float_pesewas: openingFloatPesewas },
      ...keyedBy(id),
    }),
  );
}

export async function closeShift(
  shiftId: string,
  declaredCashPesewas: number,
  note: string,
): Promise<Shift> {
  return unwrap<Shift>(
    await api.POST("/api/v1/shifts/{shift_id}/close", {
      params: { path: { shift_id: shiftId } },
      body: { declared_cash_pesewas: declaredCashPesewas, note },
    }),
  );
}

export async function fetchZReport(shiftId: string): Promise<ZReport> {
  return unwrap<ZReport>(
    await api.GET("/api/v1/shifts/{shift_id}/z-report", { params: { path: { shift_id: shiftId } } }),
  );
}

export async function recordDrawerMovement(
  shiftId: string,
  input: { kind: DrawerKind; amount_pesewas: number; note: string },
  authorisation: Authorisation,
): Promise<{ id: string }> {
  return unwrap<{ id: string }>(
    await api.POST("/api/v1/shifts/{shift_id}/movements", {
      params: { path: { shift_id: shiftId } },
      body: withAuthorisation(
        { ...input, reason_code: authorisation.reason_code },
        authorisation,
      ),
    }),
  );
}

// ------------------------------------------------------------------ bills

export async function fetchOpenBills(): Promise<OpenBillsResponse> {
  const body = unwrap<OpenBillsResponse>(await api.GET("/api/v1/bills/open"));
  return { bills: body?.bills ?? [], outstanding_pesewas: body?.outstanding_pesewas ?? 0 };
}

export async function fetchBill(sessionId: string): Promise<Bill> {
  const body = unwrap<Bill>(
    await api.GET("/api/v1/sessions/{session_id}/bill", {
      params: { path: { session_id: sessionId } },
    }),
  );
  return { ...body, lines: body?.lines ?? [], discounts: body?.discounts ?? [], orders: body?.orders ?? [] };
}

// ------------------------------------------------------------------ money

export interface RecordPaymentInput {
  id: string;
  method: PaymentMethod;
  amount_pesewas: number;
  tendered_pesewas?: number | null;
  external_reference?: string | null;
}

export async function recordPayment(
  sessionId: string,
  input: RecordPaymentInput,
): Promise<PaymentResult> {
  return unwrap<PaymentResult>(
    await api.POST("/api/v1/sessions/{session_id}/payments", {
      params: { path: { session_id: sessionId } },
      body: input,
      ...keyedBy(input.id),
    }),
  );
}

export async function voidPayment(
  paymentId: string,
  authorisation: Authorisation,
): Promise<{ id: string }> {
  return unwrap<{ id: string }>(
    await api.POST("/api/v1/payments/{payment_id}/void", {
      params: { path: { payment_id: paymentId } },
      body: withAuthorisation({ reason_code: authorisation.reason_code, note: "" }, authorisation),
    }),
  );
}

export async function applyDiscount(
  orderId: string,
  input: { kind: "PERCENT" | "AMOUNT"; value: number },
  authorisation: Authorisation,
): Promise<unknown> {
  return unwrap<unknown>(
    await api.POST("/api/v1/orders/{order_id}/discount", {
      params: { path: { order_id: orderId } },
      body: withAuthorisation(
        { ...input, reason_code: authorisation.reason_code, note: "" },
        authorisation,
      ),
    }),
  );
}

export async function voidOrder(
  orderId: string,
  authorisation: Authorisation,
): Promise<unknown> {
  return unwrap<unknown>(
    await api.POST("/api/v1/orders/{order_id}/void", {
      params: { path: { order_id: orderId } },
      body: withAuthorisation({ reason_code: authorisation.reason_code, note: "" }, authorisation),
    }),
  );
}

export async function reopenSession(
  sessionId: string,
  authorisation: Authorisation,
): Promise<unknown> {
  return unwrap<unknown>(
    await api.POST("/api/v1/sessions/{session_id}/reopen", {
      params: { path: { session_id: sessionId } },
      body: withAuthorisation({ reason_code: authorisation.reason_code, note: "" }, authorisation),
    }),
  );
}
