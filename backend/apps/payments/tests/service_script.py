"""
A scripted RENZY service — the WS05 exit-criterion fixture, written to be imported by WS06.

Twenty tables across two tills, all six payment methods, two voided payments, one bill reopened on a
manager's PIN, one discount, one comp, one round cancelled before the kitchen saw it and one voided
after it had. Two tables are still owing money when the second till counts its drawer.

Everything runs through the real HTTP command surface (`CommandView` → `run_command`), so the
projections, the event log and the Z-report are the ones production would produce. Nothing here
writes a projection table.

Determinism does not come from a random seed: `TABLE_PLAN` *is* the seed. `expected_totals()` folds
that plan into `EXPECTED` with no database and no clock, so a report can assert exact pesewas and a
human can add the plan up by hand. Money is `int` pesewas everywhere, including the expectations.

From another workstream's tests:

    from apps.payments.tests.service_script import EXPECTED, run_service_script

    def test_money_taken(restaurant, api_client):
        service = run_service_script(restaurant)
        assert today["money_taken_pesewas"] == EXPECTED.money_taken_pesewas

…or take the fixture at the foot of this module:

    from apps.payments.tests.service_script import scripted_service  # noqa: F401

Two things the script deliberately does not give you. It runs at whatever wall-clock time the test
runs, so it cannot stand in for a business-date boundary case, and every order number it produces is
consecutive, so it cannot stand in for gap detection. Write those as their own small fixtures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, NamedTuple

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.authorisation import issue_authorisation
from apps.accounts.models import Device, Restaurant, Staff
from apps.accounts.pins import hash_pin
from apps.accounts.tokens import issue_staff_token, new_device_token
from apps.core.roles import AuthorisationPurpose
from apps.core.uuid7 import uuid7
from apps.floor.models import Table, TableSession
from apps.menu.models import MenuCategory, MenuItem, PrepStation
from apps.orders.totals import apply_percent_discount
from apps.payments.commands import normalise_reference
from apps.payments.models import DrawerMovement, PaymentMethod

# Reason codes the script uses. Reports group by these, so they are part of the contract.
DISCOUNT_REASON = "REGULAR_GUEST"
COMP_REASON = "SERVICE_RECOVERY"
CANCEL_REASON = "GUEST_CHANGED_MIND"  # void before the kitchen acknowledged: no PIN
VOID_AFTER_ACK_REASON = "WRONG_ITEM"  # void after acknowledgement: manager PIN
REOPEN_REASON = "ADD_ITEMS"


# ---------------------------------------------------------------- the menu


@dataclass(frozen=True)
class MenuSpec:
    name: str
    price_pesewas: int
    station: str


MENU: dict[str, MenuSpec] = {
    "jollof": MenuSpec("Jollof Rice with Grilled Chicken", 7500, PrepStation.KITCHEN),
    "banku": MenuSpec("Banku with Grilled Tilapia", 9500, PrepStation.GRILL),
    "waakye": MenuSpec("Waakye Special", 5500, PrepStation.KITCHEN),
    "kelewele": MenuSpec("Kelewele", 2500, PrepStation.KITCHEN),
    "malta": MenuSpec("Malta Guinness", 1200, PrepStation.BAR),
    "club": MenuSpec("Club Beer", 1800, PrepStation.BAR),
}

# A round is what the waiter sends to the kitchen in one go: menu key → quantity.
Round = dict[str, int]


# ---------------------------------------------------------------- the plan


@dataclass(frozen=True)
class Tender:
    """One thing the guest hands over. `amount_pesewas=None` means "settle whatever is left"."""

    method: str
    amount_pesewas: int | None = None
    tendered_pesewas: int | None = None  # cash handed over, when it differs from the amount
    reference: str | None = None  # MoMo / card / transfer id, keyed by hand
    voided: bool = False  # recorded, then voided on a manager's PIN
    void_reason: str = "WRONG_AMOUNT"


@dataclass(frozen=True)
class TablePlan:
    number: str
    party_size: int
    rounds: tuple[Round, ...]
    tenders: tuple[Tender, ...] = ()
    till: int = 0  # index into SHIFT_PLAN: which cashier takes the money
    discount_percent: int = 0  # manager-authorised, against the first round
    comp_round: int | None = None  # this round is comped to zero
    cancelled_round: Round | None = None  # sent, then voided before the kitchen acknowledged
    voided_round: Round | None = None  # sent, acknowledged, then voided on a manager's PIN
    reopen_round: Round | None = None  # served after a manager-authorised reopen
    reopen_after_tender: int = 0  # the reopen happens before this tender
    clear_table: bool = False  # session closed at the end: the table is wiped and free


@dataclass(frozen=True)
class Movement:
    kind: str
    amount_pesewas: int
    reason_code: str
    note: str = ""


@dataclass(frozen=True)
class ShiftPlan:
    cashier_name: str
    opening_float_pesewas: int
    movements: tuple[Movement, ...] = ()
    declared_variance_pesewas: int = 0  # what the count is out by; 0 = the drawer balances


CASH = PaymentMethod.CASH
MOMO_MTN = PaymentMethod.MOMO_MTN
MOMO_TELECEL = PaymentMethod.MOMO_TELECEL
MOMO_AT = PaymentMethod.MOMO_AT
CARD = PaymentMethod.CARD
BANK = PaymentMethod.BANK

SHIFT_PLAN: tuple[ShiftPlan, ...] = (
    ShiftPlan(
        cashier_name="Ama Owusu",
        opening_float_pesewas=20000,
        movements=(
            Movement(DrawerMovement.Kind.PAID_OUT, 10000, "SUPPLIER_PAID", "gas refill"),
            Movement(DrawerMovement.Kind.NO_SALE, 0, "NO_SALE", "wrong drawer opened"),
        ),
        declared_variance_pesewas=-2000,  # the classic short count
    ),
    ShiftPlan(
        cashier_name="Kwesi Asante",
        opening_float_pesewas=15000,
        movements=(Movement(DrawerMovement.Kind.PAID_IN, 5000, "CHANGE_FLOAT", "small notes"),),
        declared_variance_pesewas=0,
    ),
)

TABLE_PLAN: tuple[TablePlan, ...] = (
    # ------------------------------------------------ till 0: Ama's shift, tables 1–12
    TablePlan("1", 2, ({"jollof": 2, "malta": 2},), (Tender(CASH),), clear_table=True),
    TablePlan(
        "2",
        4,
        ({"banku": 4}, {"club": 4}),
        (Tender(MOMO_MTN, reference=" mp24 0917 aa "),),  # normalises to MP240917AA
        clear_table=True,
    ),
    TablePlan("3", 1, ({"waakye": 1},), (Tender(CASH),), clear_table=True),
    TablePlan(
        "4",
        3,
        ({"jollof": 3}, {"kelewele": 2}),
        (Tender(CASH, 10000), Tender(CARD, reference="CARD-8841")),
        clear_table=True,
    ),
    TablePlan("5", 2, ({"banku": 2},), (Tender(MOMO_TELECEL, reference="TL-5501"),)),
    TablePlan(
        "6",
        6,
        ({"jollof": 6}, {"club": 6}, {"kelewele": 3}),
        (Tender(CASH),),
        discount_percent=10,  # 10% off the food round: 4500
    ),
    TablePlan(
        "7",
        2,
        ({"jollof": 1, "malta": 1},),
        (Tender(CASH),),
        voided_round={"kelewele": 2},  # cooked, then voided: the owner should see 5000
    ),
    TablePlan(
        "8",
        5,
        ({"banku": 5},),
        (
            Tender(MOMO_MTN, reference="MP-WRONGTILL", voided=True, void_reason="WRONG_METHOD"),
            Tender(CASH),  # the guest actually paid cash; the bill reopens and settles again
        ),
    ),
    TablePlan(
        "9",
        2,
        ({"waakye": 2, "malta": 2},),
        (
            Tender(CASH, 5000, voided=True),  # keyed twice by mistake, voided while part-paid
            Tender(CASH, 5000),
            Tender(CARD, reference="CARD-9002"),
        ),
    ),
    TablePlan(
        "10",
        3,
        ({"jollof": 3}, {"kelewele": 2}),
        (Tender(CASH),),
        comp_round=1,  # the kelewele goes on the house: 5000
    ),
    TablePlan(
        "11",
        2,
        ({"jollof": 2},),
        (Tender(CASH),),
        cancelled_round={"club": 2},  # pulled before the kitchen saw it: not a variance
    ),
    TablePlan("12", 4, ({"banku": 2}, {"waakye": 2}), (Tender(BANK, reference="BT-4410"),)),
    # ------------------------------------------------ till 1: Kwesi's shift, tables 13–20
    TablePlan(
        "13",
        8,
        ({"jollof": 8}, {"club": 8}),
        (Tender(MOMO_MTN, reference="MP-BIGTABLE"), Tender(CASH)),
        till=1,
        reopen_round={"club": 4},  # "one more round" after the bill was settled
        reopen_after_tender=1,
    ),
    TablePlan(
        "14",
        2,
        ({"waakye": 2},),
        (Tender(CASH, tendered_pesewas=15000),),  # 40.00 change out of the drawer
        till=1,
        clear_table=True,
    ),
    TablePlan(
        "15",
        3,
        ({"jollof": 2}, {"kelewele": 1}),
        (Tender(MOMO_AT, reference="AT-7781"),),
        till=1,
    ),
    TablePlan("16", 2, ({"banku": 1, "malta": 1},), (Tender(CARD),), till=1, clear_table=True),
    TablePlan(
        "Terrace 1",
        4,
        ({"jollof": 4},),
        (Tender(CASH, 20000), Tender(MOMO_MTN, reference="MP-TERRACE")),
        till=1,
    ),
    TablePlan("Terrace 2", 2, ({"club": 4},), (Tender(CASH),), till=1, clear_table=True),
    TablePlan(
        "Terrace 3",
        6,
        ({"banku": 6}, {"club": 6}),
        (Tender(CASH, 30000),),  # part-paid and still sitting there at close
        till=1,
    ),
    TablePlan("Terrace 4", 2, ({"jollof": 1, "malta": 2},), (), till=1),  # not paid at all
)


# ---------------------------------------------------------------- what the plan adds up to


@dataclass(frozen=True)
class TenderOutcome:
    """One tender, resolved against the bill as it stood at that moment."""

    method: str
    amount_pesewas: int
    tendered_pesewas: int | None
    change_pesewas: int | None
    reference: str | None
    balance_after_pesewas: int
    settles: bool
    voided: bool
    void_reason: str | None
    reopens_on_void: bool


@dataclass(frozen=True)
class TableOutcome:
    plan: TablePlan
    bill_total_pesewas: int
    paid_pesewas: int
    settled: bool
    discount_pesewas: int
    comp_pesewas: int
    voided_order_pesewas: int  # voided after acknowledgement: a variance the owner must see
    cancelled_order_pesewas: int  # voided before acknowledgement: not a variance
    tenders: tuple[TenderOutcome, ...]

    @property
    def balance_pesewas(self) -> int:
        return self.bill_total_pesewas - self.paid_pesewas


@dataclass(frozen=True)
class ShiftTotals:
    cashier_name: str
    opening_float_pesewas: int
    cash_payments_pesewas: int
    paid_in_pesewas: int
    paid_out_pesewas: int
    expected_cash_pesewas: int
    declared_cash_pesewas: int
    variance_pesewas: int
    money_taken_pesewas: int
    totals_by_method: dict[str, int]
    payment_count: int


@dataclass(frozen=True)
class ServiceTotals:
    """Every figure a report should be able to reproduce. Integer pesewas, no rounding anywhere."""

    money_taken_pesewas: int
    money_taken_by_method: dict[str, int]
    covers: int  # Σ party_size of settled bills
    bills_settled: int
    bills_open: int
    bills_closed: int
    settled_bill_total_pesewas: int
    open_bill_total_pesewas: int
    outstanding_pesewas: int
    discounts_pesewas: int
    comps_pesewas: int
    voided_orders_pesewas: int  # after acknowledgement
    cancelled_orders_pesewas: int  # before acknowledgement
    voided_payments_pesewas: int
    payment_voids: int
    sessions_reopened: int  # a payment void on a settled bill reopens one too
    manager_reopens: int
    item_value_pesewas: dict[str, int]  # menu item name → value of non-voided lines
    shifts: tuple[ShiftTotals, ...]
    tables: tuple[TableOutcome, ...] = field(repr=False, default=())

    def table(self, number: str) -> TableOutcome:
        return next(t for t in self.tables if t.plan.number == number)


def round_total_pesewas(round_: Round) -> int:
    return sum(MENU[key].price_pesewas * quantity for key, quantity in round_.items())


def _simulate(plan: TablePlan) -> TableOutcome:
    """The hand calculation: what this table owes, pays and leaves behind. No database."""
    round_totals = [round_total_pesewas(r) for r in plan.rounds]
    discount = (
        apply_percent_discount(round_totals[0], plan.discount_percent)
        if plan.discount_percent
        else 0
    )
    comp = round_totals[plan.comp_round] if plan.comp_round is not None else 0
    bill = sum(round_totals) - discount - comp

    paid = 0
    tenders: list[TenderOutcome] = []
    for index, tender in enumerate(plan.tenders):
        if plan.reopen_round is not None and index == plan.reopen_after_tender:
            bill += round_total_pesewas(plan.reopen_round)

        amount = tender.amount_pesewas if tender.amount_pesewas is not None else bill - paid
        paid += amount
        balance_after = bill - paid
        settled_now = balance_after == 0
        tendered = change = None
        if tender.method == CASH:
            tendered = tender.tendered_pesewas if tender.tendered_pesewas is not None else amount
            change = tendered - amount
        if tender.voided:
            paid -= amount
        tenders.append(
            TenderOutcome(
                method=str(tender.method),
                amount_pesewas=amount,
                tendered_pesewas=tendered,
                change_pesewas=change,
                reference=normalise_reference(tender.reference),
                balance_after_pesewas=balance_after,
                settles=settled_now,
                voided=tender.voided,
                void_reason=tender.void_reason if tender.voided else None,
                # Taking money off a settled bill puts it back in play.
                reopens_on_void=tender.voided and settled_now,
            )
        )

    return TableOutcome(
        plan=plan,
        bill_total_pesewas=bill,
        paid_pesewas=paid,
        settled=bill - paid == 0,
        discount_pesewas=discount,
        comp_pesewas=comp,
        voided_order_pesewas=(round_total_pesewas(plan.voided_round) if plan.voided_round else 0),
        cancelled_order_pesewas=(
            round_total_pesewas(plan.cancelled_round) if plan.cancelled_round else 0
        ),
        tenders=tuple(tenders),
    )


def _item_value(outcomes: tuple[TableOutcome, ...]) -> dict[str, int]:
    """Value of every line that survived the service, open bills included. Snapshots, not bills."""
    value: dict[str, int] = {}
    for outcome in outcomes:
        rounds = list(outcome.plan.rounds)
        if outcome.plan.reopen_round is not None:
            rounds.append(outcome.plan.reopen_round)
        for round_ in rounds:
            for key, quantity in round_.items():
                spec = MENU[key]
                value[spec.name] = value.get(spec.name, 0) + spec.price_pesewas * quantity
    return dict(sorted(value.items(), key=lambda kv: (-kv[1], kv[0])))


def _shift_totals(index: int, outcomes: tuple[TableOutcome, ...]) -> ShiftTotals:
    plan = SHIFT_PLAN[index]
    by_method: dict[str, int] = {}
    payment_count = 0
    for outcome in outcomes:
        if outcome.plan.till != index:
            continue
        for tender in outcome.tenders:
            if tender.voided:
                continue
            by_method[tender.method] = by_method.get(tender.method, 0) + tender.amount_pesewas
            payment_count += 1

    paid_in = sum(m.amount_pesewas for m in plan.movements if m.kind == DrawerMovement.Kind.PAID_IN)
    paid_out = sum(
        m.amount_pesewas for m in plan.movements if m.kind == DrawerMovement.Kind.PAID_OUT
    )
    cash = by_method.get(str(CASH), 0)
    expected = plan.opening_float_pesewas + cash - paid_out + paid_in
    return ShiftTotals(
        cashier_name=plan.cashier_name,
        opening_float_pesewas=plan.opening_float_pesewas,
        cash_payments_pesewas=cash,
        paid_in_pesewas=paid_in,
        paid_out_pesewas=paid_out,
        expected_cash_pesewas=expected,
        declared_cash_pesewas=expected + plan.declared_variance_pesewas,
        variance_pesewas=plan.declared_variance_pesewas,
        money_taken_pesewas=sum(by_method.values()),
        totals_by_method=by_method,
        payment_count=payment_count,
    )


def expected_totals() -> ServiceTotals:
    """Fold `TABLE_PLAN` and `SHIFT_PLAN` into the figures every report must reproduce."""
    outcomes = tuple(_simulate(plan) for plan in TABLE_PLAN)
    settled = [o for o in outcomes if o.settled]
    still_owing = [o for o in outcomes if not o.settled]
    by_method: dict[str, int] = {}
    for outcome in outcomes:
        for tender in outcome.tenders:
            if tender.voided:
                continue
            by_method[tender.method] = by_method.get(tender.method, 0) + tender.amount_pesewas

    voided_tenders = [t for o in outcomes for t in o.tenders if t.voided]
    return ServiceTotals(
        money_taken_pesewas=sum(by_method.values()),
        money_taken_by_method=by_method,
        covers=sum(o.plan.party_size for o in settled),
        bills_settled=len(settled),
        bills_open=len(still_owing),
        bills_closed=sum(1 for o in outcomes if o.plan.clear_table),
        settled_bill_total_pesewas=sum(o.bill_total_pesewas for o in settled),
        open_bill_total_pesewas=sum(o.bill_total_pesewas for o in still_owing),
        outstanding_pesewas=sum(o.balance_pesewas for o in still_owing),
        discounts_pesewas=sum(o.discount_pesewas for o in outcomes),
        comps_pesewas=sum(o.comp_pesewas for o in outcomes),
        voided_orders_pesewas=sum(o.voided_order_pesewas for o in outcomes),
        cancelled_orders_pesewas=sum(o.cancelled_order_pesewas for o in outcomes),
        voided_payments_pesewas=sum(t.amount_pesewas for t in voided_tenders),
        payment_voids=len(voided_tenders),
        sessions_reopened=sum(1 for o in outcomes if o.plan.reopen_round is not None)
        + sum(1 for t in voided_tenders if t.reopens_on_void),
        manager_reopens=sum(1 for o in outcomes if o.plan.reopen_round is not None),
        item_value_pesewas=_item_value(outcomes),
        shifts=tuple(_shift_totals(i, outcomes) for i in range(len(SHIFT_PLAN))),
        tables=outcomes,
    )


EXPECTED: ServiceTotals = expected_totals()


# ---------------------------------------------------------------- driving the service


class Auth(NamedTuple):
    """Device token, staff JWT, who it is, and what they are holding."""

    device_token: str
    jwt: str
    staff: Staff
    device: Device


@dataclass(frozen=True)
class Cast:
    api: APIClient
    restaurant: Restaurant
    device: Device
    manager: Auth  # the duty manager: authorises every override in the script
    cashiers: tuple[Auth, ...]
    waiters: tuple[Auth, ...]
    kitchen: Auth
    menu: dict[str, MenuItem]
    tables: dict[str, Table]


def headers(auth: Auth, idempotency_key: str | None = None) -> dict[str, str]:
    return {
        "HTTP_X_DEVICE_TOKEN": auth.device_token,
        "HTTP_AUTHORIZATION": f"Bearer {auth.jwt}",
        "HTTP_IDEMPOTENCY_KEY": idempotency_key or str(uuid7()),
    }


def _post(cast: Cast, path: str, body: dict[str, Any], auth: Auth, expected: int = 200) -> Any:
    response = cast.api.post(path, body, format="json", **headers(auth))
    if response.status_code != expected:
        raise AssertionError(
            f"POST {path} returned {response.status_code}, expected {expected}: "
            f"{getattr(response, 'data', None)}"
        )
    return response


def _authorisation(cast: Cast, purpose: AuthorisationPurpose, reason_code: str) -> dict[str, str]:
    """A manager's PIN, already verified — the block a command carrying an override must include."""
    token = issue_authorisation(
        staff_id=cast.manager.staff.id, device_id=cast.device.id, purpose=purpose
    )
    return {"token": token, "reason_code": reason_code}


def _build_cast(restaurant: Restaurant, api: APIClient) -> Cast:
    pin = hash_pin("1234")
    # One enrolled device hosts every role: the till, the tablet and the kitchen screen in one.
    token, token_hash = new_device_token()
    device = Device.objects.create(
        label="RENZY till",
        token_hash=token_hash,
        allowed_roles=["WAITER", "KITCHEN", "CASHIER", "MANAGER"],
        enrolled_at=timezone.now(),
    )

    def staff_auth(full_name: str, role: str) -> Auth:
        staff = Staff.objects.create(full_name=full_name, role=role, pin_hash=pin)
        jwt = issue_staff_token(
            staff_id=staff.id, role=role, restaurant_id=restaurant.id, device_id=device.id
        )
        return Auth(token, jwt, staff, device)

    manager = staff_auth("Nana Mensah", "MANAGER")
    cashiers = tuple(staff_auth(shift.cashier_name, "CASHIER") for shift in SHIFT_PLAN)
    waiters = (staff_auth("Kofi Antwi", "WAITER"), staff_auth("Adwoa Sarpong", "WAITER"))
    kitchen = staff_auth("Yaw Boateng", "KITCHEN")

    category = MenuCategory.objects.create(name="Service")
    menu = {
        key: MenuItem.objects.create(
            category=category,
            name=spec.name,
            price_pesewas=spec.price_pesewas,
            prep_station=spec.station,
        )
        for key, spec in MENU.items()
    }
    tables = {
        plan.number: Table.objects.create(
            number=plan.number, qr_token=Table.new_qr_token(), seats=plan.party_size
        )
        for plan in TABLE_PLAN
    }
    return Cast(
        api=api,
        restaurant=restaurant,
        device=device,
        manager=manager,
        cashiers=cashiers,
        waiters=waiters,
        kitchen=kitchen,
        menu=menu,
        tables=tables,
    )


# ---------------------------------------------------------------- what the script produced


@dataclass(frozen=True)
class ScriptedTable:
    number: str
    session_id: str
    party_size: int
    bill_total_pesewas: int
    paid_pesewas: int
    settled: bool
    closed: bool
    order_ids: tuple[str, ...]
    payment_ids: tuple[str, ...]
    voided_payment_ids: tuple[str, ...]


@dataclass(frozen=True)
class ScriptedShift:
    id: str
    cashier_id: str
    cashier_name: str
    totals: ShiftTotals


@dataclass(frozen=True)
class ScriptedService:
    restaurant_id: str
    cast: Cast
    tables: tuple[ScriptedTable, ...]
    shifts: tuple[ScriptedShift, ...]
    totals: ServiceTotals = EXPECTED

    def table(self, number: str) -> ScriptedTable:
        return next(t for t in self.tables if t.number == number)

    @property
    def open_tables(self) -> tuple[ScriptedTable, ...]:
        return tuple(t for t in self.tables if not t.settled)


def _serve_round(cast: Cast, session_id: str, round_: Round, waiter: Auth) -> str:
    """Waiter sends it, the kitchen cooks it, the waiter serves it. Drinks skip the kitchen ack."""
    order_id = _open_round(cast, session_id, round_, waiter)
    drinks_only = all(MENU[key].station == PrepStation.BAR for key in round_)
    steps: list[tuple[str, Auth]] = [("submit", waiter)]
    if not drinks_only:
        steps.append(("ack", cast.kitchen))
    steps += [("ready", cast.kitchen), ("serve", waiter)]
    for step, auth in steps:
        _post(cast, f"/api/v1/orders/{order_id}/{step}", {}, auth)
    return order_id


def _open_round(cast: Cast, session_id: str, round_: Round, waiter: Auth) -> str:
    order_id = str(uuid7())
    _post(cast, "/api/v1/orders", {"id": order_id, "session_id": session_id}, waiter, 201)
    for key, quantity in round_.items():
        _post(
            cast,
            f"/api/v1/orders/{order_id}/items",
            {
                "id": str(uuid7()),
                "menu_item_id": str(cast.menu[key].id),
                "quantity": quantity,
                "modifier_ids": [],
            },
            waiter,
        )
    return order_id


def _cancel_round(cast: Cast, session_id: str, round_: Round, waiter: Auth) -> str:
    """Pulled before the kitchen acknowledged it: no PIN needed, nothing was cooked."""
    order_id = _open_round(cast, session_id, round_, waiter)
    _post(cast, f"/api/v1/orders/{order_id}/submit", {}, waiter)
    _post(cast, f"/api/v1/orders/{order_id}/void", {"reason_code": CANCEL_REASON}, waiter)
    return order_id


def _void_cooked_round(cast: Cast, session_id: str, round_: Round, waiter: Auth) -> str:
    """Acknowledged, then voided: manager PIN, reason code, and a variance the owner must see."""
    order_id = _open_round(cast, session_id, round_, waiter)
    _post(cast, f"/api/v1/orders/{order_id}/submit", {}, waiter)
    _post(cast, f"/api/v1/orders/{order_id}/ack", {}, cast.kitchen)
    _post(
        cast,
        f"/api/v1/orders/{order_id}/void",
        {
            "reason_code": VOID_AFTER_ACK_REASON,
            "authorisation": _authorisation(
                cast, AuthorisationPurpose.VOID_AFTER_ACK, VOID_AFTER_ACK_REASON
            ),
        },
        waiter,
    )
    return order_id


def _run_table(cast: Cast, plan: TablePlan, outcome: TableOutcome, waiter: Auth) -> ScriptedTable:
    cashier = cast.cashiers[plan.till]
    session_id = str(uuid7())
    _post(
        cast,
        "/api/v1/sessions",
        {
            "id": session_id,
            "table_id": str(cast.tables[plan.number].id),
            "party_size": plan.party_size,
        },
        waiter,
        201,
    )

    order_ids = [_serve_round(cast, session_id, round_, waiter) for round_ in plan.rounds]
    if plan.cancelled_round is not None:
        order_ids.append(_cancel_round(cast, session_id, plan.cancelled_round, waiter))
    if plan.voided_round is not None:
        order_ids.append(_void_cooked_round(cast, session_id, plan.voided_round, waiter))

    if plan.discount_percent:
        # The cashier applies it; the manager authorises it. Both names land on the event.
        _post(
            cast,
            f"/api/v1/orders/{order_ids[0]}/discount",
            {
                "kind": "PERCENT",
                "value": plan.discount_percent,
                "authorisation": _authorisation(
                    cast, AuthorisationPurpose.DISCOUNT, DISCOUNT_REASON
                ),
            },
            cashier,
        )
    if plan.comp_round is not None:
        # Only a manager may comp, and the comp still carries a PIN and a reason code.
        _post(
            cast,
            f"/api/v1/orders/{order_ids[plan.comp_round]}/comp",
            {"authorisation": _authorisation(cast, AuthorisationPurpose.COMP, COMP_REASON)},
            cast.manager,
        )

    payment_ids: list[str] = []
    voided_payment_ids: list[str] = []
    for index, tender in enumerate(outcome.tenders):
        if plan.reopen_round is not None and index == plan.reopen_after_tender:
            _reopen(cast, session_id, cashier)
            order_ids.append(_serve_round(cast, session_id, plan.reopen_round, waiter))

        payment_id = _pay(cast, session_id, tender, cashier)
        if tender.voided:
            voided_payment_ids.append(payment_id)
            _void_payment(cast, payment_id, tender, cashier)
        else:
            payment_ids.append(payment_id)

    if plan.clear_table:
        _post(cast, f"/api/v1/sessions/{session_id}/close", {}, cashier)

    session = TableSession.objects.get(pk=session_id)
    _expect(
        (int(session.bill_total_pesewas), int(session.paid_pesewas)),
        (outcome.bill_total_pesewas, outcome.paid_pesewas),
        f"table {plan.number} bill",
    )
    _expect(session.settled_at is not None, outcome.settled, f"table {plan.number} settled")
    return ScriptedTable(
        number=plan.number,
        session_id=session_id,
        party_size=plan.party_size,
        bill_total_pesewas=int(session.bill_total_pesewas),
        paid_pesewas=int(session.paid_pesewas),
        settled=session.settled_at is not None,
        closed=session.closed_at is not None,
        order_ids=tuple(order_ids),
        payment_ids=tuple(payment_ids),
        voided_payment_ids=tuple(voided_payment_ids),
    )


def _pay(cast: Cast, session_id: str, tender: TenderOutcome, cashier: Auth) -> str:
    body: dict[str, Any] = {
        "id": str(uuid7()),
        "method": tender.method,
        "amount_pesewas": tender.amount_pesewas,
    }
    if tender.tendered_pesewas is not None:
        body["tendered_pesewas"] = tender.tendered_pesewas
    if tender.reference is not None:
        body["external_reference"] = tender.reference
    data = _post(cast, f"/api/v1/sessions/{session_id}/payments", body, cashier, 201).data
    _expect(data["balance_pesewas"], tender.balance_after_pesewas, "balance after payment")
    _expect(data["settled"], tender.settles, "settled by this payment")
    _expect(data["change_pesewas"], tender.change_pesewas, "change")
    return str(data["id"])


def _void_payment(cast: Cast, payment_id: str, tender: TenderOutcome, cashier: Auth) -> None:
    data = _post(
        cast,
        f"/api/v1/payments/{payment_id}/void",
        {
            "authorisation": _authorisation(
                cast, AuthorisationPurpose.PAYMENT_VOID, tender.void_reason or "WRONG_AMOUNT"
            )
        },
        cashier,
    ).data
    _expect(data["session_reopened"], tender.reopens_on_void, "session reopened by the void")


def _reopen(cast: Cast, session_id: str, cashier: Auth) -> None:
    _post(
        cast,
        f"/api/v1/sessions/{session_id}/reopen",
        {"authorisation": _authorisation(cast, AuthorisationPurpose.REOPEN, REOPEN_REASON)},
        cashier,
    )


def _open_shift(cast: Cast, index: int) -> str:
    shift_id = str(uuid7())
    _post(
        cast,
        "/api/v1/shifts",
        {
            "id": shift_id,
            "opening_float_pesewas": SHIFT_PLAN[index].opening_float_pesewas,
        },
        cast.cashiers[index],
        201,
    )
    return shift_id


def _close_shift(cast: Cast, index: int, shift_id: str) -> None:
    totals = EXPECTED.shifts[index]
    for movement in SHIFT_PLAN[index].movements:
        _post(
            cast,
            f"/api/v1/shifts/{shift_id}/movements",
            {
                "kind": movement.kind,
                "amount_pesewas": movement.amount_pesewas,
                "note": movement.note,
                "authorisation": _authorisation(
                    cast, AuthorisationPurpose.DRAWER_MOVEMENT, movement.reason_code
                ),
            },
            cast.cashiers[index],
            201,
        )

    data = _post(
        cast,
        f"/api/v1/shifts/{shift_id}/close",
        {"declared_cash_pesewas": totals.declared_cash_pesewas},
        cast.cashiers[index],
    ).data
    _expect(data["cash_payments_pesewas"], totals.cash_payments_pesewas, "shift cash")
    _expect(data["expected_cash_pesewas"], totals.expected_cash_pesewas, "shift expected cash")
    _expect(data["variance_pesewas"], totals.variance_pesewas, "shift variance")


def _expect(actual: Any, expected: Any, what: str) -> None:
    if actual != expected:
        raise AssertionError(f"{what}: got {actual}, the plan says {expected}")


def run_service_script(restaurant: Restaurant, *, api: APIClient | None = None) -> ScriptedService:
    """
    Run the whole service. Asserts as it goes that the API agrees with `EXPECTED`, so a caller that
    only needs the data can trust it, and a caller that is testing a report can assert against
    `EXPECTED` without repeating the arithmetic.
    """
    cast = _build_cast(restaurant, api or APIClient())
    tables: list[ScriptedTable] = []
    shifts: list[ScriptedShift] = []

    for index, shift_plan in enumerate(SHIFT_PLAN):
        shift_id = _open_shift(cast, index)
        for position, plan in enumerate(TABLE_PLAN):
            if plan.till != index:
                continue
            waiter = cast.waiters[position % len(cast.waiters)]
            tables.append(_run_table(cast, plan, EXPECTED.tables[position], waiter))
        _close_shift(cast, index, shift_id)
        shifts.append(
            ScriptedShift(
                id=shift_id,
                cashier_id=str(cast.cashiers[index].staff.id),
                cashier_name=shift_plan.cashier_name,
                totals=EXPECTED.shifts[index],
            )
        )

    return ScriptedService(
        restaurant_id=str(restaurant.id),
        cast=cast,
        tables=tuple(tables),
        shifts=tuple(shifts),
    )


@pytest.fixture
def scripted_service(restaurant: Restaurant) -> ScriptedService:
    """The whole service, run once. Import this into a conftest to use it in another app's tests."""
    return run_service_script(restaurant)


__all__ = [
    "EXPECTED",
    "MENU",
    "SHIFT_PLAN",
    "TABLE_PLAN",
    "Auth",
    "Cast",
    "ScriptedService",
    "ScriptedShift",
    "ScriptedTable",
    "ServiceTotals",
    "ShiftTotals",
    "TableOutcome",
    "TablePlan",
    "Tender",
    "TenderOutcome",
    "expected_totals",
    "headers",
    "round_total_pesewas",
    "run_service_script",
    "scripted_service",
]
