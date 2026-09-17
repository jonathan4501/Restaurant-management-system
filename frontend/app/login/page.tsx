"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { ConnectivityBadge } from "@/components/ConnectivityBadge";
import { PinPad } from "@/components/PinPad";
import { api, isProblem, type Problem } from "@/lib/api/client";
import { routeForRole } from "@/lib/auth/routes";
import { initials, type DeviceMe, type EnrolResponse, type PinLoginResponse, type StaffSummary } from "@/lib/domain";
import { useDevice } from "@/lib/stores/device";
import { useStaff } from "@/lib/stores/staff";

/** A problem+json detail from the API, or `fallback` when the request never reached it (network, CORS). */
function problemMessage(err: unknown, fallback: string): string {
  if (isProblem(err)) return err.detail || err.title;
  return fallback;
}

function staffTestId(name: string): string {
  return `staff-${name.split(" ")[0]?.toLowerCase() ?? "staff"}`;
}

export default function LoginPage() {
  const router = useRouter();
  const hydrated = useDevice((s) => s.hydrated);
  const deviceToken = useDevice((s) => s.deviceToken);
  const deviceLabel = useDevice((s) => s.label);
  const allowedRoles = useDevice((s) => s.allowedRoles);
  const hydrate = useDevice((s) => s.hydrate);
  const setEnrolment = useDevice((s) => s.setEnrolment);
  const setSession = useStaff((s) => s.setSession);
  const [enrolCode, setEnrolCode] = useState("");
  const [selected, setSelected] = useState<StaffSummary | null>(null);
  const [pin, setPin] = useState("");
  const [pinError, setPinError] = useState<string | null>(null);
  const [lockout, setLockout] = useState<number | null>(null);

  useEffect(() => { hydrate(); }, [hydrate]);

  const deviceQuery = useQuery({
    queryKey: ["devices/me"],
    enabled: hydrated && Boolean(deviceToken),
    queryFn: async () => { const { data, error } = await api.GET("/api/v1/devices/me"); if (error) throw error; return data as unknown as DeviceMe; },
  });

  const enrolMutation = useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST("/api/v1/devices/enrol", { body: { enrolment_code: enrolCode.trim() } });
      if (error) throw error;
      const body = data as unknown as EnrolResponse;
      setEnrolment({ deviceToken: body.device_token, deviceId: body.device_id, label: body.label ?? null, allowedRoles: body.allowed_roles });
    },
  });

  const pinMutation = useMutation({
    mutationFn: async () => {
      if (!selected) throw new Error("Pick a staff member");
      const { data, error, response } = await api.POST("/api/v1/auth/pin", { body: { staff_id: selected.id, pin } });
      if (response.status === 423 && isProblem(error as unknown)) {
        const problem = error as unknown as Problem;
        setLockout(problem.retry_after_seconds ?? 900);
        throw new Error(problem.detail);
      }
      if (error) throw error;
      return data as unknown as PinLoginResponse;
    },
    onSuccess: (body) => {
      const staffMember = body.staff;
      setSession(body.token, staffMember);
      router.replace(routeForRole(staffMember.role));
    },
    onError: (err: unknown) => { setPinError(problemMessage(err, "Sign-in failed")); },
  });

  const staffError = deviceQuery.isError ? problemMessage(deviceQuery.error, "Could not load staff for this device.") : null;
  const waiters = useMemo(() => (deviceQuery.data?.staff ?? []).filter((s) => allowedRoles.includes(s.role)), [deviceQuery.data?.staff, allowedRoles]);

  if (!hydrated) return <main className="staff-shell staff-theme flex min-h-screen items-center justify-center"><p className="text-sm text-[var(--ink-3)]">Loading…</p></main>;

  if (!deviceToken) {
    return (
      <main className="staff-shell staff-theme flex min-h-screen flex-col items-center justify-center gap-6 px-4">
        <div className="w-full max-w-sm">
          <p className="wordmark mb-2 text-xl">RENZY</p>
          <h1 className="mb-1 text-2xl font-semibold">Enrol this device</h1>
          <p className="mb-4 text-sm text-[var(--ink-3)]">Enter the code from the manager once.</p>
          <label className="block text-sm font-medium">Enrolment code<input data-testid="enrolment-code" value={enrolCode} onChange={(e) => setEnrolCode(e.target.value)} className="mt-1 w-full min-h-14 rounded-lg border border-[var(--line)] bg-[var(--surface-2)] px-3 text-lg tracking-widest" autoComplete="off" /></label>
          <button type="button" data-testid="enrol-submit" disabled={enrolMutation.isPending || enrolCode.trim().length < 4} onClick={() => void enrolMutation.mutate()} className="mt-4 flex min-h-16 w-full items-center justify-center rounded-lg bg-[var(--accent)] text-lg font-semibold text-[var(--accent-ink)] disabled:opacity-40">{enrolMutation.isPending ? "Enrolling…" : "Continue"}</button>
          {enrolMutation.isError ? <p role="alert" data-testid="enrol-error" className="mt-3 text-sm text-[var(--danger)]">{problemMessage(enrolMutation.error, "Could not reach the server. Check the connection and try again.")}</p> : null}
        </div>
        <ConnectivityBadge />
      </main>
    );
  }

  return (
    <main className="staff-shell staff-theme flex min-h-screen flex-col px-4 py-6">
      <header className="mb-6 flex items-center justify-between"><div><p className="wordmark text-xl">RENZY</p><h1 className="text-2xl font-semibold">Who is signing in?</h1>{deviceLabel ? <p className="text-sm text-[var(--ink-3)]">{deviceLabel}</p> : null}</div><ConnectivityBadge /></header>
      {staffError ? <p role="alert" data-testid="staff-error" className="mb-4 text-sm text-[var(--danger)]">{staffError}</p> : null}
      {!selected ? (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4" data-testid="staff-grid">
          {waiters.map((member) => (
            <button key={member.id} type="button" data-testid={staffTestId(member.name)} onClick={() => { setSelected(member); setPin(""); setPinError(null); }} className="flex min-h-28 flex-col items-center justify-center gap-2 rounded-xl border border-[var(--line)] bg-[var(--surface)] p-4 active:bg-[var(--surface-3)]">
              <span className="flex h-14 w-14 items-center justify-center rounded-full bg-[var(--accent-soft)] text-lg font-semibold text-[var(--accent)]">{initials(member.name)}</span>
              <span className="text-center text-sm font-semibold">{member.name}</span>
            </button>
          ))}
        </div>
      ) : (
        <div className="mx-auto flex w-full max-w-sm flex-col items-center gap-4">
          <button type="button" className="self-start min-h-14 text-sm text-[var(--accent)]" onClick={() => setSelected(null)}>← Back</button>
          <p className="text-lg font-semibold">{selected.name}</p>
          <PinPad value={pin} onChange={setPin} onSubmit={() => void pinMutation.mutate()} disabled={pinMutation.isPending} error={pinError} lockoutSeconds={lockout} />
        </div>
      )}
    </main>
  );
}
