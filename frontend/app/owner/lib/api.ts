/**
 * Owner reporting + session calls. Reporting paths are typed in schema.d.ts.
 * Owner login/totp/me are under-documented in OpenAPI (no body schemas yet), so those
 * three go through fetch with credentials — same base URL and Idempotency-Key rules.
 */

import { API_BASE_URL, IDEMPOTENCY_HEADER, api, isProblem, newIdempotencyKey, type Problem } from "@/lib/api/client";
import { tokens } from "@/lib/auth/tokens";

import { lastNBusinessDates } from "./dates";
import type {
  EventLog,
  LogFilter,
  OwnerMe,
  Patterns,
  Today,
  Variance,
  ZReport,
} from "./types";

export function problemMessage(err: unknown, fallback: string): string {
  if (isProblem(err)) return err.detail || err.title;
  if (err instanceof Error && err.message) return err.message;
  return fallback;
}

function unwrap<T>(result: { data?: unknown; error?: unknown }): T {
  if (result.error) throw result.error;
  return result.data as T;
}

function commonHeaders(extra?: Record<string, string>): HeadersInit {
  const headers: Record<string, string> = {
    Accept: "application/json",
    "Content-Type": "application/json",
    ...extra,
  };
  const device = tokens.device();
  const session = tokens.session();
  if (device) headers["X-Device-Token"] = device;
  if (session) headers["Authorization"] = `Bearer ${session}`;
  return headers;
}

async function ownerPost<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    credentials: "include",
    headers: commonHeaders({
      [IDEMPOTENCY_HEADER]: newIdempotencyKey(),
      "X-Client-Time": new Date().toISOString(),
    }),
    body: JSON.stringify(body),
  });
  const data: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    if (isProblem(data)) throw data;
    throw { type: "about:blank", title: "Error", status: response.status, code: "http_error", detail: "Request failed", errors: {} } satisfies Problem;
  }
  return data as T;
}

export async function ownerLogin(email: string, password: string): Promise<{ totp_required: boolean }> {
  return ownerPost("/api/v1/auth/owner/login", { email, password });
}

export async function ownerTotp(code: string): Promise<{ ok: boolean }> {
  return ownerPost("/api/v1/auth/owner/totp", { code });
}

export async function fetchOwnerMe(): Promise<OwnerMe> {
  const response = await fetch(`${API_BASE_URL}/api/v1/auth/owner/me`, {
    credentials: "include",
    headers: commonHeaders(),
    cache: "no-store",
  });
  const data: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    if (isProblem(data)) throw data;
    throw Object.assign(new Error("Not signed in"), { status: response.status });
  }
  return data as OwnerMe;
}

export async function ownerLogout(): Promise<void> {
  await fetch(`${API_BASE_URL}/api/v1/auth/logout`, {
    method: "POST",
    credentials: "include",
    headers: commonHeaders({
      [IDEMPOTENCY_HEADER]: newIdempotencyKey(),
      "X-Client-Time": new Date().toISOString(),
    }),
    body: "{}",
  }).catch(() => undefined);
}

export async function fetchVariance(days = 7): Promise<Variance> {
  const { from, to } = lastNBusinessDates(days);
  return unwrap<Variance>(
    await api.GET("/api/v1/reports/variance", { params: { query: { from, to } } }),
  );
}

export async function fetchToday(): Promise<Today> {
  return unwrap<Today>(await api.GET("/api/v1/reports/today"));
}

export async function fetchPatterns(days = 7): Promise<Patterns> {
  const { from, to } = lastNBusinessDates(days);
  return unwrap<Patterns>(
    await api.GET("/api/v1/reports/patterns", { params: { query: { from, to } } }),
  );
}

export async function fetchEventLog(
  filter: LogFilter = {},
  cursor?: number | null,
): Promise<EventLog> {
  return unwrap<EventLog>(
    await api.GET("/api/v1/events/log", {
      params: {
        query: {
          actor_id: filter.actor_id,
          type: filter.type,
          aggregate_type: filter.aggregate_type,
          from: filter.from,
          to: filter.to,
          flagged: filter.flagged,
          cursor: cursor ?? undefined,
          limit: 50,
        },
      },
    }),
  );
}

export async function fetchZReport(shiftId: string): Promise<ZReport> {
  return unwrap<ZReport>(
    await api.GET("/api/v1/shifts/{shift_id}/z-report", {
      params: { path: { shift_id: shiftId } },
    }),
  );
}
