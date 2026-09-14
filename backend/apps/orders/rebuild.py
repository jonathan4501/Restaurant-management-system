"""
Rebuild and verify projections from the event stream.

rebuild(restaurant_id): inside a transaction, clear every registered projection table for the
restaurant and replay all events in seq order through the projector registry. This is the one
place a projection table is cleared: projections are derived data, not facts.

verify(restaurant_id): snapshot projections → rebuild inside a savepoint → snapshot again →
roll back → diff. Returns the differences; empty means the projections are faithful.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.db import models, transaction

from apps.core import projections
from apps.core.tenancy import restaurant_context

from .models import OrderEvent


def _rows(model: type[models.Model], restaurant_id: uuid.UUID) -> dict[str, dict[str, Any]]:
    fields = [f.attname for f in model._meta.concrete_fields]
    out: dict[str, dict[str, Any]] = {}
    for row in model.objects.unscoped().filter(restaurant_id=restaurant_id).values(*fields):  # type: ignore[attr-defined]
        out[str(row["id"])] = {
            k: (str(v) if isinstance(v, uuid.UUID) else v) for k, v in row.items()
        }
    return out


def rebuild(restaurant_id: uuid.UUID) -> int:
    with transaction.atomic(), restaurant_context(restaurant_id):
        # Clear children before parents; registration order is parent-first, so reverse it.
        for model in reversed(projections.projection_models()):
            model.objects.unscoped().filter(restaurant_id=restaurant_id).delete()  # type: ignore[attr-defined]
        count = 0
        for event in (
            OrderEvent.objects.unscoped()
            .filter(restaurant_id=restaurant_id)
            .order_by("seq")
            .iterator()
        ):
            projections.apply(event)
            count += 1
        return count


def verify(restaurant_id: uuid.UUID) -> dict[str, dict[str, Any]]:
    before = {m._meta.db_table: _rows(m, restaurant_id) for m in projections.projection_models()}
    diffs: dict[str, dict[str, Any]] = {}

    class _Rollback(Exception):
        pass

    try:
        with transaction.atomic():
            rebuild(restaurant_id)
            after = {
                m._meta.db_table: _rows(m, restaurant_id) for m in projections.projection_models()
            }
            for table, rows_before in before.items():
                rows_after = after[table]
                table_diff: dict[str, Any] = {}
                for pk in set(rows_before) | set(rows_after):
                    b, a = rows_before.get(pk), rows_after.get(pk)
                    if b != a:
                        table_diff[pk] = {"stored": b, "rebuilt": a}
                if table_diff:
                    diffs[table] = table_diff
            raise _Rollback
    except _Rollback:
        pass
    return diffs
