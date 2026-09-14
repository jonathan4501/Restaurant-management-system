# 03 — Data model

PostgreSQL. Reference schema — Django models should mirror this shape.

**No tax tables.** There is no `tax_rules`, no `order_tax_lines`, no `fiscal_invoices`. Menu prices
are what the guest pays and the order total is the sum of the lines. See `decisions/0005`.

---

## Conventions, enforced everywhere

1. **Money is `INTEGER` pesewas.** `7500` is GH₵ 75.00. No floats, no `NUMERIC`, no `Decimal` in the
   schema. Format only at the UI edge.
2. **`restaurant_id` on every table**, enforced by a base manager, not by remembering.
3. **UUIDv7 primary keys**, generated client-side where the client originates the entity — this is
   what makes offline writes and idempotency work.
4. **No hard deletes.** `voided_at`, `revoked_at`, `is_active`.
5. **Snapshot** name and price onto order lines. Never join to `menu_items` for history.

> **Amended 2026-09-14** by ADR-0007 (one event stream, per-restaurant `seq`) and ADR-0008 (the bill is
> the table session). Also added: `drawer_movements`, `order_counters`, `idempotency_keys`, and a
> nullable `orders.order_number` assigned at submit. All changes are additive to the original draft.

---

## Tenancy and people

```sql
CREATE TABLE restaurants (
    id                UUID PRIMARY KEY,
    name              TEXT NOT NULL,
    timezone          TEXT NOT NULL DEFAULT 'Africa/Accra',
    currency          CHAR(3) NOT NULL DEFAULT 'GHS',
    day_cutover_hour  SMALLINT NOT NULL DEFAULT 4,   -- business date rolls at 04:00 local
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE staff (
    id            UUID PRIMARY KEY,
    restaurant_id UUID NOT NULL REFERENCES restaurants(id),
    full_name     TEXT NOT NULL,
    role          TEXT NOT NULL
                  CHECK (role IN ('WAITER','KITCHEN','CASHIER','MANAGER','OWNER')),
    pin_hash      TEXT NOT NULL,          -- argon2id. Never plaintext, never md5/sha1.
    email         TEXT,                   -- MANAGER/OWNER only
    totp_secret   TEXT,                   -- MANAGER/OWNER only, encrypted at rest
    is_active     BOOLEAN NOT NULL DEFAULT true,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX ON staff (restaurant_id, email) WHERE email IS NOT NULL;

CREATE TABLE devices (
    id                UUID PRIMARY KEY,
    restaurant_id     UUID NOT NULL REFERENCES restaurants(id),
    label             TEXT NOT NULL,              -- 'Kitchen screen', 'Tablet 3'
    device_token_hash TEXT,                       -- sha256 of the bearer token; NULL until enrolled
    enrolment_code    TEXT,                       -- one-time code shown in the back office
    enrolment_expires_at TIMESTAMPTZ,
    allowed_roles     TEXT[] NOT NULL,
    last_seen_at      TIMESTAMPTZ,
    enrolled_at       TIMESTAMPTZ,
    revoked_at        TIMESTAMPTZ
);

-- Every write carries a client-generated Idempotency-Key. The first request stores its response;
-- a replay returns it unchanged. See docs/07-backend-architecture.md §3.
CREATE TABLE idempotency_keys (
    restaurant_id     UUID NOT NULL REFERENCES restaurants(id),
    key               UUID NOT NULL,
    request_hash      TEXT NOT NULL,              -- sha256(method + path + body)
    status            TEXT NOT NULL CHECK (status IN ('IN_PROGRESS','DONE')),
    response_status   SMALLINT,
    response_body     JSONB,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (restaurant_id, key)
);
```

## Menu

```sql
CREATE TABLE menu_categories (
    id            UUID PRIMARY KEY,
    restaurant_id UUID NOT NULL REFERENCES restaurants(id),
    name          TEXT NOT NULL,
    sort_order    INTEGER NOT NULL DEFAULT 0,
    is_active     BOOLEAN NOT NULL DEFAULT true
);

CREATE TABLE menu_items (
    id             UUID PRIMARY KEY,
    restaurant_id  UUID NOT NULL REFERENCES restaurants(id),
    category_id    UUID NOT NULL REFERENCES menu_categories(id),
    name           TEXT NOT NULL,
    description    TEXT,
    image_url      TEXT,
    price_pesewas  INTEGER NOT NULL CHECK (price_pesewas >= 0),  -- what the guest pays
    prep_station   TEXT NOT NULL DEFAULT 'KITCHEN'
                   CHECK (prep_station IN ('KITCHEN','GRILL','BAR')),
    is_available   BOOLEAN NOT NULL DEFAULT true,   -- the 86 switch
    is_active      BOOLEAN NOT NULL DEFAULT true,   -- retired from the menu entirely
    sort_order     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE modifier_groups (
    id            UUID PRIMARY KEY,
    restaurant_id UUID NOT NULL REFERENCES restaurants(id),
    name          TEXT NOT NULL,                    -- 'Pepper level', 'Add extras'
    selection     TEXT NOT NULL CHECK (selection IN ('ONE','MANY')),
    is_required   BOOLEAN NOT NULL DEFAULT false,
    sort_order    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE modifiers (
    id             UUID PRIMARY KEY,
    restaurant_id  UUID NOT NULL REFERENCES restaurants(id),
    group_id       UUID NOT NULL REFERENCES modifier_groups(id),
    name           TEXT NOT NULL,                   -- 'No pepper', 'Extra plantain'
    price_pesewas  INTEGER NOT NULL DEFAULT 0,      -- 0 for free choices
    is_default     BOOLEAN NOT NULL DEFAULT false,
    is_available   BOOLEAN NOT NULL DEFAULT true,
    sort_order     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE menu_item_modifier_groups (
    menu_item_id UUID NOT NULL REFERENCES menu_items(id),
    group_id     UUID NOT NULL REFERENCES modifier_groups(id),
    sort_order   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (menu_item_id, group_id)
);
```

## Floor and orders

```sql
CREATE TABLE tables (
    id            UUID PRIMARY KEY,
    restaurant_id UUID NOT NULL REFERENCES restaurants(id),
    number        TEXT NOT NULL,          -- text: '7', '12A', 'Terrace 2'
    seats         INTEGER,
    qr_token      TEXT NOT NULL,          -- for guest-phone ordering
    is_active     BOOLEAN NOT NULL DEFAULT true,
    UNIQUE (restaurant_id, number)
);

CREATE TABLE table_sessions (
    id            UUID PRIMARY KEY,
    restaurant_id UUID NOT NULL REFERENCES restaurants(id),
    table_id      UUID NOT NULL REFERENCES tables(id),
    opened_by     UUID NOT NULL REFERENCES staff(id),
    party_size    INTEGER,
    opened_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at     TIMESTAMPTZ
);
CREATE UNIQUE INDEX one_open_session_per_table
    ON table_sessions (table_id) WHERE closed_at IS NULL;

-- ADR-0008: the session is the bill. These are projection columns maintained by the runner.
ALTER TABLE table_sessions
    ADD COLUMN bill_total_pesewas INTEGER NOT NULL DEFAULT 0,   -- Σ non-voided orders.total
    ADD COLUMN paid_pesewas       INTEGER NOT NULL DEFAULT 0,   -- Σ non-voided payments.amount
    ADD COLUMN settled_at         TIMESTAMPTZ,                  -- balance reached zero
    ADD COLUMN reopened_count     INTEGER NOT NULL DEFAULT 0;

-- Order numbers are sequential per restaurant per business date and assigned at SUBMIT, never at
-- draft creation, so abandoned drafts do not create false gaps. Locked with SELECT ... FOR UPDATE.
CREATE TABLE order_counters (
    restaurant_id  UUID NOT NULL REFERENCES restaurants(id),
    business_date  DATE NOT NULL,
    next_number    INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (restaurant_id, business_date)
);

CREATE TABLE orders (
    id             UUID PRIMARY KEY,
    restaurant_id  UUID NOT NULL REFERENCES restaurants(id),
    session_id     UUID NOT NULL REFERENCES table_sessions(id),
    business_date  DATE,                   -- set at submit, from restaurants.day_cutover_hour
    order_number   INTEGER,                -- NULL while DRAFT; sequential per business date; gaps are an alarm
    status         TEXT NOT NULL DEFAULT 'DRAFT'
                   CHECK (status IN ('DRAFT','SUBMITTED','PREPARING','READY','SERVED','CLOSED','VOIDED')),
    subtotal_pesewas  INTEGER NOT NULL DEFAULT 0,   -- Σ line totals
    discount_pesewas  INTEGER NOT NULL DEFAULT 0,
    total_pesewas     INTEGER NOT NULL DEFAULT 0,   -- subtotal − discount. This is the whole calc.
    placed_by      UUID REFERENCES staff(id),       -- NULL when the guest ordered themselves
    origin         TEXT NOT NULL DEFAULT 'WAITER'
                   CHECK (origin IN ('WAITER','GUEST_TABLET','GUEST_QR')),
    submitted_at   TIMESTAMPTZ,
    acknowledged_at TIMESTAMPTZ,
    ready_at       TIMESTAMPTZ,
    served_at      TIMESTAMPTZ,
    closed_at      TIMESTAMPTZ,
    voided_at      TIMESTAMPTZ,
    void_reason    TEXT,
    voided_by      UUID REFERENCES staff(id),
    authorised_by  UUID REFERENCES staff(id),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (restaurant_id, business_date, order_number)
);
CREATE INDEX ON orders (restaurant_id, status, created_at DESC);
CREATE INDEX ON orders (restaurant_id, session_id);

CREATE TABLE order_items (
    id            UUID PRIMARY KEY,
    restaurant_id UUID NOT NULL REFERENCES restaurants(id),
    order_id      UUID NOT NULL REFERENCES orders(id),
    menu_item_id  UUID NOT NULL REFERENCES menu_items(id),

    -- SNAPSHOTS. Never join to menu_items to price or label a historical line.
    name_snapshot       TEXT NOT NULL,
    unit_price_pesewas  INTEGER NOT NULL,
    prep_station        TEXT NOT NULL,

    quantity      INTEGER NOT NULL CHECK (quantity > 0),
    modifiers     JSONB NOT NULL DEFAULT '[]',   -- [{name, price_pesewas}] — also snapshots
    notes         TEXT,
    course        INTEGER NOT NULL DEFAULT 1,     -- firing order
    status        TEXT NOT NULL DEFAULT 'PENDING'
                  CHECK (status IN ('PENDING','PREPARING','READY','SERVED','VOIDED')),
    line_total_pesewas INTEGER NOT NULL           -- (unit_price + Σ modifier prices) × quantity
);
CREATE INDEX ON order_items (restaurant_id, order_id);
```

## The event log — the source of truth

One stream for every action in the restaurant (ADR-0007). The table keeps the name `order_events`
because every document and `CLAUDE.md` refer to it by that name; `aggregate_type` says what kind of
thing the event is about.

```sql
CREATE TABLE order_events (
    id                UUID PRIMARY KEY,            -- UUIDv7, client-generated
    restaurant_id     UUID NOT NULL REFERENCES restaurants(id),
    seq               BIGINT NOT NULL,             -- per restaurant, gapless, assigned under an advisory lock
    aggregate_type    TEXT NOT NULL
                      CHECK (aggregate_type IN ('ORDER','SESSION','SHIFT','MENU_ITEM','DEVICE','STAFF')),
    aggregate_id      UUID NOT NULL,
    order_id          UUID,                        -- set for ORDER events and SESSION events about one order
    event_type        TEXT NOT NULL,
    payload           JSONB NOT NULL,
    actor_id          UUID REFERENCES staff(id),   -- NULL when the guest or the system acted
    actor_role        TEXT NOT NULL
                      CHECK (actor_role IN ('WAITER','KITCHEN','CASHIER','MANAGER','OWNER','GUEST','SYSTEM')),
    authorised_by     UUID REFERENCES staff(id),   -- the manager who approved an override
    reason_code       TEXT,                        -- mandatory on authorised actions; promoted for reporting
    device_id         UUID REFERENCES devices(id),
    idempotency_key   UUID NOT NULL,
    client_created_at TIMESTAMPTZ NOT NULL,        -- what the device claimed
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),  -- what the server knows
    CONSTRAINT uniq_seq  UNIQUE (restaurant_id, seq),
    CONSTRAINT uniq_idem UNIQUE (restaurant_id, idempotency_key)
);

CREATE INDEX ON order_events (restaurant_id, order_id, seq) WHERE order_id IS NOT NULL;
CREATE INDEX ON order_events (restaurant_id, aggregate_type, aggregate_id, seq);
CREATE INDEX ON order_events (restaurant_id, created_at DESC);
CREATE INDEX ON order_events (restaurant_id, event_type, created_at DESC);
CREATE INDEX ON order_events (restaurant_id, actor_id, created_at DESC);

-- Append-only, enforced by the database rather than by discipline.
-- A trigger always exists (works on managed Postgres without custom roles); REVOKE is added on top
-- wherever the app connects with a dedicated role.
CREATE FUNCTION order_events_append_only() RETURNS trigger AS $$
BEGIN RAISE EXCEPTION 'order_events is append-only'; END $$ LANGUAGE plpgsql;
CREATE TRIGGER order_events_no_update BEFORE UPDATE OR DELETE ON order_events
    FOR EACH ROW EXECUTE FUNCTION order_events_append_only();
REVOKE UPDATE, DELETE ON order_events FROM app_user;
```

### Event vocabulary

| Aggregate | Events |
|---|---|
| `ORDER` | `ORDER_OPENED` `ITEM_ADDED` `ITEM_REMOVED` `ITEM_MODIFIED` `ORDER_SUBMITTED` `KITCHEN_ACKNOWLEDGED` `ITEM_STARTED` `ITEM_READY` `ORDER_READY` `ORDER_SERVED` `COURSE_FIRED` `DISCOUNT_APPLIED` `COMP_APPLIED` `PRICE_OVERRIDDEN` `ORDER_VOIDED` `ORDER_CLOSED` `ORDER_REOPENED` |
| `SESSION` | `SESSION_OPENED` `PAYMENT_RECORDED` `PAYMENT_VOIDED` `SESSION_SETTLED` `SESSION_REOPENED` `SESSION_CLOSED` `RECEIPT_REQUESTED` |
| `SHIFT` | `SHIFT_OPENED` `DRAWER_MOVEMENT` `DRAWER_COUNTED` `SHIFT_CLOSED` |
| `MENU_ITEM` | `ITEM_86ED` `ITEM_RESTORED` `PRICE_CHANGED` |
| `DEVICE` | `DEVICE_ENROLLED` `DEVICE_REVOKED` `PIN_FAILED` `PIN_LOCKED` |
| `STAFF` | `MANAGER_AUTHORISED` |

Events whose type is in the **flagged set** — `ORDER_VOIDED` (after acknowledgement), `DISCOUNT_APPLIED`,
`COMP_APPLIED`, `PRICE_OVERRIDDEN`, `ORDER_REOPENED`, `SESSION_REOPENED`, `PAYMENT_VOIDED`,
`DRAWER_MOVEMENT`, `PIN_FAILED`, `PIN_LOCKED`, `PRICE_CHANGED` during service — render visually distinct
in the owner's log. The flag is derived from the type; it is not a stored column.

## Payments, shifts, and the drawer

```sql
CREATE TABLE shifts (
    id                     UUID PRIMARY KEY,
    restaurant_id          UUID NOT NULL REFERENCES restaurants(id),
    cashier_id             UUID NOT NULL REFERENCES staff(id),
    opened_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at              TIMESTAMPTZ,
    opening_float_pesewas  INTEGER NOT NULL,
    declared_cash_pesewas  INTEGER,      -- what the cashier counted
    expected_cash_pesewas  INTEGER,      -- float + cash payments − payouts
    variance_pesewas       INTEGER GENERATED ALWAYS AS
        (declared_cash_pesewas - expected_cash_pesewas) STORED,   -- the money question
    closed_by              UUID REFERENCES staff(id),
    notes                  TEXT
);
CREATE UNIQUE INDEX one_open_shift_per_cashier
    ON shifts (cashier_id) WHERE closed_at IS NULL;

-- Cash that moves without a sale. NO_SALE opens the drawer; PAID_OUT is cash leaving (supplier paid
-- from the till); PAID_IN is cash arriving. All three need a manager PIN and a reason.
CREATE TABLE drawer_movements (
    id              UUID PRIMARY KEY,
    restaurant_id   UUID NOT NULL REFERENCES restaurants(id),
    shift_id        UUID NOT NULL REFERENCES shifts(id),
    kind            TEXT NOT NULL CHECK (kind IN ('NO_SALE','PAID_OUT','PAID_IN')),
    amount_pesewas  INTEGER NOT NULL DEFAULT 0 CHECK (amount_pesewas >= 0),   -- 0 for NO_SALE
    reason_code     TEXT NOT NULL,
    note            TEXT,
    recorded_by     UUID NOT NULL REFERENCES staff(id),
    authorised_by   UUID NOT NULL REFERENCES staff(id),
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON drawer_movements (restaurant_id, shift_id);

-- expected_cash = opening_float + Σ CASH payments.amount − Σ PAID_OUT + Σ PAID_IN   (non-voided only)

CREATE TABLE payments (
    id                 UUID PRIMARY KEY,
    restaurant_id      UUID NOT NULL REFERENCES restaurants(id),
    session_id         UUID NOT NULL REFERENCES table_sessions(id),   -- ADR-0008: the bill
    order_id           UUID REFERENCES orders(id),                    -- only when paying one round
    shift_id           UUID NOT NULL REFERENCES shifts(id),
    method             TEXT NOT NULL
                       CHECK (method IN ('CASH','MOMO_MTN','MOMO_TELECEL','MOMO_AT','CARD','BANK')),
    amount_pesewas     INTEGER NOT NULL CHECK (amount_pesewas > 0),
    tendered_pesewas   INTEGER,          -- cash only, for change
    change_pesewas     INTEGER,          -- cash only
    external_reference TEXT,             -- MoMo transaction ID, keyed by the cashier
    recorded_by        UUID NOT NULL REFERENCES staff(id),
    recorded_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    voided_at          TIMESTAMPTZ,
    void_reason        TEXT,
    voided_by          UUID REFERENCES staff(id),
    void_authorised_by UUID REFERENCES staff(id)
);
CREATE INDEX ON payments (restaurant_id, shift_id);
CREATE INDEX ON payments (restaurant_id, session_id);
CREATE INDEX ON payments (restaurant_id, recorded_at DESC);
```

A bill supports **several payments** — that is what makes split bills and partial settlement work.
The bill is the table session (ADR-0008): a session is `settled` when
`Σ non-voided payments.amount_pesewas >= Σ non-voided orders.total_pesewas`, at which point every
`SERVED` order in it becomes `CLOSED` in the same transaction. Orders not yet served block settlement.

---

## Reporting

Read from projections and aggregates, never by folding the event log at query time.
Daily rollups are computed by a Celery job and stored:

```sql
CREATE TABLE daily_sales (
    restaurant_id        UUID NOT NULL REFERENCES restaurants(id),
    business_date        DATE NOT NULL,
    money_taken_pesewas  INTEGER NOT NULL,   -- gross cash through the till. NOT revenue.
    covers               INTEGER NOT NULL,
    orders_closed        INTEGER NOT NULL,
    orders_voided        INTEGER NOT NULL,
    void_value_pesewas   INTEGER NOT NULL,
    discount_pesewas     INTEGER NOT NULL,
    cash_variance_pesewas INTEGER NOT NULL,
    PRIMARY KEY (restaurant_id, business_date)
);
```

Note the column name: **`money_taken_pesewas`**. It is gross cash before tax, cost of goods, wages
and rent. Do not surface it in the UI as "Revenue" or "Profit". See `decisions/0005`.

"Business date" is not calendar date — a restaurant's day runs past midnight. Define it as
`opened_at` shifted by a per-restaurant cutover hour (default 04:00 Africa/Accra).
