import { describe, expect, it } from "vitest";

import type { EventEnvelope } from "@/lib/domain";
import { affectedQueries, applyOrder, SseParser, toEnvelope } from "@/lib/realtime/sse";

function envelope(seq: number, type = "ORDER_SUBMITTED", aggregate = "ORDER"): EventEnvelope {
  return {
    id: `e${seq}`,
    seq,
    type,
    aggregate_type: aggregate as EventEnvelope["aggregate_type"],
    aggregate_id: "a1",
    order_id: "o1",
    actor_role: "WAITER",
    reason_code: null,
    created_at: "2026-09-16T12:00:00Z",
    payload: {},
  };
}

describe("SSE parsing", () => {
  it("reads id, event and data, and ignores keepalives", () => {
    const parser = new SseParser();
    const messages = parser.push(
      'id: 7\nevent: ORDER_READY\ndata: {"seq":7}\n\n: keepalive\n\nid: 8\nevent: ORDER_SERVED\ndata: {"seq":8}\n\n',
    );
    expect(messages).toHaveLength(2);
    expect(messages[0]).toEqual({ id: 7, event: "ORDER_READY", data: '{"seq":7}' });
    expect(messages[1]!.id).toBe(8);
  });

  it("holds a half-delivered message until the rest of it arrives", () => {
    const parser = new SseParser();
    expect(parser.push("id: 3\nevent: ORDER_S")).toEqual([]);
    expect(parser.push('UBMITTED\ndata: {"seq":3}')).toEqual([]);
    const done = parser.push("\n\n");
    expect(done).toHaveLength(1);
    expect(done[0]!.event).toBe("ORDER_SUBMITTED");
  });

  it("survives \\r\\n and a data field with no space", () => {
    const parser = new SseParser();
    const [message] = parser.push('id:9\r\nevent:RESYNC\r\ndata:{"seq":9}\r\n\r\n');
    expect(message).toEqual({ id: 9, event: "RESYNC", data: '{"seq":9}' });
  });

  it("turns a message into an envelope, or nothing when the body is not usable", () => {
    expect(toEnvelope({ id: 4, event: "ORDER_READY", data: '{"seq":4}' })?.seq).toBe(4);
    expect(toEnvelope({ id: 4, event: "ORDER_READY", data: "not json" })).toBeNull();
    expect(toEnvelope({ id: null, event: "x", data: "{}" })).toBeNull();
  });
});

describe("dedupe by seq", () => {
  it("drops anything already applied and sorts what is left", () => {
    const fresh = applyOrder(5, [envelope(7), envelope(5), envelope(6), envelope(4)]);
    expect(fresh.map((e) => e.seq)).toEqual([6, 7]);
  });

  it("drops a duplicate inside the same batch (replay overlapping live)", () => {
    const fresh = applyOrder(0, [envelope(1), envelope(1), envelope(2)]);
    expect(fresh.map((e) => e.seq)).toEqual([1, 2]);
  });

  it("returns nothing when everything is old", () => {
    expect(applyOrder(9, [envelope(3), envelope(9)])).toEqual([]);
  });
});

describe("what to refetch", () => {
  it("maps an aggregate to the screens that care", () => {
    expect(affectedQueries(envelope(1, "ORDER_SUBMITTED", "ORDER"))).toContain("kds");
    expect(affectedQueries(envelope(2, "PAYMENT_RECORDED", "SESSION"))).toEqual(["tables", "bills"]);
    expect(affectedQueries(envelope(3, "ITEM_86ED", "MENU_ITEM"))).toEqual(["menu", "kds"]);
    expect(affectedQueries(envelope(4, "DEVICE_ENROLLED", "DEVICE"))).toEqual([]);
  });
});
