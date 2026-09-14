"""
Projection registry. Apps register handlers with @project(EventType.X); the command runner calls
apply() for every appended event inside the command transaction, and rebuild_projections replays
the whole stream through the same handlers. Handlers must be deterministic and must not read the clock.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import TYPE_CHECKING

from django.db import models

if TYPE_CHECKING:
    from apps.orders.models import OrderEvent

Handler = Callable[["OrderEvent"], None]

_handlers: dict[str, list[Handler]] = defaultdict(list)
_projection_models: list[type[models.Model]] = []


def project(*event_types: str) -> Callable[[Handler], Handler]:
    def register(fn: Handler) -> Handler:
        for et in event_types:
            _handlers[str(et)].append(fn)
        return fn

    return register


def register_projection_model(model: type[models.Model]) -> type[models.Model]:
    """Mark a table as derived from the event stream, so rebuild/verify know to clear and compare it."""
    if model not in _projection_models:
        _projection_models.append(model)
    return model


def projection_models() -> list[type[models.Model]]:
    return list(_projection_models)


def handlers_for(event_type: str) -> list[Handler]:
    return list(_handlers.get(event_type, ()))


def apply(event: OrderEvent) -> None:
    for handler in _handlers.get(event.event_type, ()):
        handler(event)
