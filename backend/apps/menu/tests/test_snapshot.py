"""snapshot_line validation + property tests for line totals."""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from apps.core.errors import ApiError, ErrorCode
from apps.menu.models import MenuItemModifierGroup, Modifier, ModifierGroup
from apps.menu.snapshot import snapshot_line

pesewas = st.integers(min_value=0, max_value=100_000)


@pytest.mark.django_db
def test_snapshot_happy_path(linked_guinea, pepper_group, extras_group) -> None:
    mild = Modifier.objects.get(group=pepper_group, name="Mild")
    plantain = Modifier.objects.get(group=extras_group, name="Extra plantain")
    snap = snapshot_line(linked_guinea, [mild.id, plantain.id], 2)
    assert snap.name == "Grilled Guinea Fowl"
    assert snap.unit_price_pesewas == 15000
    assert snap.prep_station == "GRILL"
    assert snap.line_total_pesewas == (15000 + 800) * 2
    assert {m["name"] for m in snap.modifiers} == {"Mild", "Extra plantain"}


@pytest.mark.django_db
def test_required_group_missing(linked_guinea) -> None:
    with pytest.raises(ApiError) as exc:
        snapshot_line(linked_guinea, [], 1)
    assert exc.value.code == ErrorCode.REQUIRED_MODIFIER_MISSING
    assert exc.value.status_code == 422


@pytest.mark.django_db
def test_one_group_with_two_modifiers(linked_guinea, pepper_group) -> None:
    mild = Modifier.objects.get(group=pepper_group, name="Mild")
    hot = Modifier.objects.get(group=pepper_group, name="Hot")
    with pytest.raises(ApiError) as exc:
        snapshot_line(linked_guinea, [mild.id, hot.id], 1)
    assert exc.value.code == ErrorCode.MODIFIER_INVALID
    assert exc.value.status_code == 422


@pytest.mark.django_db
def test_unavailable_modifier(linked_guinea, pepper_group) -> None:
    mild = Modifier.objects.get(group=pepper_group, name="Mild")
    mild.is_available = False
    mild.save()
    with pytest.raises(ApiError) as exc:
        snapshot_line(linked_guinea, [mild.id], 1)
    assert exc.value.code == ErrorCode.MODIFIER_INVALID


@pytest.mark.django_db
def test_unavailable_item(linked_guinea, pepper_group) -> None:
    mild = Modifier.objects.get(group=pepper_group, name="Mild")
    linked_guinea.is_available = False
    linked_guinea.save()
    with pytest.raises(ApiError) as exc:
        snapshot_line(linked_guinea, [mild.id], 1)
    assert exc.value.code == ErrorCode.ITEM_UNAVAILABLE


@pytest.mark.django_db
def test_inactive_item(linked_guinea, pepper_group) -> None:
    mild = Modifier.objects.get(group=pepper_group, name="Mild")
    linked_guinea.is_active = False
    linked_guinea.save()
    with pytest.raises(ApiError) as exc:
        snapshot_line(linked_guinea, [mild.id], 1)
    assert exc.value.code == ErrorCode.ITEM_INACTIVE


@pytest.mark.django_db
def test_modifier_not_linked_to_item(guinea_fowl, restaurant) -> None:
    other = ModifierGroup.objects.create(
        name="Orphan", selection=ModifierGroup.Selection.ONE, is_required=False
    )
    mod = Modifier.objects.create(group=other, name="Nope", price_pesewas=100)
    with pytest.raises(ApiError) as exc:
        snapshot_line(guinea_fowl, [mod.id], 1)
    assert exc.value.code == ErrorCode.MODIFIER_INVALID


@given(
    unit=pesewas,
    mod_prices=st.lists(pesewas, max_size=5),
    qty=st.integers(min_value=1, max_value=30),
)
@settings(
    suppress_health_check=[HealthCheck.function_scoped_fixture], deadline=None, max_examples=40
)
@pytest.mark.django_db
def test_line_total_property(restaurant, category, unit, mod_prices, qty) -> None:
    from apps.core.uuid7 import uuid7
    from apps.menu.models import MenuItem

    item = MenuItem.objects.create(
        category=category,
        name=f"Item-{uuid7()}",
        price_pesewas=unit,
        prep_station="KITCHEN",
    )
    group = ModifierGroup.objects.create(
        name=f"Extras-{item.id}",
        selection=ModifierGroup.Selection.MANY,
        is_required=False,
    )
    MenuItemModifierGroup.objects.create(menu_item=item, group=group)
    ids = []
    for i, price in enumerate(mod_prices):
        mod = Modifier.objects.create(group=group, name=f"m{i}", price_pesewas=price, sort_order=i)
        ids.append(mod.id)

    snap = snapshot_line(item, ids, qty)
    assert snap.line_total_pesewas == (unit + sum(mod_prices)) * qty
    assert snap.unit_price_pesewas == unit
    assert len(snap.modifiers) == len(mod_prices)
