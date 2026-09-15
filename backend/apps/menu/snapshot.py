"""
snapshot_line — the ONLY place WS03 (and anyone else) may read a price from the menu.

Returns a frozen line snapshot. Validates availability, group membership, ONE/MANY and required.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from apps.core.errors import ApiError, ErrorCode
from apps.menu.models import MenuItem, Modifier, ModifierGroup


@dataclass(frozen=True)
class LineSnapshot:
    name: str
    unit_price_pesewas: int
    prep_station: str
    modifiers: list[dict[str, object]]  # [{id, name, price_pesewas}]
    line_total_pesewas: int


def snapshot_line(
    menu_item: MenuItem,
    modifier_ids: Sequence[uuid.UUID],
    quantity: int,
) -> LineSnapshot:
    """
    Validate and price one order line from the live menu.

    Raises ApiError 422 with codes from docs/09-api-contract.md §2:
    item_inactive, item_unavailable, modifier_invalid, required_modifier_missing.
    """
    if quantity < 1:
        raise ApiError(
            400,
            ErrorCode.VALIDATION_ERROR,
            "quantity must be at least 1.",
            errors={"quantity": ["Must be >= 1."]},
        )

    if not menu_item.is_active:
        raise ApiError(
            422,
            ErrorCode.ITEM_INACTIVE,
            f"Menu item {menu_item.name!r} is no longer on the menu.",
        )
    if not menu_item.is_available:
        raise ApiError(
            422,
            ErrorCode.ITEM_UNAVAILABLE,
            f"Menu item {menu_item.name!r} is currently unavailable (86'd).",
        )

    linked_groups: list[ModifierGroup] = [
        link.group
        for link in menu_item.modifier_links.select_related("group").all()
        if link.group.is_active
    ]
    linked_group_ids = {g.id for g in linked_groups}

    # Load requested modifiers in one query; reject unknowns / wrong-tenant via scoped manager.
    requested: list[Modifier] = []
    if modifier_ids:
        found = {
            m.id: m
            for m in Modifier.objects.filter(id__in=list(modifier_ids)).select_related("group")
        }
        for mid in modifier_ids:
            mod = found.get(mid)
            if mod is None:
                raise ApiError(
                    422,
                    ErrorCode.MODIFIER_INVALID,
                    f"Modifier {mid} does not exist.",
                )
            if not mod.is_active or not mod.is_available:
                raise ApiError(
                    422,
                    ErrorCode.MODIFIER_INVALID,
                    f"Modifier {mod.name!r} is unavailable.",
                )
            if mod.group_id not in linked_group_ids:
                raise ApiError(
                    422,
                    ErrorCode.MODIFIER_INVALID,
                    f"Modifier {mod.name!r} is not offered on {menu_item.name!r}.",
                )
            requested.append(mod)

    by_group: dict[uuid.UUID, list[Modifier]] = defaultdict(list)
    for mod in requested:
        by_group[mod.group_id].append(mod)

    for group in linked_groups:
        chosen = by_group.get(group.id, [])
        if group.selection == ModifierGroup.Selection.ONE and len(chosen) > 1:
            raise ApiError(
                422,
                ErrorCode.MODIFIER_INVALID,
                f"Group {group.name!r} allows at most one selection.",
            )
        if group.is_required and len(chosen) != 1:
            raise ApiError(
                422,
                ErrorCode.REQUIRED_MODIFIER_MISSING,
                f"Group {group.name!r} requires exactly one selection.",
            )

    unit = int(menu_item.price_pesewas)
    mod_payload = [
        {
            "id": str(m.id),
            "name": m.name,
            "price_pesewas": int(m.price_pesewas),
        }
        for m in requested
    ]
    line_total = (unit + sum(int(m.price_pesewas) for m in requested)) * quantity

    return LineSnapshot(
        name=menu_item.name,
        unit_price_pesewas=unit,
        prep_station=menu_item.prep_station,
        modifiers=mod_payload,
        line_total_pesewas=line_total,
    )
