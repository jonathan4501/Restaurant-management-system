"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";

import { useConnectivity } from "@/lib/stores/connectivity";
import { useDevice } from "@/lib/stores/device";
import { useStaff } from "@/lib/stores/staff";

function StoreHydrator() {
  const hydrateDevice = useDevice((s) => s.hydrate);
  const hydrateStaff = useStaff((s) => s.hydrate);
  const setOnline = useConnectivity((s) => s.setOnline);

  useEffect(() => {
    hydrateDevice();
    hydrateStaff();
    const onOnline = () => setOnline(true);
    const onOffline = () => setOnline(false);
    setOnline(navigator.onLine);
    window.addEventListener("online", onOnline);
    window.addEventListener("offline", onOffline);
    return () => {
      window.removeEventListener("online", onOnline);
      window.removeEventListener("offline", onOffline);
    };
  }, [hydrateDevice, hydrateStaff, setOnline]);

  return null;
}

export function AppProviders({ children }: { children: ReactNode }) {
  const [client] = useState(() => new QueryClient({ defaultOptions: { queries: { staleTime: 30_000, retry: 1 } } }));

  return (
    <QueryClientProvider client={client}>
      <StoreHydrator />
      {children}
    </QueryClientProvider>
  );
}
