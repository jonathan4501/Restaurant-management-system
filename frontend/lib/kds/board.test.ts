import { describe, expect, it } from "vitest";

import type { KdsTicket, OrderItemStatus, TicketLine } from "@/lib/domain";
import {
  ackTicket,
  markAllReady,
  markLineReady,
  patchTicket,
  removeTicket,
  serverNowIso,
} from "@/lib/kds/board";

function line(itemId: string, status: OrderItemStatus = "PENDING"): TicketLine {
  return {
    item_id: itemId,
    menu_item_id: `mi-${itemId}`,
    name: "Jollof Rice",
    quantity: 1,
    modifiers: [],
    notes: "",
    prep_station: "KITCHEN",
    course: 1,
    status,
    unit_price_pesewas: 7500,
    line_total_pesewas: 7500,
  };
}

function ticket(overrides: Partial<KdsTicket> = {}): KdsTicket {
  return {
    order_id: "o-1",
    order_number: 1001,
    table_number: "7",
    status: "SUBMITTED",
    submitted_at: "2026-09-16T12:00:00Z",
    acknowledged_at: null,
    ready_at: null,
    items: [line("i-1"), line("i-2")],
    ...overrides,
  };
}

describe("accepting a ticket", () => {
  it("moves it to Preparing and starts the cooking clock", () => {
    const acked = ackTicket(ticket(), "2026-09-16T12:03:00Z");
    expect(acked.status).toBe("PREPARING");
    expect(acked.acknowledged_at).toBe("2026-09-16T12:03:00Z");
  });

  it("leaves a ticket the kitchen already took alone", () => {
    const already = ticket({ status: "PREPARING", acknowledged_at: "2026-09-16T12:01:00Z" });
    expect(ackTicket(already, "2026-09-16T12:09:00Z")).toBe(already);
  });
});

describe("marking food ready", () => {
  it("keeps the ticket cooking while a line is still open", () => {
    const cooking = ticket({ status: "PREPARING", acknowledged_at: "2026-09-16T12:01:00Z" });
    const after = markLineReady(cooking, "i-1", "2026-09-16T12:12:00Z");
    expect(after.status).toBe("PREPARING");
    expect(after.items.map((l) => l.status)).toEqual(["READY", "PENDING"]);
    expect(after.ready_at).toBeNull();
  });

  it("moves the ticket to Ready when the last line lands, like the server does", () => {
    const cooking = ticket({ status: "PREPARING", items: [line("i-1", "READY"), line("i-2")] });
    const after = markLineReady(cooking, "i-2", "2026-09-16T12:12:00Z");
    expect(after.status).toBe("READY");
    expect(after.ready_at).toBe("2026-09-16T12:12:00Z");
  });

  it("counts a voided line as finished — nobody is cooking it", () => {
    const cooking = ticket({ status: "PREPARING", items: [line("i-1", "VOIDED"), line("i-2")] });
    expect(markLineReady(cooking, "i-2", "2026-09-16T12:12:00Z").status).toBe("READY");
  });

  it("'All ready' finishes every open line at once and leaves finished ones as they were", () => {
    const cooking = ticket({ status: "PREPARING", items: [line("i-1", "VOIDED"), line("i-2")] });
    const after = markAllReady(cooking, "2026-09-16T12:15:00Z");
    expect(after.status).toBe("READY");
    expect(after.items.map((l) => l.status)).toEqual(["VOIDED", "READY"]);
  });
});

describe("the board as a whole", () => {
  it("patches one ticket and leaves the rest untouched", () => {
    const rows = [ticket(), ticket({ order_id: "o-2", order_number: 1002 })];
    const after = patchTicket(rows, "o-2", (t) => ackTicket(t, "2026-09-16T12:03:00Z"));
    expect(after[0]!.status).toBe("SUBMITTED");
    expect(after[1]!.status).toBe("PREPARING");
  });

  it("takes a served ticket off the board", () => {
    const rows = [ticket(), ticket({ order_id: "o-2" })];
    expect(removeTicket(rows, "o-1").map((t) => t.order_id)).toEqual(["o-2"]);
  });

  it("stamps optimistic timestamps with server time, not the tablet's clock", () => {
    const clientNow = Date.parse("2026-09-16T12:00:00Z");
    expect(serverNowIso(5 * 60 * 1000, clientNow)).toBe("2026-09-16T12:05:00.000Z");
  });
});
