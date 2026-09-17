"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo, useState } from "react";

import { useEventStream } from "@/lib/realtime/useEventStream";

import { fetchPatterns, fetchToday, fetchVariance, ownerLogout, problemMessage } from "../lib/api";
import type { LogPreset } from "../lib/types";
import { OwnerShell } from "./OwnerShell";
import { PatternsSection } from "./PatternsSection";
import { TodayStrip, voidValueFromVariance } from "./TodayStrip";
import { VariancePanel } from "./VariancePanel";
import { ZReportSheet } from "./ZReportSheet";

interface Props {
  ownerName: string;
  onSignedOut: () => void;
}

export function OwnerDashboard({ ownerName, onSignedOut }: Props) {
  const router = useRouter();
  const search = useSearchParams();
  const queryClient = useQueryClient();
  const [zShiftId, setZShiftId] = useState<string | null>(null);

  const invalidateReports = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ["owner-today"] });
    void queryClient.invalidateQueries({ queryKey: ["owner-variance"] });
    void queryClient.invalidateQueries({ queryKey: ["owner-patterns"] });
  }, [queryClient]);

  const stream = useEventStream({
    onResync: invalidateReports,
    onEvent: () => {
      void queryClient.invalidateQueries({ queryKey: ["owner-today"] });
    },
    onSignedOut: () => {
      onSignedOut();
      router.replace("/owner");
    },
  });

  const variance = useQuery({
    queryKey: ["owner-variance"],
    queryFn: () => fetchVariance(7),
    refetchInterval: stream.state === "live" ? false : 30_000,
  });
  const today = useQuery({
    queryKey: ["owner-today"],
    queryFn: fetchToday,
    refetchInterval: stream.state === "live" ? false : 15_000,
  });
  const patterns = useQuery({
    queryKey: ["owner-patterns"],
    queryFn: () => fetchPatterns(7),
    refetchInterval: stream.state === "live" ? false : 60_000,
  });

  const currentHour = useMemo(() => {
    try {
      return Number(
        new Intl.DateTimeFormat("en-GB", {
          timeZone: "Africa/Accra",
          hour: "2-digit",
          hourCycle: "h23",
        }).formatToParts(new Date()).find((p) => p.type === "hour")?.value,
      );
    } catch {
      return null;
    }
  }, []);

  function openLog(preset: LogPreset) {
    const params = new URLSearchParams();
    params.set("preset", preset.kind);
    if (preset.kind === "discounts" && preset.actor_id) params.set("actor_id", preset.actor_id);
    if (preset.kind === "cash" && preset.shift_id) params.set("shift_id", preset.shift_id);
    router.push(`/owner/events?${params.toString()}`);
  }

  async function logout() {
    await ownerLogout();
    onSignedOut();
    router.replace("/owner");
  }

  const loading = variance.isLoading || today.isLoading;
  const presetHint = search.get("preset");

  return (
    <OwnerShell name={ownerName} title="Back office" onLogout={() => void logout()}>
      {stream.stale ? (
        <p className="mb-4 rounded-lg border border-[var(--warn)] bg-[var(--surface)] px-3 py-2 text-sm text-[var(--warn)]">
          Live feed is quiet — figures refresh on a timer until it returns.
        </p>
      ) : null}

      {loading ? (
        <p className="text-sm text-[var(--ink-3)]">Loading last night&apos;s variance…</p>
      ) : null}

      {variance.isError ? (
        <p role="alert" className="mb-4 text-sm text-[var(--danger)]">
          {problemMessage(variance.error, "Could not load variance")}
        </p>
      ) : null}

      {variance.data ? (
        <VariancePanel
          variance={variance.data}
          onOpenLog={openLog}
          onOpenZReport={(id) => setZShiftId(id)}
        />
      ) : null}

      {today.data ? (
        <TodayStrip
          today={today.data}
          voidValuePesewas={voidValueFromVariance(variance.data)}
        />
      ) : null}

      {patterns.data ? (
        <PatternsSection patterns={patterns.data} currentHour={currentHour} />
      ) : patterns.isError ? (
        <p role="alert" className="text-sm text-[var(--danger)]">
          {problemMessage(patterns.error, "Could not load patterns")}
        </p>
      ) : null}

      {presetHint ? (
        <p className="sr-only">Opened from preset {presetHint}</p>
      ) : null}

      {zShiftId ? <ZReportSheet shiftId={zShiftId} onClose={() => setZShiftId(null)} /> : null}
    </OwnerShell>
  );
}
