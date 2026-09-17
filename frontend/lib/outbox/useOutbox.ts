"use client";

/**
 * Joins the outbox to the shell: start the drain, and mirror its counts into the connectivity
 * store so `ConnectivityBadge` can say "pending 3" without any screen knowing how it got there.
 */

import { useEffect } from "react";

import { useConnectivity } from "@/lib/stores/connectivity";

import { outbox, startOutbox } from "./index";
import type { OutboxSnapshot } from "./types";

export function useOutbox(): void {
  const setPendingCount = useConnectivity((s) => s.setPendingCount);
  const setFailedCount = useConnectivity((s) => s.setFailedCount);

  useEffect(() => {
    const unsubscribe = outbox.subscribe((snapshot: OutboxSnapshot) => {
      setPendingCount(snapshot.queued);
      setFailedCount(snapshot.failed);
    });
    const stop = startOutbox();
    return () => {
      unsubscribe();
      stop();
    };
  }, [setPendingCount, setFailedCount]);
}

/** Put the failed commands back in the queue. Wired to the badge's "Retry". */
export function retryFailed(): void {
  void outbox.retryFailed();
}

/** Forget the failed commands. They never reached the server, so nothing is being erased. */
export function discardFailed(): void {
  void outbox.discardFailed();
}
