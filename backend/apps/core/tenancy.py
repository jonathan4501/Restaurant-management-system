"""
restaurant_id on every table and every query — enforced by construction, not by memory.

The current restaurant lives in a contextvar set by RequestContextMiddleware (HTTP), by
restaurant_context() (Celery tasks, management commands, tests), or by the SSE view. TenantManager
refuses to run a query when no restaurant is set; that is a programming error, not a data leak.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from django.db import models

from .uuid7 import uuid7

_current_restaurant: ContextVar[uuid.UUID | None] = ContextVar("current_restaurant", default=None)


class TenantContextMissing(RuntimeError):
    """A tenant-scoped query ran with no restaurant in context."""


def get_current_restaurant() -> uuid.UUID | None:
    return _current_restaurant.get()


def require_current_restaurant() -> uuid.UUID:
    rid = _current_restaurant.get()
    if rid is None:
        raise TenantContextMissing(
            "No restaurant in context. Wrap the call in restaurant_context(restaurant_id) "
            "or use Model.objects.unscoped() if you really mean every tenant."
        )
    return rid


def set_current_restaurant(restaurant_id: uuid.UUID | None) -> object:
    return _current_restaurant.set(restaurant_id)


def reset_current_restaurant(token: object) -> None:
    _current_restaurant.reset(token)  # type: ignore[arg-type]


@contextmanager
def restaurant_context(restaurant_id: uuid.UUID) -> Iterator[None]:
    token = _current_restaurant.set(restaurant_id)
    try:
        yield
    finally:
        _current_restaurant.reset(token)


class TenantQuerySet(models.QuerySet):
    pass


class TenantManager(models.Manager):
    """Filters every query by the restaurant in context. `.unscoped()` is the only way around it."""

    use_in_migrations = False

    def get_queryset(self) -> models.QuerySet:
        rid = require_current_restaurant()
        return super().get_queryset().filter(restaurant_id=rid)

    def unscoped(self) -> models.QuerySet:
        """Every tenant. Allowed only in migrations, rebuilds, and the allow-list in test_invariants."""
        return super().get_queryset()

    def create(self, **kwargs: object) -> Any:
        kwargs.setdefault("restaurant_id", require_current_restaurant())
        return super().create(**kwargs)


class TenantModel(models.Model):
    """Base for every table that belongs to a restaurant — which is every table except restaurants."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    restaurant = models.ForeignKey(
        "accounts.Restaurant", on_delete=models.PROTECT, related_name="+", editable=False
    )

    objects = TenantManager()

    class Meta:
        abstract = True

    def save(self, *args: object, **kwargs: object) -> None:
        if self.restaurant_id is None:
            self.restaurant_id = require_current_restaurant()
        super().save(*args, **kwargs)  # type: ignore[arg-type]
