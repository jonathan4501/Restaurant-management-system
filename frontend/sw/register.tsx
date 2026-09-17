"use client";

/**
 * Registers the Serwist service worker and surfaces an "Update available" prompt
 * instead of reloading mid-service when a new worker is waiting.
 */

import { useEffect, useState } from "react";

declare global {
  interface Window {
    serwist?: {
      register: () => Promise<ServiceWorkerRegistration | undefined>;
      addEventListener: (type: string, listener: (event: Event) => void) => void;
      messageSkipWaiting: () => void;
    };
  }
}

export function ServiceWorkerRegister() {
  const [updateReady, setUpdateReady] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!("serviceWorker" in navigator) || !window.serwist) return;

    const onWaiting = () => setUpdateReady(true);
    const onControlling = () => {
      window.location.reload();
    };

    window.serwist.addEventListener("waiting", onWaiting);
    window.serwist.addEventListener("controlling", onControlling);
    void window.serwist.register();
  }, []);

  if (!updateReady) return null;

  return (
    <div
      role="status"
      data-testid="sw-update-available"
      className="fixed bottom-4 left-1/2 z-50 flex -translate-x-1/2 items-center gap-3 rounded-lg border border-[var(--line)] bg-[var(--surface-2)] px-4 py-3 text-sm"
    >
      <span>Update available</span>
      <button
        type="button"
        data-testid="sw-update-accept"
        className="min-h-14 rounded-lg bg-[var(--accent)] px-4 font-semibold text-[var(--accent-ink)]"
        onClick={() => {
          window.serwist?.messageSkipWaiting();
          setUpdateReady(false);
        }}
      >
        Update
      </button>
      <button
        type="button"
        data-testid="sw-update-dismiss"
        className="min-h-14 rounded-lg border border-[var(--line)] px-3"
        onClick={() => setUpdateReady(false)}
      >
        Later
      </button>
    </div>
  );
}
