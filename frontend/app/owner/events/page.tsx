"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useMemo } from "react";

import { fetchOwnerMe, ownerLogout } from "../lib/api";
import type { LogPreset } from "../lib/types";
import { EventLogPanel } from "../components/EventLogPanel";
import { OwnerLogin } from "../components/OwnerLogin";
import { OwnerShell } from "../components/OwnerShell";

function EventsInner() {
  const router = useRouter();
  const search = useSearchParams();
  const queryClient = useQueryClient();

  const me = useQuery({
    queryKey: ["owner-me"],
    queryFn: fetchOwnerMe,
    retry: false,
  });

  const preset = useMemo<LogPreset | null>(() => {
    const kind = search.get("preset");
    if (kind === "voids") return { kind: "voids" };
    if (kind === "discounts") return { kind: "discounts", actor_id: search.get("actor_id") ?? undefined };
    if (kind === "reopens") return { kind: "reopens" };
    if (kind === "cash") return { kind: "cash", shift_id: search.get("shift_id") ?? undefined };
    if (kind === "gaps") return { kind: "gaps" };
    return null;
  }, [search]);

  const onAuthenticated = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ["owner-me"] });
  }, [queryClient]);

  if (me.isLoading) {
    return (
      <main className="staff-shell staff-theme flex min-h-screen items-center justify-center">
        <p className="text-sm text-[var(--ink-3)]">Checking owner session…</p>
      </main>
    );
  }

  if (me.isError || !me.data) {
    return <OwnerLogin onAuthenticated={onAuthenticated} />;
  }

  return (
    <OwnerShell
      name={me.data.name}
      title="Event log"
      onLogout={() => {
        void ownerLogout().then(() => {
          queryClient.removeQueries({ queryKey: ["owner-me"] });
          router.replace("/owner");
        });
      }}
    >
      <EventLogPanel initialPreset={preset} />
    </OwnerShell>
  );
}

export default function OwnerEventsPage() {
  return (
    <Suspense
      fallback={
        <main className="staff-shell staff-theme p-6 text-sm text-[var(--ink-3)]">Loading log…</main>
      }
    >
      <EventsInner />
    </Suspense>
  );
}
