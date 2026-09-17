/**
 * Retry delay for a deferred command: 1s, 2s, 4s, 8s, 16s, then 30s for as long as the outage
 * lasts. No jitter — one tablet is not a thundering herd, and a deterministic curve is one a test
 * and a waiter can both predict.
 */

export const BASE_BACKOFF_MS = 1_000;
export const MAX_BACKOFF_MS = 30_000;

/** `attempts` is how many times the entry has been tried, so the first failure asks for 1s. */
export function backoffMs(attempts: number): number {
  const exponent = Math.max(0, attempts - 1);
  return Math.min(BASE_BACKOFF_MS * 2 ** exponent, MAX_BACKOFF_MS);
}
