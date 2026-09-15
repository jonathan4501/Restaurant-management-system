"use client";
import { useSearchParams } from "next/navigation";
import { useMemo } from "react";
import type { OrderMode } from "@/lib/domain";
import { canAccessTables } from "@/lib/order/modifiers";
export function useOrderMode() {
  const params = useSearchParams();
  const raw = params.get("mode");
  const mode: OrderMode = raw === "guest" || raw === "qr" ? raw : "waiter";
  return useMemo(() => ({ mode, canSeeTables: canAccessTables(mode), isGuestSurface: mode === "guest" || mode === "qr", usesGuestClient: mode === "guest" || mode === "qr" }), [mode]);
}
