"""Invalidate the GET /menu Redis cache when admin (or any ORM write) touches menu rows."""

from __future__ import annotations

from typing import Any

from django.db.models.signals import post_delete, post_save

from apps.menu.cache import invalidate_menu_cache
from apps.menu.models import MenuCategory, MenuItem, MenuItemModifierGroup, Modifier, ModifierGroup


def _invalidate(sender: type, instance: Any, **kwargs: Any) -> None:
    rid = getattr(instance, "restaurant_id", None)
    if rid is not None:
        invalidate_menu_cache(rid)


def connect_signals() -> None:
    for model in (MenuCategory, MenuItem, ModifierGroup, Modifier, MenuItemModifierGroup):
        post_save.connect(
            _invalidate, sender=model, dispatch_uid=f"menu.cache.save.{model.__name__}"
        )
        post_delete.connect(
            _invalidate, sender=model, dispatch_uid=f"menu.cache.delete.{model.__name__}"
        )


connect_signals()
