import { describe, expect, it } from "vitest";

import { mergeEventPages, replaceEventPage } from "./cursor";
import type { EventLogRow } from "./types";

function row(seq: number, type = "ORDER_SUBMITTED"): EventLogRow {
  return {
    seq,
    type,
    aggregate_type: "ORDER",
    aggregate_id: "00000000-0000-4000-8000-000000000001",
    order_id: null,
    actor_id: null,
    actor: "Kofi",
    actor_role: "WAITER",
    authorised_by: null,
    reason_code: null,
    flagged: false,
    created_at: "2026-09-16T19:00:00Z",
    payload: {},
  };
}

describe("cursor merging", () => {
  it("appends the next page and drops duplicate seqs", () => {
    const first = [row(100), row(99), row(98)];
    const second = [row(98), row(97), row(96)];
    const merged = mergeEventPages(first, second);
    expect(merged.map((r) => r.seq)).toEqual([100, 99, 98, 97, 96]);
  });

  it("returns the incoming page unchanged when the list is empty", () => {
    expect(mergeEventPages([], [row(5), row(4)]).map((r) => r.seq)).toEqual([5, 4]);
  });

  it("replaceEventPage dedupes a fresh filter result", () => {
    expect(replaceEventPage([row(3), row(3), row(2)]).map((r) => r.seq)).toEqual([3, 2]);
  });
});
