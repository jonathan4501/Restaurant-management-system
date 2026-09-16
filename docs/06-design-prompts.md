# RENZY — design prompt pack

Prompts for generating the UI, screen by screen. Tool-agnostic: works with v0, Lovable, Bolt,
Figma AI, Uizard, or a chat model producing HTML.

**How to use it**

1. Paste **Prompt 0 — the design system** first, on its own. Let the tool acknowledge it.
2. Then paste screen prompts **one at a time**, in the order you need them. Never batch them —
   tools average across batched requests and every screen comes out looking the same.
3. If the tool loses the system between screens, re-paste the "Quick reference" block at the end
   of Prompt 0 above each screen prompt.
4. Reject the first output against the checklist in §Rejecting bad output. First attempts are
   almost always generic; the second attempt after specific rejection is usually good.

---

## Read this before you start

**"Premium and attractive" across all four screens is a trap.** A guest holding a tablet and a
line cook at a hot grill want opposite things. Make the kitchen display beautiful and the kitchen
will hate it — thin type, low-contrast greys, generous whitespace and soft shadows are unreadable
at two metres through steam, under glare, with sixty seconds of attention to spare.

So the design system below is **one brand with two expressions**:

| | Guest screens | Staff screens |
|---|---|---|
| Ground | Light, paper-like | Dark, near-black |
| Mood | Editorial, hospitable, photo-led | Industrial, dense, instrument-like |
| Type | Serif display + generous sizing | Grotesque + mono, larger body |
| Touch targets | 48px minimum | **56px minimum, 64px for primary** |
| Motion | Light, welcoming | **Almost none.** Only the ticket timer moves. |
| Radius | 12px — softer | 8px — tighter |
| Depth | Soft shadows | Borders and fills only, no shadows |

That split *is* the premium signal. A system that knows the difference between a guest and a
cook reads as considered. One that paints everything the same reads as a template.

---

# PROMPT 0 — The design system

> Paste this first, on its own.

```
You are designing the UI for RENZY, a restaurant in Shiashi, Accra, Ghana. The product is an
order and sales system used on four devices: a tablet handed to the guest, a kitchen display
screen, a cashier terminal, and the owner's back office.

I will give you one screen at a time. First, adopt this design system and apply it to every
screen without restating it back to me.

## THE CORE IDEA

One brand, two expressions.

GUEST screens are light, editorial and hospitable — this is the restaurant's face. Food
photography leads. Generous space. A guest should want to look at it.

STAFF screens (kitchen, cashier, owner) are dark, dense and instrument-like — these are tools
used for ten hours straight in heat, glare and noise. Legibility and target size beat beauty
every single time. They should look like professional equipment, not like a consumer app.

Both share the same palette, typefaces and spacing scale, so they are visibly the same product.

## PALETTE

Light mode (guest screens):
  ground          #F2F4F0   page background — a cool paper white with a faint green cast, NOT cream
  surface         #FFFFFF   cards, sheets
  surface-sunken  #E8EDE8   wells, inactive areas
  line            #DCE2DD   hairlines and borders
  ink             #12191A   primary text
  ink-2           #47565A   secondary text
  ink-3           #78888C   tertiary text, captions
  green           #0E5C4A   primary accent — buttons, active states, confirmations
  green-soft      #D6EAE3   accent fills and chips
  brass           #8A6520   prices, emphasis, the wordmark
  brass-soft      #F2E6CE   brass fills

Dark mode (staff screens):
  ground          #0D1412
  surface         #141D1B
  surface-2       #1D2825
  surface-3       #27332F
  line            #2E3B37
  ink             #E9F0ED
  ink-2           #A8BAB5
  ink-3           #768883
  green           #3FBF9E   primary accent, lifted for dark grounds
  green-soft      #123028
  brass           #D4A44A
  brass-soft      #33280F

State colours (separate from the accent — never reuse them as decoration):
  queued   light #4A72A8 / dark #8FB4DC     an order sent, not yet picked up
  cooking  light #A8650C / dark #E0A356     in progress
  ready    the green accent
  late     light #A8241D / dark #EE8B84     overdue, voided, or a cash shortfall

## TYPOGRAPHY

Three roles, all Google Fonts:

  Instrument Serif  — the RENZY wordmark, and guest-screen section headings and dish names.
                      High contrast, editorial. Use it sparingly and never below 18px.
  Archivo           — all interface text, both modes. Weights 400/500/600/700.
                      Do NOT substitute Inter or Space Grotesk.
  IBM Plex Mono     — every number that matters: prices, totals, ticket timers, table numbers,
                      order numbers, receipts, quantities. Always with tabular figures.

Scales:
  Guest  12 / 14 / 16 / 20 / 28 / 40
  Staff  13 / 15 / 18 / 24 / 32 / 44   (staff screens run one step larger than a consumer app)

Uppercase labels get 0.1em letter-spacing and weight 700 at 10–11px. Headings get
text-wrap: balance. Body copy never exceeds 65 characters per line.

## LAYOUT AND COMPONENTS

Spacing scale: 4, 8, 12, 16, 24, 32, 48, 64. Nothing off the scale.
Radius: 12px on guest screens, 8px on staff screens. Pills (999px) only for filter chips.
Depth: guest screens use one soft shadow. Staff screens use NO shadows — borders and fills only,
because shadows turn to mush on a dark screen under kitchen glare.

Touch targets: 48px minimum on guest screens. 56px minimum on staff screens, 64px for the
primary action on a screen. Staff hands are wet, greasy and moving.

Not everything is a card. Use border, fill, radius and shadow by role — lift the one element
that needs attention rather than stamping the same treatment on every block.

## HARD UX RULES — these are not style preferences

1. No hover-only interactions anywhere. Every device is a touchscreen.
2. No hamburger menus, no nested navigation, no settings buried two levels deep on staff
   screens. A new waiter must be productive in ten minutes with no training manual.
3. Staff screens have no decorative animation. The only thing that moves is a ticket age timer.
4. State is shown by shape AND colour — a chip, a stripe, a position — never colour alone.
5. Destructive and money-moving actions (void, discount, price override, reopening a closed
   bill) are visually separated from ordinary actions and require an explicit confirmation.
6. Connection state is always visible on staff screens, never implied. When a device is offline
   and queueing, it says so plainly. Never show an order as delivered to the kitchen when it is
   still sitting in a local queue.
7. Currency is Ghana cedis, formatted "GH₵ 75.00", always in IBM Plex Mono, right-aligned in
   any column of numbers.
8. Every screen opens in a realistic working state with real content — never an empty shell,
   never lorem ipsum, never "Item 1 / Item 2".

## DO NOT

- Do not use cream (#F4F1EA) grounds, terracotta accents, or purple-to-blue gradient heroes.
- Do not use emoji as icons or section markers.
- Do not centre everything. Left-align text; centre only what is genuinely symmetrical.
- Do not put a rounded card with a coloured left rail around every block.
- Do not add a full-viewport hero to any screen. These are working tools.
- Do not show tax, VAT or levy lines anywhere. The menu price is what the guest pays and the
  total is the sum of the lines. There is no tax in this product.

## CONTENT TO USE

Real menu, real prices — use these, not placeholders:

  Mains    Jollof Rice with Grilled Chicken GH₵ 75 · Waakye Special GH₵ 60 ·
           Banku with Grilled Tilapia GH₵ 120 · Fufu with Light Soup (Goat) GH₵ 90 ·
           Fried Rice with Chicken GH₵ 85 · Red Red with Plantain GH₵ 55 ·
           Omo Tuo with Groundnut Soup GH₵ 80 · Yam Chips with Chicken GH₵ 70
  Grill    Whole Grilled Tilapia GH₵ 130 · Chicken Wings 6pc GH₵ 70 ·
           Khebab Platter GH₵ 80 · Grilled Guinea Fowl GH₵ 150
  Sides    Kelewele GH₵ 25 · Fried Plantain GH₵ 20 · Side of Jollof GH₵ 35 · Extra Shito GH₵ 10
  Drinks   Club Beer GH₵ 25 · Star Beer GH₵ 25 · Guinness Smooth GH₵ 30 ·
           Malta Guinness GH₵ 20 · Alvaro GH₵ 22 · Sobolo GH₵ 15 ·
           Bottled Water GH₵ 8 · Coconut Juice GH₵ 20

  Modifiers  Pepper level (No pepper / Mild / Hot / Extra hot) · Doneness (Medium / Well done) ·
             Extras (Extra plantain +GH₵ 8 · Extra shito +GH₵ 5 · Extra soup +GH₵ 10)

  Staff      Kofi and Efua (waiters) · Yaw (kitchen) · Ama Mensah (cashier and manager)
  Tables     1 to 16
  Time       A Monday evening, around 19:40

Acknowledge with one sentence, then wait. I will send the first screen next.
```

### Quick reference — re-paste this above a screen prompt if the tool forgets

```
RENZY design system: guest screens LIGHT (#F2F4F0 ground, #FFFFFF surface, #12191A ink,
#0E5C4A green, #8A6520 brass, 12px radius, soft shadow, 48px targets, editorial and hospitable).
Staff screens DARK (#0D1412 ground, #141D1B surface, #E9F0ED ink, #3FBF9E green, #D4A44A brass,
8px radius, NO shadows, 56px targets / 64px primary, dense and instrument-like).
Type: Instrument Serif (wordmark + guest headings), Archivo (all UI), IBM Plex Mono (all numbers,
tabular). States: queued #8FB4DC, cooking #E0A356, ready = green, late #EE8B84.
No hover-only interactions. No tax lines anywhere. Real menu content, never placeholders.
```

---

# GUEST SCREENS — light, editorial, photo-led

## Prompt 1 — Table welcome

```
Screen: the guest tablet at the moment the server hands it over. Table 7.

LIGHT expression. This is the restaurant's face and the only screen where beauty outranks density.

Layout: a calm full-screen welcome. The RENZY wordmark in Instrument Serif, large. Below it
"Table 7" set in IBM Plex Mono at a size that reads as confident, not shouted. A line of warm
copy: "Efua is looking after you this evening." One primary button, wide and green:
"See the menu". A quiet secondary link: "Call Efua".

Include a single full-bleed food photograph as the upper two thirds — grilled tilapia on a
charcoal grill, warm and close. The type sits on a light panel below it, not over it.

Bottom edge, small and muted: "Prices include everything. Nothing is added at the till."

No tax breakdown. No login. No navigation chrome. The guest does nothing but tap through.
```

## Prompt 2 — Menu browse

```
Screen: the guest browsing the menu. The main ordering screen.

LIGHT expression. Two columns: menu on the left, running order on the right.

LEFT — the menu:
  A horizontal row of category chips: Mains · Grill · Sides · Drinks. Active chip filled green.
  Below, a grid of dish cards, 2 or 3 across depending on width.

  Each dish card: a square food photo at the top, the dish name in Instrument Serif at 20px,
  one line of description in Archivo at 13px in ink-3, and the price in IBM Plex Mono in brass,
  bottom-left. Tapping anywhere on the card adds it or opens its options.

  Show one card in a SOLD OUT state: photo desaturated, price struck through, a small chip
  reading "Finished for today", card not tappable. Use Grilled Guinea Fowl for this.

RIGHT — the order panel, sticky:
  Header: "Table 7" in Instrument Serif, and an item count.
  Lines: dish name, chosen modifiers below it in small italic ink-3, price right-aligned in mono,
  and a quantity stepper with − and + in 48px round targets.
  Footer: item count and subtotal, then TOTAL in large mono. Then one wide green button,
  56px tall: "Send to kitchen".
  Under the button, small muted text: "Menu prices are what you pay. Nothing is added at the till."

Populate it: Banku with Grilled Tilapia ×1 (Hot), Club Beer ×2, Kelewele ×1. Total GH₵ 195.00.

NO tax lines. NO subtotal-plus-VAT breakdown. Subtotal and total only.
```

## Prompt 3 — Dish options sheet

```
Screen: the modifier sheet, opened by tapping a dish on the guest menu.

LIGHT expression. A centred modal sheet over a dimmed menu, max 480px wide, 12px radius,
soft shadow.

Header: the dish photo as a wide banner, then "Banku with Grilled Tilapia" in Instrument Serif
and "GH₵ 120.00" in mono brass.

Body, three option groups, each with a small uppercase label:
  PEPPER LEVEL — single choice, radio rows: No pepper / Mild (selected) / Hot / Extra hot
  HOW WELL DONE — single choice: Medium (selected) / Well done
  ADD EXTRAS — multi choice with prices right-aligned in mono:
    Extra plantain +GH₵ 8 · Extra shito +GH₵ 5 · Extra soup +GH₵ 10
  QUANTITY — a stepper, 48px targets

Each option row is a full-width tappable row with a 12px radius border, at least 48px tall,
with the control on the left and the price on the right. Selected rows get a green border and
a soft green fill. Not a bare list of radio buttons.

Footer: two buttons side by side — "Cancel" (secondary, 1 unit wide) and
"Add · GH₵ 128.00" (green, 2 units wide). The button carries the live total.
```

## Prompt 4 — Order sent / live status

```
Screen: what the guest sees after tapping "Send to kitchen".

LIGHT expression. This screen's job is to remove anxiety, so it must feel calm and certain.

A confirmation state: a green check, "Your order is with the kitchen", and beneath it
"Order #1049 · Table 7" in mono.

Then a simple three-step progress strip, horizontal, showing where the order is:
  Sent (done, green) → Cooking (active, amber, pulsing gently) → Ready
Each step labelled, with the active one visually dominant. NOT a spinner, NOT a percentage bar.

Below that, the order itself listed plainly — items, modifiers, quantities, prices in mono,
and the total. Read-only.

Two actions at the bottom: "Add more to this order" (green, primary, 56px) and
"Call Efua" (secondary, outlined).

A quiet line at the very bottom: "Your bill stays open until you are ready to pay."

This is the ONE guest screen where a gentle animation is allowed — the cooking step may pulse.
Nothing else moves.
```

---

# STAFF SCREENS — dark, dense, instrument-like

## Prompt 5 — PIN login and staff switch

```
Screen: a shared staff tablet at the start of a shift.

DARK expression. Dense, fast, no decoration.

Centre panel, max 420px: the RENZY wordmark small at the top in brass. Below it a row of staff
avatars or initials chips — Kofi, Efua, Yaw, Ama — each a 64px tappable target with the name
underneath and a small uppercase role label (WAITER, WAITER, KITCHEN, MANAGER).

Selecting one reveals a numeric keypad: digits 0–9 in a 3×4 grid, every key at least 72px
square, mono type at 24px. Four PIN dots above it. A backspace key.

Show an error state variant: "PIN not recognised — 2 attempts left" in the late colour, with
small muted text below: "Attempts are logged against this device."

Top-right corner of the screen, always visible: a connection indicator — a small dot and the
word "Online" in ink-3, plus the device label "Tablet 3".

No email field. No password field. No "forgot password". Staff use PINs on shared devices and
switching users must take under two seconds.
```

## Prompt 6 — Floor view (waiter)

```
Screen: the waiter's table map — the home screen of the waiter app.

DARK expression. Information-dense, scannable in one glance from across a room.

A grid of table cards, 4–5 across, tables 1 to 16. Each card shows:
  - Table number, large, IBM Plex Mono, 32px
  - A state chip: Free / Seated / Ordered / Food ready / Awaiting payment
  - When occupied: party size, how long they have been seated in mono (e.g. "42m"),
    and the running bill total in mono
  - A 4px left stripe carrying the state colour

State colours: Free = surface-2 with ink-3 text · Seated = ink-2 · Ordered = queued blue ·
Food ready = green · Awaiting payment = brass.

Sort so that tables needing attention are visually loudest — a "Food ready" card should catch
the eye from four metres.

Top bar: the waiter's name and role chip ("Efua · Waiter"), a shift timer in mono, the
connection indicator, and a "Switch user" button.

Include ONE card in an offline-pending state: a small "2 pending" badge in brass with a
queue icon, and a tooltip-style caption "Waiting to sync". This must be honest and visible,
never hidden.

No hamburger menu. Everything a waiter needs is on this screen or one tap from it.
```

## Prompt 7 — Kitchen display (the most important screen)

```
Screen: the kitchen order display, running full-screen on a 24-inch monitor mounted on a wall,
read from 2 to 3 metres away by a cook who has sixty seconds of attention.

DARK expression, pushed to its extreme. Maximum contrast. Nothing decorative. This screen must
be legible through steam, under fluorescent glare, at a glance.

Three columns, equal width, full height: NEW · PREPARING · READY.
Each column header: the label in 13px uppercase 700 with 0.1em tracking, a count in mono, and
a 2px underline in the column's state colour (queued blue / cooking amber / green).

Ticket cards, stacked oldest first, each with a 5px left stripe in its column colour:
  - Top row: order number and submitted time in small mono ink-3 on the left;
    the TABLE NUMBER in Instrument Serif at 28px directly below it;
    on the right, the AGE TIMER in IBM Plex Mono at 32px, weight 600.
  - Item lines: quantity in mono brass at 18px, then the item name in Archivo 600 at 17px.
    Modifiers on their own line beneath, in the cooking amber, italic, 14px —
    modifiers must be a different colour from the item name, this is what gets read under pressure.
  - Each item carries a small station tag on the right: KITCHEN / GRILL / BAR.
  - Bottom: one full-width button, 64px tall, labelled for the column —
    "Start cooking" / "Mark ready" / "Picked up".

The age timer is the whole point of this screen:
  under 10 minutes — ink-2
  10 to 15 minutes — cooking amber
  over 15 minutes — late red, AND the whole card gets a 1px red ring and its left stripe turns red.
Show at least one overdue ticket so the escalation is visible.

Above the columns, a thin strip: "FINISHED TODAY" as an uppercase label followed by chips for
86'd items (Grilled Guinea Fowl), and on the right a button "Mark an item finished".
Right edge: connection indicator.

NO shadows. NO rounded-card softness. NO animation except the timers counting. This is
equipment, not an app.
```

## Prompt 8 — Cashier: open bills and payment

```
Screen: the cashier terminal taking payment.

DARK expression. Dense and fast — the cashier does this fifty times a night.

Left column, 300px: a list of open bills, one card per table. Each shows table number (bold),
the total in mono right-aligned, order number and item count in small ink-3, and a state chip:
Sent / Cooking / Food ready / Ready to pay. The selected bill has a green border and soft green fill.

Right panel, the selected bill — Table 5, Order #1045:
  Header: table and order number, item count, time opened, and the state chip.

  Split into two columns:

  LEFT — take payment:
    A small uppercase label "TAKE PAYMENT", then a grid of method buttons, each 64px tall,
    showing the method name in 600 and a small caption beneath:
      Cash (Notes & coins) · MTN MoMo (Reference required) ·
      Telecel Cash (Reference required) · Card (Visa / Mastercard)
    Selected method gets a green border and fill.

    With Cash selected: a large mono input "Cash received", a row of quick-amount chips
    (50 · 100 · 200 · 500 · Exact), then a CHANGE DUE panel — green-soft fill, green border,
    the amount in mono at 24px. Change must be the largest number on this half of the screen;
    a tired cashier reads it at a glance.

    Then the primary action, 64px, full width, green: "Mark paid · GH₵ 320.00".
    Below it, clearly separated by space and a divider, a quiet destructive button in the late
    colour with an outline, not a fill: "Void this order". Under it, small ink-3 text:
    "Voiding after the kitchen has started needs a manager PIN and a reason."

  RIGHT — the bill preview:
    Styled like an actual thermal receipt: IBM Plex Mono throughout, ~11px, dashed rules,
    RENZY in Instrument Serif centred at the top, address beneath.
    Then item lines — quantity, name, price right-aligned — with modifiers indented in ink-3.
    A dashed rule, then TOTAL DUE in bold.
    NO tax lines. NO VAT. NO QR code. Items, total, that is all.

Top of screen: "Shift 2 · Ama Mensah · opened 17:00 · float GH₵ 200.00" and the connection
indicator.
```

## Prompt 9 — Split bill

```
Screen: splitting one table's bill between several payers. Cashier terminal.

DARK expression.

Header: "Table 9 · Order #1047 · GH₵ 205.00" and a segmented control offering three modes:
"Split evenly" · "Split by item" · "Custom amounts". Show SPLIT BY ITEM as the active mode.

Main area, two panels:
  LEFT — the unassigned items, each a row with quantity, name, price in mono, and a set of
  small round payer chips (1, 2, 3) to assign it to. Assigned items dim and move out.
  RIGHT — a column per payer, up to four. Each column: "Payer 1", the items assigned to them,
  their running total in mono at 24px, a payment-method selector, and a "Take payment" button
  (56px). Once paid, the column collapses to a green "Paid — Cash · GH₵ 68.00" summary.

A persistent bar at the bottom: "GH₵ 137.00 of GH₵ 205.00 settled · GH₵ 68.00 outstanding",
with a slim progress bar in green. The bill cannot close until this reads fully settled —
make that state visually obvious.

No tax lines anywhere.
```

## Prompt 10 — Manager authorisation

```
Screen: the manager PIN dialog, shown when someone tries to void an order the kitchen has
already started, apply a discount, override a price, or reopen a closed bill.

DARK expression. A modal over a dimmed screen, max 440px, 8px radius.

This dialog must feel like friction. It is a control, not a formality. Do not make it pretty
or quick to dismiss.

Header: "Manager authorisation" in 18px 600. Below it, in ink-2:
"Order #1046 is already with the kitchen. Voiding it needs a manager PIN and a reason."
Then the value at risk, in mono, late colour, prominent: "GH₵ 266.00".

Body:
  A PIN field (masked, mono) with a numeric keypad, 72px keys.
  A REASON group — required, single choice, full-width rows with borders:
    Guest changed mind · Wrong table · Kitchen error · Item finished
  Small ink-3 note: "Your name and the reason appear on the owner's report."

Footer: "Cancel" (secondary) and "Void order" (outlined in the late colour — outlined, never a
solid red fill; a solid red button invites an accidental confident tap). The Void button is
disabled until both a PIN and a reason are present.
```

## Prompt 11 — Shift close and drawer count

```
Screen: the cashier closing their shift and counting the drawer. Cashier terminal.

DARK expression. This is the single most valuable screen in the product — it is where cash
theft becomes visible — so it must be unambiguous and slightly formal.

Header: "Closing Shift 2 · Ama Mensah · 17:00 to 23:14".

Section 1 — WHAT THE SYSTEM EXPECTS. A clean table, all figures in mono, right-aligned:
  Opening float          GH₵ 200.00
  Cash payments taken    GH₵ 2,263.00
  Payouts                GH₵   0.00
  ────────────────────────────────
  Expected in drawer     GH₵ 2,463.00    (bold, larger)

Section 2 — WHAT YOU COUNTED. A denomination counter: rows for GH₵ 200, 100, 50, 20, 10, 5, 2, 1
and coins, each with a quantity stepper and a computed line value in mono. A running counted
total updates at the bottom.

Section 3 — THE DIFFERENCE. One panel, and its treatment changes with the result:
  balanced → green border, green-soft fill, "Balanced"
  short or over → late colour border and fill, the variance in mono at 32px, e.g. "−GH₵ 45.00",
  and a required free-text explanation field beneath.
Show the SHORT state, since that is the one that matters.

Footer: "Close shift and print Z-report" (green, 64px) — disabled until the count is complete
and, if there is a variance, until an explanation has been entered.

Small ink-3 line at the bottom: "This report goes to the owner. It cannot be edited afterwards."
```

---

# OWNER SCREENS — dark, dashboard

## Prompt 12 — Back office overview

```
Screen: the owner's dashboard, opened on a phone or a laptop. Design for laptop; it must stack
cleanly to one column at 400px.

DARK expression.

Critically: this screen leads with WHERE MONEY LEAKS, not with revenue. The owner bought this
system to find theft. Revenue is the screen he enjoys; variance is the screen that pays for it.
Do not reorder these sections.

SECTION 1 — "Where money can leak" (first, above everything):
  Four tiles in one row, sharing a hairline grid rather than floating as separate cards.
  Tiles whose value is a problem get a late-coloured fill and their number in the late colour.
    Cash variance · Shift 2      −GH₵ 45.00    Ama Mensah · counted 2,418 vs 2,463 expected
    Voids after cooking started  2             GH₵ 195.00 · both authorised by Ama
    Discounts & comps            GH₵ 84.00     3 bills · staff meals
    Bills reopened after closing 1             #1039 · "add drinks" · 19:28
  Each tile carries a small 8px square severity marker before its label.
  Section caption, right-aligned in ink-3: "Everything here needed a manager PIN and left a name."

SECTION 2 — "Today so far": five stat tiles.
    Money taken  GH₵ 5,790.00   (caption: cash + mobile money + card)
    Covers       47
    Average bill GH₵ 123.19     (caption: vs GH₵ 118.40 last Monday)
    Lost to voids GH₵ 195.00    (caption: food cooked, never paid for)
    Open bills   5
  Section caption: "Money taken is gross cash through the till — before tax, food cost, wages
  and rent."
  IMPORTANT: the label is "Money taken". Never "Revenue", never "Profit", never "Sales". Keep it.

SECTION 3 — two panels side by side:
  LEFT, wider: "Money taken by hour" — a single-series vertical bar chart, hours 12:00 to 19:00.
  Bars in the green accent with 4px rounded tops anchored to the baseline. Three faint horizontal
  gridlines with mono axis labels. The peak bar direct-labelled with its value; no label on every
  bar. The final bar at 42% opacity with a caption "hour still in progress".
  No legend — a single series needs none, the title names it.
  RIGHT: "How people paid" — a labelled horizontal bar list, not a pie chart. Rows:
  Cash GH₵ 2,373.90 · MTN MoMo GH₵ 2,200.20 · Telecel Cash GH₵ 694.80 · Card GH₵ 521.10.
  Each row: label left, value right in mono, a slim 7px track beneath with a green fill.
  All bars the same green — the row label carries identity, so colour does not need to.

SECTION 4 — "Best sellers": the same labelled-bar-list pattern, by value.
  Banku with Grilled Tilapia 14 sold GH₵ 1,680 · Jollof Rice with Grilled Chicken 22 sold
  GH₵ 1,650 · Club Beer 38 sold GH₵ 950 · Waakye Special 12 sold GH₵ 720.

Never a dual-axis chart. Never a pie chart. Never a 3D effect. Chart text takes its colour from
the theme's ink tokens, never from a series colour.
```

## Prompt 13 — Audit log

```
Screen: the owner's full activity log. Every action by every person, in order.

DARK expression. This is a dense data view — treat it like a well-designed log reader,
not like a social feed.

Header: "Every action, in order" with the caption "Append-only. Nothing here can be edited or
deleted." On the right, filter controls in a single row: a date range, a staff-member select,
and an event-type select. Filters live in one row above the table, never in a sidebar drawer.

The log itself: rows, not cards. Each row is a three-column grid:
  time (mono, 11px, ink-3, fixed 64px) | actor (10px uppercase 700, ink-3, fixed 96px) |
  description (ink-2, with the event type in bold ink)

Example rows to include:
  19:41  KITCHEN · YAW    ORDER_READY — #1048 ready · 17m 20s
  19:39  WAITER · KOFI    ORDER_SUBMITTED — #1047 · Table 9 · GH₵ 205.00
  19:32  KITCHEN · YAW    KITCHEN_ACKNOWLEDGED — #1046 picked up
  19:28  MANAGER · AMA    ORDER_REOPENED — #1039 reopened after close · "add drinks"
  19:23  WAITER · KOFI    ORDER_SUBMITTED — #1048 · Table 12 · GH₵ 220.00
  19:21  MANAGER · AMA    ORDER_VOIDED — #1042 voided after cooking · "wrong table" · auth Ama
  19:14  CASHIER · AMA    PAYMENT_RECORDED — #1041 · MTN MoMo · GH₵ 118.80

Rows that matter — voids, discounts, reopens, failed PIN attempts — get a late-coloured row
fill and their event type in the late colour. They must be findable by scrolling fast without
reading.

At 400px width the row collapses to two lines: time on the first, actor and description stacked
on the second.
```

## Prompt 14 — Menu management

```
Screen: the owner editing the menu. Back office.

DARK expression. A working admin screen — clear, not flashy.

Left rail, 220px: the category list (Mains · Grill · Sides · Drinks) with item counts in mono,
drag handles for reordering, and an "Add category" action at the bottom.

Main area: the items in the selected category as a table, one row per dish:
  a 48px square thumbnail | name and description stacked | price in mono, editable inline |
  prep station as a select (Kitchen / Grill / Bar) | an availability toggle | a row menu.

The availability toggle is the important control — it is how an item gets 86'd — so make it a
real switch with a visible on/off state and a label, not an ambiguous icon. An unavailable row
dims and shows a "Finished today" chip.

Above the table: a search field, a "Add dish" primary button (green), and a small ink-3 note:
"Price changes apply to new orders only. Bills already open keep the price they were rung at."

Show an inline price-edit state: the price cell as a focused mono input with a save and cancel
affordance, and a warning chip beside it reading "Changing a price during service needs a
manager PIN."
```

## Prompt 15 — Staff and devices

```
Screen: the owner managing who can use the system and on what. Back office.

DARK expression. Two stacked sections.

SECTION 1 — Staff. A table: name | role chip (Waiter / Kitchen / Cashier / Manager) |
last active in mono | an active/inactive toggle | a "Reset PIN" action.
Rows: Kofi (Waiter), Efua (Waiter), Yaw (Kitchen), Ama Mensah (Manager).
A primary "Add staff" button. Note beneath: "Staff are never deleted, only deactivated —
their history stays in the log."

SECTION 2 — Devices. A card grid: device label (Tablet 1, Tablet 3, Kitchen screen, Cashier PC,
Table 7 QR), the roles it is allowed to use, last seen in mono, and a connection state dot.
Each card has a "Revoke" action in the late colour, outlined.
Show one device in a REVOKED state — dimmed, with a "Revoked 12 Sep" chip — and one OFFLINE,
with "Last seen 4h ago" in the late colour.

Note beneath: "A device that is not enrolled cannot send orders. Revoke immediately if a tablet
goes missing."
```

---

# Rejecting bad output

Run the first attempt against this. If any of it is true, reject specifically — quote the line
and say what to do instead. Vague feedback ("make it more premium") produces vague fixes.

- [ ] It used Inter or Space Grotesk instead of Archivo.
- [ ] Numbers are in the UI font instead of IBM Plex Mono, or columns of figures don't line up.
- [ ] The kitchen display has soft shadows, thin low-contrast type, or targets under 56px.
- [ ] Anything on a staff screen animates other than the ticket timer.
- [ ] Guest and staff screens look identical — the split identity was ignored.
- [ ] There's a tax, VAT or levy line anywhere.
- [ ] The owner dashboard leads with revenue instead of variance.
- [ ] The "Money taken" tile got renamed to Revenue, Sales or Profit.
- [ ] A pie chart, a dual-axis chart, or a value label on every single bar.
- [ ] Emoji used as icons or section markers.
- [ ] Every block is a rounded card with a coloured left rail.
- [ ] Placeholder content — "Item 1", lorem ipsum, "$9.99", or dishes that aren't on the menu above.
- [ ] Anything is centred that shouldn't be, or everything is centred.
- [ ] The void button is a solid red fill rather than an outline.
- [ ] Connection state isn't visible on staff screens.

---

# Build order

Generate in this order — it matches the build phases, so nothing is designed before it's needed:

**First:** 7 (kitchen display) · 8 (cashier) · 6 (floor view) · 2 (guest menu)
These four are the product. Get them right before anything else.

**Second:** 5 (PIN login) · 3 (options sheet) · 1 (welcome) · 4 (order status) · 10 (manager auth)

**Third:** 12 (owner overview) · 11 (shift close) · 13 (audit log)

**Last:** 9 (split bill) · 14 (menu management) · 15 (staff and devices)

Design 7 first, not 1. The kitchen display is the hardest screen and the one the whole system
lives or dies on — if the design system survives that screen, everything else is straightforward.
Welcome screens are easy and flatter the design system in ways that hide its weaknesses.
