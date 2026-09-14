from __future__ import annotations

import pytest

from apps.accounts.models import Staff
from apps.accounts.principals import Principal
from apps.core.roles import ActorRole
from apps.menu.cache import invalidate_menu_cache
from apps.menu.models import MenuCategory, MenuItem, MenuItemModifierGroup, Modifier, ModifierGroup


@pytest.fixture(autouse=True)
def clear_menu_cache(restaurant):
    invalidate_menu_cache(restaurant.id)
    yield
    invalidate_menu_cache(restaurant.id)


@pytest.fixture
def kitchen_staff(restaurant, pin_hash) -> Staff:
    return Staff.objects.create(full_name="Yaw", role="KITCHEN", pin_hash=pin_hash)


@pytest.fixture
def kitchen_principal(restaurant, kitchen_staff, device) -> Principal:
    return Principal("STAFF", restaurant.id, kitchen_staff.id, ActorRole.KITCHEN, device[0].id)


@pytest.fixture
def manager_principal(restaurant, manager, device) -> Principal:
    return Principal("STAFF", restaurant.id, manager.id, ActorRole.MANAGER, device[0].id)


@pytest.fixture
def category(restaurant) -> MenuCategory:
    return MenuCategory.objects.create(name="Grill", sort_order=1)


@pytest.fixture
def guinea_fowl(category) -> MenuItem:
    return MenuItem.objects.create(
        category=category,
        name="Grilled Guinea Fowl",
        description="Half bird, charcoal grilled",
        price_pesewas=15000,
        prep_station="GRILL",
        sort_order=0,
    )


@pytest.fixture
def pepper_group(restaurant) -> ModifierGroup:
    return ModifierGroup.objects.create(
        name="Pepper level", selection=ModifierGroup.Selection.ONE, is_required=True, sort_order=0
    )


@pytest.fixture
def extras_group(restaurant) -> ModifierGroup:
    return ModifierGroup.objects.create(
        name="Add extras", selection=ModifierGroup.Selection.MANY, is_required=False, sort_order=1
    )


@pytest.fixture
def linked_guinea(guinea_fowl, pepper_group, extras_group) -> MenuItem:
    MenuItemModifierGroup.objects.create(menu_item=guinea_fowl, group=pepper_group, sort_order=0)
    MenuItemModifierGroup.objects.create(menu_item=guinea_fowl, group=extras_group, sort_order=1)
    Modifier.objects.create(
        group=pepper_group, name="Mild", price_pesewas=0, is_default=True, sort_order=0
    )
    Modifier.objects.create(
        group=pepper_group, name="Hot", price_pesewas=0, is_default=False, sort_order=1
    )
    Modifier.objects.create(
        group=extras_group, name="Extra plantain", price_pesewas=800, sort_order=0
    )
    return guinea_fowl
