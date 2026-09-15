"use client";

import { Suspense } from "react";
import { OrderScreen } from "@/components/OrderScreen";

export default function OrderPage() {
  return (
    <Suspense fallback={<main className="staff-shell staff-theme flex min-h-screen items-center justify-center">Loading…</main>}>
      <OrderScreen />
    </Suspense>
  );
}
