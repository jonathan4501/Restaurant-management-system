# 07 — Backend architecture

Module-level design of the Django backend. `02-architecture.md` says *why*; this says *what goes where
and how it is wired*. Code sketches here are the actual interfaces in `backend/apps/core` — if the code
and this document disagree, fix one of them in the same PR.

---

## 1. One write path

```
HTTP POST ─► DRF CommandView ─► run_command(ctx, handler)
                                   │
                                   ├─ 1. idempotency: claim key, or replay stored response
                                   ├─ 2. transaction.atomic()
                                   ├─ 3. pg_advisory_xact_lock(restaurant)     ← serialises appends per tenant
                                   ├─ 4. handler(ctx) → CommandOutcome         ← locks its aggregate, validates,
                                   │                                             returns EventDrafts + response
                                   ├─ 5. append events: seq = last+1, server created_at
                                   ├─ 6. projector.apply(event) for each       ← same code as rebuild
                                   ├─ 7. idempotency: store response
                                   └─ 8. on_commit → Redis publish(envelope)   ← SSE fan-out
```

There is no other way to change state. Django admin edits to menu/staff are configuration, not
operations; the few admin actions that matter operationally (price change during service, 86, revoke
device) are wired to commands too.

### Interfaces (`apps/core/commands.py`)

```python
@dataclass(frozen=True)
class CommandContext:
    restaurant_id: UUID
    actor_id: UUID | None          # None for GUEST and SYSTEM
    actor_role: ActorRole          # WAITER KITCHEN CASHIER MANAGER OWNER GUEST SYSTEM
    device_id: UUID | None
    authorised_by: UUID | None     # resolved from a manager authorisation token
    reason_code: str | None
    idempotency_key: UUID
    client_created_at: datetime
    request_hash: str

@dataclass(frozen=True)
class EventDraft:
    aggregate_type: AggregateType  # ORDER SESSION SHIFT MENU_ITEM DEVICE STAFF
    aggregate_id: UUID
    event_type: str                # from apps.orders.events vocabulary
    payload: dict[str, Any]        # produced by the event's dataclass .to_payload()
    order_id: UUID | None = None
    event_id: UUID | None = None   # client-supplied UUIDv7 when the client originated it

@dataclass
class CommandOutcome:
    events: list[EventDraft]
    response: dict[str, Any]
    status: int = 200

Handler = Callable[[CommandContext], CommandOutcome]

def run_command(ctx: CommandContext, handler: Handler) -> CommandResponse: ...
```

A handler is a plain function. It uses `select_for_update()` on the aggregate row it changes, checks
the state machine, computes totals, and returns events. It **does not** write projection tables —
the projector does that from the events, so that `rebuild_projections` produces byte-identical rows.

### `CommandView` (`apps/core/views.py`)

```python
class CommandView(APIView):
    authentication_classes = [DeviceStaffAuthentication]   # WS01 adds Guest and Owner variants
    permission_classes = [RolePermission]                    # declares allowed_roles
    input_serializer: type[Serializer]
    allowed_roles: tuple[ActorRole, ...]
    requires_authorisation: bool = False                     # manager PIN + reason_code

    def handle(self, ctx: CommandContext, data: dict, **kwargs) -> CommandOutcome: ...
```

`CommandView.post` reads and validates `Idempotency-Key` (UUIDv7, required, else 400
`idempotency_key_missing`), builds `CommandContext` from the authenticated principal, resolves the
optional `authorisation` block into `authorised_by` + `reason_code`, and calls `run_command`.

---

## 2. Tenancy (`apps/core/tenancy.py`)

```python
_current: ContextVar[UUID | None]

def set_current_restaurant(rid) / get_current_restaurant() / restaurant_context(rid)  # contextmanager

class TenantManager(models.Manager):
    def get_queryset(self):
        rid = get_current_restaurant()
        if rid is None: raise TenantContextMissing
        return super().get_queryset().filter(restaurant_id=rid)
    def unscoped(self): return super().get_queryset()      # grep-checked; allow-list in CI

class TenantModel(models.Model):
    id = UUIDField(primary_key=True, default=uuid7, editable=False)
    restaurant = ForeignKey("accounts.Restaurant", on_delete=PROTECT)
    objects = TenantManager()
    class Meta: abstract = True
```

- Auth middleware sets the context for every authenticated request from the principal's restaurant.
- Celery tasks and management commands wrap their work in `restaurant_context(rid)`.
- Related managers (`order.items.all()`) inherit the tenant filter automatically.
- Django admin uses `TenantAdmin` (`apps/core/admin.py`), whose `get_queryset` scopes to the owner's
  restaurant. Superusers with no restaurant see nothing rather than everything.
- A cross-tenant id in a URL returns **404**, never 403 — do not confirm existence.

---

## 3. Idempotency (`apps/core/idempotency.py`)

Table `idempotency_keys (restaurant_id, key) PRIMARY KEY`, `request_hash`, `status`, `response_*`.

```
claim(ctx):
    INSERT (status=IN_PROGRESS) in its own short transaction
    on conflict → read the row:
        DONE  and same request_hash   → return Replay(status, body)   + header Idempotent-Replayed: true
        DONE  and different hash      → 422 idempotency_key_reused
        IN_PROGRESS younger than 60 s → 409 idempotency_in_progress
        IN_PROGRESS older than 60 s   → take over (the earlier attempt died before commit)
complete(ctx, status, body):  UPDATE the row inside the command transaction
```

`request_hash = sha256(method + path + canonical_json(body))`. The claim row commits before the command
transaction opens so that a concurrent duplicate sees it immediately; the response is written inside
the command transaction so that a rollback leaves the key claimable again after the 60 s window.

---

## 4. The event store (`apps/orders/models.py::OrderEvent`)

Columns as in `03-data-model.md` (ADR-0007). Points that matter in code:

- `seq` is assigned by the runner as `max(seq)+1` **for this restaurant**, inside the advisory lock.
  Never rely on a DB sequence here.
- Append-only is enforced by a Postgres trigger created in migration `orders/0002_append_only_trigger`
  (with a reverse that drops it). `REVOKE UPDATE, DELETE` is applied by `infra/db/roles.sql` where a
  separate app role exists. A test in `orders/tests/test_append_only.py` attempts an `UPDATE` and expects
  `django.db.utils.InternalError`.
- `OrderEvent.objects` is a `TenantManager`; there is no `save()` path exposed — the runner uses
  `bulk_create` on a list built from `EventDraft`s.
- Event vocabulary lives in `apps/orders/events.py`: an `EventType` `StrEnum` plus one frozen dataclass
  per type with `to_payload()`. Adding an event = adding an enum member and a dataclass; the
  `test_every_event_has_a_payload_class` test enforces it.

### Projections (`apps/*/projector.py`)

```python
@project(EventType.ORDER_SUBMITTED)
def _(event: OrderEvent) -> None: ...        # updates orders / order_items rows
```

A registry in `apps/core/projections.py` maps `event_type → [handlers]`. The runner calls
`apply(event)` after appending each event, inside the same transaction. `manage.py rebuild_projections
--restaurant <id>` truncates the projection tables for that restaurant and replays every event through the
same registry; `manage.py verify_projections` rebuilds into a temporary schema and diffs. Projection code
must therefore be **deterministic** and must not read the clock: use `event.created_at`.

---

## 5. State machine (`apps/orders/state_machine.py`)

```python
class OrderStatus(StrEnum): DRAFT SUBMITTED PREPARING READY SERVED CLOSED VOIDED
class OrderCommand(StrEnum): ADD_ITEM REMOVE_ITEM MODIFY_ITEM SUBMIT ACK START_ITEM READY_ITEM READY SERVE
                             DISCOUNT COMP PRICE_OVERRIDE VOID CLOSE REOPEN

@dataclass(frozen=True)
class Transition:
    to: OrderStatus
    requires_authorisation: bool       # manager PIN + reason code
    emits: EventType

TRANSITIONS: dict[tuple[OrderStatus, OrderCommand], Transition] = {
    (DRAFT, ADD_ITEM):       Transition(DRAFT, False, ITEM_ADDED),
    (DRAFT, SUBMIT):         Transition(SUBMITTED, False, ORDER_SUBMITTED),
    (SUBMITTED, ACK):        Transition(PREPARING, False, KITCHEN_ACKNOWLEDGED),
    (SUBMITTED, VOID):       Transition(VOIDED, False, ORDER_VOIDED),      # nothing cooked yet
    (PREPARING, VOID):       Transition(VOIDED, True,  ORDER_VOIDED),
    (READY, VOID):           Transition(VOIDED, True,  ORDER_VOIDED),
    (SERVED, VOID):          Transition(VOIDED, True,  ORDER_VOIDED),
    (PREPARING, READY):      Transition(READY, False, ORDER_READY),
    (READY, SERVE):          Transition(SERVED, False, ORDER_SERVED),
    (SERVED, CLOSE):         Transition(CLOSED, False, ORDER_CLOSED),      # only via session settlement
    (CLOSED, REOPEN):        Transition(SERVED, True,  ORDER_REOPENED),
    ...
}

def transition(status, command) -> Transition   # raises IllegalTransition → 409 illegal_transition
```

Item-level statuses (`PENDING PREPARING READY SERVED VOIDED`) have their own small table in the same
module. Discounts, comps and price overrides do not change status but are listed because they
**require authorisation**; the table is the single place that says so.

`test_state_machine.py` iterates every `(status, command)` pair and asserts either the expected
transition or `IllegalTransition`. A new command without a test entry fails the test.

---

## 6. Authentication and principals (`apps/accounts`)

```python
@dataclass(frozen=True)
class Principal:
    kind: Literal["STAFF", "GUEST", "OWNER", "SYSTEM"]
    restaurant_id: UUID
    actor_id: UUID | None
    actor_role: ActorRole
    device_id: UUID | None
    session_id: UUID | None        # GUEST only — the one table session it may touch
```

| Principal | How it is established | Class |
|---|---|---|
| Device | `X-Device-Token: <opaque>` → `Device` by `sha256(token)`, not revoked | required for STAFF |
| Staff | `Authorization: Bearer <JWT>` HS256, 12 h, claims `{sub: staff_id, role, rid, did}`; `did` must equal the device | `DeviceStaffAuthentication` |
| Owner | Django session + `django-otp` verified | `OwnerSessionAuthentication` |
| Guest | `Authorization: Bearer <JWT>` 2 h, claims `{sid: session_id, rid, role: GUEST, mode}` | `GuestAuthentication` — only on `/api/v1/guest/…` |

**PIN login** (`POST /auth/pin`): argon2id verify; failures counted in Redis `pin_fail:{device_id}`;
5 failures → `PIN_LOCKED` event and 15-minute lockout returned as 423 `pin_locked`; every failure appends
`PIN_FAILED` (aggregate `DEVICE`).

**Manager authorisation** (`POST /auth/authorise` `{pin, purpose}`): verifies a MANAGER/OWNER PIN, emits
`MANAGER_AUTHORISED`, returns `{authorisation_token, expires_in: 60}` stored in Redis as
`auth:{token} → {staff_id, device_id, purpose}`. A command that `requires_authorisation` must carry
`"authorisation": {"token": "...", "reason_code": "..."}`; the runner consumes the token (single use),
checks `purpose` matches the command, and fills `ctx.authorised_by`. Missing or wrong → 403
`authorisation_required`. The waiter or cashier remains the `actor`; the manager is `authorised_by`.
Two names on every override — that is the collusion-visibility requirement from `02-architecture.md §7`.

**Guest sandbox**: `GuestAuthentication` sets `Principal.session_id`; every guest view filters by it and
the guest router exposes only menu read, own draft build/submit, and own order status. No SSE. Guest
requests are rate-limited per session (DRF throttle, 60/min). A guest token for a closed session is 401.

---

## 7. Realtime (`apps/realtime`)

- `GET /api/v1/stream` is a Django **async** view (not DRF), authenticated by the same headers via
  `sync_to_async(resolve_principal)`. It returns `StreamingHttpResponse(agen(), content_type="text/event-stream")`
  with `Cache-Control: no-cache` and `X-Accel-Buffering: no`.
- On connect: if `Last-Event-ID` (or `?since=`) is present, replay `order_events` for the restaurant with
  `seq > since` in order **before** subscribing, then subscribe to Redis channel `events:{restaurant_id}` and
  forward, skipping any envelope with `seq <= last_sent`. Heartbeat `: keepalive\n\n` every 15 s.
- Role filter: `visible_to(role, envelope)` in `realtime/filters.py`. KITCHEN sees `ORDER` and `MENU_ITEM`;
  CASHIER sees `ORDER`, `SESSION`, `SHIFT`, `MENU_ITEM`; WAITER sees `ORDER`, `SESSION`, `MENU_ITEM`;
  MANAGER/OWNER see all. GUEST has no stream.
- Envelope (also the `data:` JSON):
  `{"id", "seq", "type", "aggregate_type", "aggregate_id", "order_id", "actor_role", "reason_code", "created_at", "payload"}`.
  `id:` line = `seq`. `event:` line = `type`.
- `GET /api/v1/events?since=<seq>&limit=200` returns the same envelopes as JSON for the polling fallback.
- Publisher: `apps/core/publisher.py::publish(restaurant_id, envelope)` called from
  `transaction.on_commit`. If Redis is down the publish fails **silently to the client** (logged to Sentry);
  clients recover on next reconnect via replay. Never fail a command because pub/sub failed.

---

## 8. Money (`apps/core/money.py`, `apps/orders/totals.py`)

```python
class PesewasField(models.IntegerField): ...          # the only money column type
def line_total(unit_price: int, modifier_prices: Iterable[int], quantity: int) -> int
def order_total(line_totals: Iterable[int], discount: int) -> int    # never below zero
```

Integers in, integers out, `int` type hints, mypy strict on these modules. Property-based tests assert
`line_total(u, m, q) == (u + sum(m)) * q` and `0 <= order_total <= sum(lines)`. Percent discounts
round **half up to the pesewa** using `Decimal` **inside the function only** — the value stored and
returned is `int`. No other module imports `Decimal`.

---

## 9. Payments and shifts (`apps/payments`)

- `POST /sessions/{id}/payments` handler: requires an open shift for `ctx.actor_id` (403 `shift_required`);
  loads the session `FOR UPDATE`; `balance = bill_total − paid`; rejects `amount > balance`
  (422 `overpayment`); cash requires `tendered ≥ amount`, `change = tendered − amount`; emits
  `PAYMENT_RECORDED`; if the new balance is 0 also emits `SESSION_SETTLED` and one `ORDER_CLOSED` per
  `SERVED` order. Any order in `SUBMITTED/PREPARING/READY` → 409 `unserved_orders`.
- `PAYMENT_VOIDED` requires authorisation; recomputes `paid`; if the session was settled it emits
  `SESSION_REOPENED` and `ORDER_REOPENED` per order (both flagged).
- Shift close: `expected = float + Σ cash − Σ PAID_OUT + Σ PAID_IN` computed server-side from projections;
  `declared` from the cashier; `variance` is a stored generated column.

---

## 10. Reporting (`apps/reporting`)

Reads projections only — never folds the event log at request time. `daily_sales` is written by the
Celery beat task `rollup_daily_sales` at `day_cutover_hour` for the previous business date and can be
re-run idempotently. The four owner endpoints in `09-api-contract.md §Owner` map one-to-one to the four
panels in `01-product-spec.md §8`, in that order. The money figure is `money_taken_pesewas` and its
OpenAPI description reads "Money taken (gross cash through the till)".

---

## 11. Errors (`apps/core/errors.py`)

All errors are RFC 9457 `application/problem+json`:

```json
{"type": "https://renzy.app/errors/illegal_transition", "title": "Illegal transition",
 "status": 409, "code": "illegal_transition", "detail": "Cannot ack an order in status READY",
 "errors": {}}
```

`ApiError(status, code, detail, errors=None)` raised anywhere in a handler becomes this shape. DRF
`ValidationError` becomes `400 validation_error` with field errors under `errors`. The full `code` list is
in `09-api-contract.md §2`.

---

## 12. Observability and operations

- Sentry: `sentry_sdk` with Django, Celery, Redis integrations; `restaurant_id` and `device_id` as tags.
- Logging: JSON to stdout, one line per request with `request_id`, `restaurant_id`, `actor_id`, latency.
- `GET /healthz` checks DB and Redis; `GET /readyz` additionally checks migrations are applied.
- Management commands: `seed_renzy`, `rebuild_projections`, `verify_projections`, `enrol_device`,
  `set_pin`, `rollup_daily_sales --date`.
- Every Celery task is idempotent and keyed by `(restaurant_id, business_date)`.

---

## 13. Settings and secrets

`config/settings/base.py` reads everything from environment via `environ`-style helpers; `dev.py`,
`test.py`, `prod.py` override. Required env: `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`,
`JWT_SIGNING_KEY`, `TOTP_ENCRYPTION_KEY`, `SENTRY_DSN` (prod), `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`.
`infra/.env.example` lists all of them with dev-only values. Nothing secret is committed.
