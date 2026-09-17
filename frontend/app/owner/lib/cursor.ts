import type { EventLogRow } from "./types";

/**
 * Merge a newly fetched page into the list already on screen.
 * Pages arrive newest-first; we append older rows and drop duplicates by seq.
 */
export function mergeEventPages(
  existing: EventLogRow[],
  incoming: EventLogRow[],
): EventLogRow[] {
  if (incoming.length === 0) return existing;
  if (existing.length === 0) return dedupeBySeq(incoming);

  const seen = new Set(existing.map((r) => r.seq));
  const appended: EventLogRow[] = [];
  for (const row of incoming) {
    if (seen.has(row.seq)) continue;
    seen.add(row.seq);
    appended.push(row);
  }
  return existing.concat(appended);
}

/** Replace the list (new filter / refresh) while keeping seq uniqueness. */
export function replaceEventPage(incoming: EventLogRow[]): EventLogRow[] {
  return dedupeBySeq(incoming);
}

function dedupeBySeq(rows: EventLogRow[]): EventLogRow[] {
  const seen = new Set<number>();
  const out: EventLogRow[] = [];
  for (const row of rows) {
    if (seen.has(row.seq)) continue;
    seen.add(row.seq);
    out.push(row);
  }
  return out;
}
