"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Suspense, useCallback, useState } from "react";

import { fetchOwnerMe } from "./lib/api";
import { OwnerDashboard } from "./components/OwnerDashboard";
import { OwnerLogin } from "./components/OwnerLogin";

function OwnerHome() {
  const queryClient = useQueryClient();
  const [gate, setGate] = useState(0);

  const me = useQuery({
    queryKey: ["owner-me", gate],
    queryFn: fetchOwnerMe,
    retry: false,
  });

  const onAuthenticated = useCallback(() => {
    setGate((n) => n + 1);
    void queryClient.invalidateQueries({ queryKey: ["owner-me"] });
  }, [queryClient]);

  const onSignedOut = useCallback(() => {
    queryClient.removeQueries({ queryKey: ["owner-me"] });
    setGate((n) => n + 1);
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
    <Suspense fallback={<p className="staff-shell staff-theme p-6 text-sm">Loading…</p>}>
      <OwnerDashboard ownerName={me.data.name} onSignedOut={onSignedOut} />
    </Suspense>
  );
}

export default function OwnerPage() {
  return <OwnerHome />;
}
