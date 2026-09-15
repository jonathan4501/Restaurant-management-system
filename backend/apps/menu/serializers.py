"""Serialize the full active menu tree for GET /menu."""

from __future__ import annotations

from typing import Any

from apps.menu.models import MenuCategory, MenuItem, Modifier, ModifierGroup


def _image_url(item: MenuItem) -> str | None:
    if not item.image:
        return None
    try:
        return item.image.url
    except ValueError:
        return None


def _modifier_dict(mod: Modifier) -> dict[str, Any]:
    return {
        "id": str(mod.id),
        "name": mod.name,
        "price_pesewas": mod.price_pesewas,
        "is_default": mod.is_default,
        "is_available": mod.is_available,
        "sort_order": mod.sort_order,
    }


def _group_dict(group: ModifierGroup, link_sort: int) -> dict[str, Any]:
    modifiers = [_modifier_dict(m) for m in group.modifiers.all() if m.is_active]
    return {
        "id": str(group.id),
        "name": group.name,
        "selection": group.selection,
        "is_required": group.is_required,
        "sort_order": link_sort,
        "modifiers": modifiers,
    }


def _item_dict(item: MenuItem) -> dict[str, Any]:
    links = [link for link in item.modifier_links.all() if link.group.is_active]
    links.sort(key=lambda link: (link.sort_order, link.group.name))
    return {
        "id": str(item.id),
        "name": item.name,
        "description": item.description,
        "image_url": _image_url(item),
        "price_pesewas": item.price_pesewas,
        "prep_station": item.prep_station,
        "is_available": item.is_available,
        "sort_order": item.sort_order,
        "modifier_groups": [_group_dict(link.group, link.sort_order) for link in links],
    }


def build_menu_payload() -> dict[str, Any]:
    """
    Active categories → active items (with is_available) → linked active groups → active modifiers.
    Caller must hold a restaurant context.
    """
    categories = (
        MenuCategory.objects.filter(is_active=True)
        .prefetch_related(
            "items__modifier_links__group__modifiers",
        )
        .order_by("sort_order", "name")
    )
    out: list[dict[str, Any]] = []
    for cat in categories:
        items = [
            _item_dict(item)
            for item in sorted(
                (i for i in cat.items.all() if i.is_active),
                key=lambda i: (i.sort_order, i.name),
            )
        ]
        out.append(
            {
                "id": str(cat.id),
                "name": cat.name,
                "sort_order": cat.sort_order,
                "items": items,
            }
        )
    return {"categories": out}
