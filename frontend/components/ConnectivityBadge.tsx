"use client";

import { useConnectivity } from "@/lib/stores/connectivity";

const LABELS = {
  online: "Online",
  offline: "Offline",
  pending: "Pending",
} as const;

export function ConnectivityBadge() {
  const { status, pendingCount } = useConnectivity();

  return (
    <div
      data-testid="connectivity-badge"
      data-status={status}
      className="inline-flex min-h-8 items-center gap-2 rounded-full border border-[var(--line)] bg-[var(--surface-2)] px-3 text-xs font-medium text-[var(--ink-2)]"
    >
      <span
        className={`h-2 w-2 rounded-full ${
          status === "online" ? "bg-[var(--accent)]" : status === "offline" ? "bg-[var(--danger)]" : "bg-[var(--warn)]"
        }`}
        aria-hidden
      />
      <span>{LABELS[status]}</span>
      {status === "pending" && pendingCount > 0 ? <span className="num">({pendingCount})</span> : null}
    </div>
  );
}
