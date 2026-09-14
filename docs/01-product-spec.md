# 01 — Product specification

**Client:** RENZY, a restaurant in Shiashi, Accra, Ghana.
**v1 goal:** every plate of food that leaves the kitchen is attached to a ticket, and every ticket
ends in a recorded payment or an authorised void — so the owner knows what was sold, by whom, and
what happened to the money.

---

## 1. What the owner is actually buying

Not "order tracking." Restaurant owners in cash-heavy markets buy a system like this to answer one
question: **where is my money going?**

The patterns it has to make visible, roughly in order of how often they happen:

1. Server takes an order verbally, serves it, pockets the cash, never rings it up.
2. Cashier voids a bill *after* the customer paid, and keeps the cash.
3. A discount is applied after the guest paid full price; the difference walks.
4. Kitchen gives food to friends out the back.
5. A receipt is reprinted and reused to legitimise a second, unrecorded sale.

**The operating rule the system enforces, and which the owner must back up in the restaurant:**

> No food leaves the kitchen without a ticket. No ticket closes without a payment or an authorised void.

If the owner will not enforce that on the floor, the software is decoration. Say so out loud before
the build starts.

**Design consequence:** the owner's first screen leads with *variance* — voids after cooking started,
discounts, comps, reopened bills, cash-drawer difference — not with a revenue chart. Revenue is the
screen he enjoys. Variance is the screen that pays for the system.

---

## 2. Roles

| Role | Device | Auth | Can do |
|---|---|---|---|
| **Guest** | Tablet handed over, or own phone via table QR | Session token scoped to one table, short-lived | Read menu, build a draft order, submit it. Nothing else. |
| **Waiter** | Shared tablet | 4–6 digit PIN | Open/close table sessions, take orders, fire courses, mark served, request a void |
| **Kitchen** | Wall screen or tablet | PIN | Acknowledge tickets, mark items and orders ready, mark an item finished (86) |
| **Cashier** | Tablet or PC at the front | PIN | View open bills, record payment, split a bill, open/close a shift, count the drawer |
| **Manager** | Any | PIN + used to authorise others | Everything above, plus authorise voids, discounts, price overrides, reopens |
| **Owner** | Phone or laptop, anywhere | Email + password + TOTP | Read everything. Menu and staff administration. Cannot be authorised away. |

Staff use **PINs, not passwords** — devices are shared and user switching must take two seconds.
The owner gets real authentication because the owner sees the money.

---

## 3. The core loop

```
Guest / Waiter                Kitchen                 Cashier                 Owner
─────────────                 ───────                 ───────                 ─────
open table session
add items + modifiers
submit order      ──────────► ticket appears
                              acknowledge
                              cook (timer running)
                              mark ready       ──────────► bill shows "food ready"
mark served       ◄───────────┘
                                                        take payment
                                                        mark paid      ──────────► lands in reports
                                                        close bill                 + audit trail
```

Everything on that diagram writes an event. The audit trail is not a separate feature; it is the
same writes, read back.

---

## 4. Ordering

- Orders belong to a **table session**, not a person. A session accumulates several rounds — drinks,
  then starters, then mains, then one more beer — and ends in one bill.
- **Modifiers are mandatory, not a nice-to-have.** "No pepper", "extra plantain", "well done",
  "tilapia instead of chicken". Get this wrong and the kitchen abandons the display on night one.
  - Single-choice groups (pepper level, doneness) and multi-choice groups (paid extras).
  - Paid extras add to the line price; free choices do not.
- **Course firing**: drinks now, starters now, mains when the starters clear. Without it everything
  lands at once and the food is cold.
- **86'ing**: the kitchen marks an item finished in one tap; it disappears from every ordering device
  immediately. The kitchen runs out of tilapia at 20:00 and the tablets must stop selling it.
- **Changing an order after the kitchen started** is an explicit, authorised, logged flow — never a
  silent edit.

### On the handed-tablet model

The client asked for a tablet handed to the guest. Build it, but build it as one **mode** of a single
ordering app, because the handed tablet has real operational costs:

- It saves no labour — the server still walks to the table and back.
- Guests browsing a menu are slower than guests being asked "what will you have?", so table turnover drops.
- Upselling dies. A tablet does not sell the special or the second beer.
- Hygiene, breakage, theft, and charging ten tablets through a Friday service.

`qr` mode — the guest's own phone, via a QR code on the table — removes the hardware fleet entirely
and is the better default for most tables. Same codebase, same API, one flag.

---

## 5. Kitchen display

The whole reason a screen beats a paper ticket is **the timer**.

- Three columns: **New**, **Preparing**, **Ready**.
- Every ticket shows its age in `mm:ss`, counting from submit (New) or acknowledge (Preparing).
- Amber at **10 minutes**, red at **15**. A late ticket must be impossible to miss from across a kitchen.
- Items are tagged by prep station (`KITCHEN`, `GRILL`, `BAR`) so the grill cook reads only their lines.
- Modifiers render in a different colour from the item name. That is what gets read under pressure.
- A backup ticket printer exists because kitchens trust paper and screens fail.

---

## 6. Cashier and money

- Open bills listed by table with a state chip: sent / cooking / food ready / ready to pay.
- Payment is **recorded, not processed** (see `decisions/0006`). Methods: Cash, MTN MoMo,
  Telecel Cash, AirtelTigo Money, Card, Bank transfer.
- Cash: tendered amount in, change calculated and shown large.
- Mobile money: cashier keys the transaction reference; it is stored against the payment.
- **Split bills and partial payments** are required, not optional. Four friends paying separately at
  one table is the normal case, not the edge case.
- A bill stays open until fully settled. Partial payments accumulate against it.

### Shifts and the cash drawer

This is the highest-value feature in the system and it is the one clients forget to ask for.

- A cashier opens a shift with a declared **opening float**.
- Every cash payment is attached to that shift.
- At close, the cashier counts the drawer and enters the figure. The system already knows what it
  should be. The difference is the **variance**.
- The Z-report shows expected vs declared vs variance, by cashier, by shift.

Without this, the owner is not tracking anything. He is looking at a number the staff produced.

---

## 7. Totals

```
line_total  = (unit_price + paid modifiers) × quantity
order_total = Σ line_total − discounts
```

That is the entire money calculation. **No tax is computed, added, split out or displayed.**
Menu prices are what the guest pays. See `decisions/0005`.

The owner-facing figure is labelled **"Money taken"**, never "Revenue" or "Profit", because it is
gross cash through the till before tax, cost of goods, wages or rent.

---

## 8. Owner back office

In this order, top to bottom:

1. **Where money can leak** — cash variance by shift and cashier; voids after cooking started with
   value, reason and who authorised; discounts and comps; bills reopened after closing; gaps in the
   ticket number sequence.
2. **Today** — money taken, covers, average bill, open bills on the floor now.
3. **Patterns** — money taken by hour, payment method mix, best sellers by value, average
   order-to-ready time per station.
4. **Every action, in order** — the full event log, filterable by staff member, date and event type.
   Flagged rows (voids, discounts, reopens, failed PIN attempts) are visually distinct.

---

## 9. Out of scope for v1

Tax and VAT calculation · GRA E-VAT fiscal clearance · payment gateway integration · inventory and
stock · delivery and takeaway · table reservations · loyalty · native mobile apps · multi-branch
reporting · payroll.

`docs/05-operating-context-ghana.md` records what was researched about the tax environment and why it
was deliberately excluded, so the decision is not accidentally reversed by someone who reads about it
later.
