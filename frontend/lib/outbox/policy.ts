/**
 * Which commands may wait in the queue, and which have to be refused out loud.
 *
 * A waiter's order can queue: the kitchen is in the building, the order is additive, and the
 * Idempotency-Key makes the replay exact. Money is different. A payment recorded offline is
 * recorded against the balance *this* device last saw — and a session can gain two more rounds of
 * drinks from another tablet while this one is dark. The cashier would tell the guest "paid in
 * full" against a bill that has since grown, and the till would reconcile against a fiction.
 *
 * So the money commands, the manager-authorised commands and the auth commands are blocked while
 * offline with an honest message rather than queued. The till screen already tells the cashier to
 * write payments down and enter them when the connection is back; this makes the API agree with it.
 *
 * Guest and QR surfaces never queue at all (WS11 task §7): a guest's phone with no network simply
 * cannot order, and pretending otherwise puts a ticket nobody will cook into a stranger's pocket.
 */

export type CommandPolicy = "queue" | "online-only";

export interface CommandRule {
  policy: CommandPolicy;
  /** Shown to the user, verbatim, as the `detail` of the problem document. */
  reason: string;
  /** The `code` of the problem document, so a screen can switch on it. */
  code: string;
}

const QUEUEABLE: CommandRule = {
  policy: "queue",
  reason: "Queued on this device until the connection is back.",
  code: "queued_offline",
};

interface Blocked {
  match: RegExp;
  reason: string;
  code: string;
}

/**
 * Matched against the path only, in order. The money patterns are deliberately written around the
 * *words* rather than the exact routes, so a new `/sessions/{id}/refund` is caught the day it is
 * added instead of silently inheriting the queue.
 */
const BLOCKED: Blocked[] = [
  {
    match: /\/guest\//,
    reason: "This device has no connection, so the order cannot reach the kitchen. Please ask a member of staff.",
    code: "guest_offline",
  },
  {
    match: /\/(auth|devices)\//,
    reason: "Signing in needs a connection. Try again when the badge says online.",
    code: "auth_offline",
  },
  {
    match: /\/(payments|shifts|movements|discount|comp|price-override|void|reopen|close)(\/|$)/,
    reason:
      "No connection. This moves money, so it cannot be queued — the bill may have changed on another device. Write it down and enter it when the connection is back.",
    code: "money_offline",
  },
];

export function classifyCommand(path: string): CommandRule {
  for (const rule of BLOCKED) {
    if (rule.match.test(path)) {
      return { policy: "online-only", reason: rule.reason, code: rule.code };
    }
  }
  return QUEUEABLE;
}
