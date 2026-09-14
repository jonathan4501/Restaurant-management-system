"""
The rules that are expensive to break, checked mechanically. If one of these fails, the fix is in
the code that broke it — not in this file.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from django.apps import apps as django_apps
from django.db import DatabaseError, models, transaction
from django.urls import URLPattern, URLResolver, get_resolver

from apps.core.commands import CommandOutcome, EventDraft, run_command
from apps.core.money import PesewasField
from apps.core.roles import AggregateType
from apps.core.tenancy import TenantModel
from apps.core.uuid7 import uuid7
from apps.orders.events import EventType
from apps.orders.models import OrderEvent

APPS_DIR = Path(__file__).resolve().parents[2]


def our_models() -> list[type[models.Model]]:
    return [m for m in django_apps.get_models() if m.__module__.startswith("apps.")]


# 1. Money is an integer number of pesewas.
def test_no_float_or_decimal_fields_anywhere() -> None:
    offenders = [
        f"{m.__name__}.{f.name}"
        for m in our_models()
        for f in m._meta.get_fields()
        if isinstance(f, models.FloatField | models.DecimalField)
    ]
    assert offenders == [], f"Money is integer pesewas. Float/Decimal fields found: {offenders}"


def test_every_money_column_is_a_pesewas_field() -> None:
    """A column named *_pesewas must use PesewasField so the invariant is greppable and typed."""
    offenders = [
        f"{m.__name__}.{f.name}"
        for m in our_models()
        for f in m._meta.get_fields()
        if getattr(f, "name", "").endswith("_pesewas")
        and not isinstance(f, PesewasField | models.GeneratedField)
        and f.name != "cash_variance_pesewas"  # may be negative; plain IntegerField by design
    ]
    assert offenders == [], offenders


# 7. restaurant_id on every table.
def test_every_model_has_restaurant() -> None:
    exempt = {"accounts.Restaurant"}
    offenders = [
        m._meta.label
        for m in our_models()
        if m._meta.label not in exempt and not issubclass(m, TenantModel)
    ]
    assert offenders == [], f"Every table carries restaurant_id via TenantModel: {offenders}"


# 7b. unscoped() only where the docs allow it.
UNSCOPED_ALLOW_LIST = {
    "apps/core/tenancy.py",  # defines it
    "apps/core/idempotency.py",
    "apps/core/commands.py",
    "apps/core/admin.py",
    "apps/core/tests/test_invariants.py",
    "apps/accounts/principals.py",
    "apps/accounts/management/commands/set_pin.py",
    "apps/orders/rebuild.py",
}


def test_unscoped_is_only_used_where_allowed() -> None:
    pattern = re.compile(r"\.unscoped\(\)")
    offenders = []
    for path in APPS_DIR.glob("**/*.py"):
        rel = path.relative_to(APPS_DIR.parent).as_posix()
        if "/migrations/" in rel or rel.endswith("/projector.py") or "/tests/" in rel:
            continue  # projectors and tests filter by restaurant_id explicitly
        if pattern.search(path.read_text(encoding="utf-8")) and rel not in UNSCOPED_ALLOW_LIST:
            offenders.append(rel)
    assert offenders == [], f"unscoped() outside the allow-list: {offenders}"


# 5. Every write is idempotent: every POST route is a CommandView (or explicitly listed).
POST_ALLOW_LIST: set[str] = set()  # add auth endpoints here with a justification when WS01 lands


def _walk(patterns: list, prefix: str = "") -> list[tuple[str, object]]:
    out = []
    for p in patterns:
        if isinstance(p, URLResolver):
            out.extend(_walk(p.url_patterns, prefix + str(p.pattern)))
        elif isinstance(p, URLPattern):
            out.append((prefix + str(p.pattern), p.callback))
    return out


def test_every_post_route_is_a_command_view() -> None:
    from apps.core.views import CommandView

    offenders = []
    for route, callback in _walk(get_resolver().url_patterns):
        if not route.startswith("api/v1/"):
            continue
        view_class = getattr(callback, "view_class", None) or getattr(callback, "cls", None)
        if view_class is None:
            continue
        if (
            hasattr(view_class, "post")
            and not issubclass(view_class, CommandView)
            and route not in POST_ALLOW_LIST
        ):
            offenders.append(route)
    assert (
        offenders == []
    ), f"POST routes must extend CommandView (Idempotency-Key by construction): {offenders}"


# 3. order_events is append-only at the database level.
@pytest.mark.django_db(transaction=True)
def test_order_events_rejects_update_and_delete(restaurant, make_ctx) -> None:
    def handler(ctx):
        return CommandOutcome(
            events=[
                EventDraft(
                    AggregateType.SESSION, uuid7(), EventType.SESSION_OPENED, {"table_number": "1"}
                )
            ],
            response={},
        )

    run_command(make_ctx(), handler)
    event = OrderEvent.objects.get()

    with pytest.raises(DatabaseError, match="append-only"), transaction.atomic():
        OrderEvent.objects.unscoped().filter(pk=event.pk).update(payload={"tampered": True})

    with pytest.raises(DatabaseError, match="append-only"), transaction.atomic():
        OrderEvent.objects.unscoped().filter(pk=event.pk).delete()

    with pytest.raises(RuntimeError, match="append-only"):
        event.payload = {"tampered": True}
        event.save()

    assert OrderEvent.objects.get().payload == {"table_number": "1"}


# Event vocabulary and payload classes stay in step.
def test_every_event_type_has_a_payload_class_and_an_aggregate() -> None:
    from apps.orders.events import AGGREGATE_OF, PAYLOADS

    missing_payload = [e for e in EventType if e not in PAYLOADS]
    missing_aggregate = [e for e in EventType if e not in AGGREGATE_OF]
    assert missing_payload == [], missing_payload
    assert missing_aggregate == [], missing_aggregate
