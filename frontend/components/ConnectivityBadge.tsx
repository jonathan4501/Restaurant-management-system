"use client";

import { retryFailed, discardFailed } from "@/lib/outbox/useOutbox";
import { useConnectivity } from "@/lib/stores/connectivity";

const LABELS = {
  online: "Online",
  offline: "Offline",
  pending: "Pending",
} as const;

export function ConnectivityBadge() {
  const { status, pendingCount, failedCount } = useConnectivity();

  return (
    <div
      data-testid="connectivity-badge"
      data-status={status}
      data-pending={pendingCount}
      data-failed={failedCount}
      className="inline-flex min-h-8 items-center gap-2 rounded-full border border-[var(--line)] bg-[var(--surface-2)] px-3 text-xs font-medium text-[var(--ink-2)]"
    >
      <span
        className={`h-2 w-2 rounded-full ${
          status === "online" ? "bg-[var(--accent)]" : status === "offline" ? "bg-[var(--danger)]" : "bg-[var(--warn)]"
        }`}
        aria-hidden
      />
      <span>{LABELS[status]}</span>
      {pendingCount > 0 ? <span className="num">({pendingCount})</span> : null}
      {failedCount > 0 ? (
        <span className="inline-flex items-center gap-1">
          <span className="text-[var(--danger)]">{failedCount} failed</span>
          <button
            type="button"
            data-testid="outbox-retry"
            className="underline"
            onClick={() => retryFailed()}
          >
            Retry
          </button>
          <button
            type="button"
            data-testid="outbox-discard"
            className="underline"
            onClick={() => discardFailed()}
          >
            Discard
          </button>
        </span>
      ) : null}
    </div>
  );
}
