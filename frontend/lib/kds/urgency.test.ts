import { describe, expect, it } from "vitest";

import {
  ageSeconds,
  formatAge,
  serverOffsetMs,
  ticketClockStart,
  urgencyFor,
} from "@/lib/kds/urgency";

describe("ticket urgency", () => {
  it("turns amber at ten minutes and red at fifteen", () => {
    expect(urgencyFor(0)).toBe("fresh");
    expect(urgencyFor(599)).toBe("fresh");
    expect(urgencyFor(600)).toBe("warning");
    expect(urgencyFor(899)).toBe("warning");
    expect(urgencyFor(900)).toBe("late");
    expect(urgencyFor(3600)).toBe("late");
  });

  it("formats mm:ss, and hours once a ticket has been standing that long", () => {
    expect(formatAge(0)).toBe("00:00");
    expect(formatAge(9)).toBe("00:09");
    expect(formatAge(614)).toBe("10:14");
    expect(formatAge(3_725)).toBe("1:02:05");
  });
});

describe("server time, not the tablet's clock", () => {
  it("measures age against the server offset", () => {
    const submitted = "2026-09-16T12:00:00Z";
    const clientNow = Date.parse("2026-09-16T12:05:00Z");

    // A tablet five minutes behind the server would otherwise show 5:00 instead of 10:00.
    const offset = serverOffsetMs("Wed, 16 Sep 2026 12:10:00 GMT", clientNow);
    expect(offset).toBe(5 * 60 * 1000);
    expect(ageSeconds(submitted, clientNow, offset)).toBe(600);
    expect(urgencyFor(ageSeconds(submitted, clientNow, offset))).toBe("warning");
  });

  it("falls back to no offset when the header is missing or unparseable", () => {
    expect(serverOffsetMs(null)).toBe(0);
    expect(serverOffsetMs("not a date")).toBe(0);
  });

  it("never reports a negative age", () => {
    const now = Date.parse("2026-09-16T12:00:00Z");
    expect(ageSeconds("2026-09-16T12:00:30Z", now)).toBe(0);
    expect(ageSeconds(null, now)).toBe(0);
  });
});

describe("which clock a ticket runs on", () => {
  it("counts from sending while new, and from pick-up once cooking", () => {
    const ticket = {
      status: "SUBMITTED",
      submitted_at: "2026-09-16T12:00:00Z",
      acknowledged_at: "2026-09-16T12:02:00Z",
    };
    expect(ticketClockStart(ticket)).toBe("2026-09-16T12:00:00Z");
    expect(ticketClockStart({ ...ticket, status: "PREPARING" })).toBe("2026-09-16T12:02:00Z");
    // Acknowledged straight to ready (no separate ack) still has a clock.
    expect(
      ticketClockStart({ status: "PREPARING", submitted_at: "2026-09-16T12:00:00Z", acknowledged_at: null }),
    ).toBe("2026-09-16T12:00:00Z");
  });
});
