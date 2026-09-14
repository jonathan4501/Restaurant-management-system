"""
Seed RENZY: one restaurant, twelve tables, five staff (PIN 1234 in dev), the prototype menu.
Idempotent — safe to run twice. Prices are already integer pesewas.
"""

from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import Restaurant, Staff
from apps.accounts.pins import hash_pin
from apps.core.tenancy import restaurant_context
from apps.floor.models import Table
from apps.menu.models import MenuCategory, MenuItem, MenuItemModifierGroup, Modifier, ModifierGroup

STAFF = [
    ("Kofi Mensah", "WAITER"),
    ("Efua Asante", "WAITER"),
    ("Yaw Boateng", "KITCHEN"),
    ("Ama Owusu", "CASHIER"),
    ("Akosua Darko", "MANAGER"),
]

MOD_GROUPS = {
    "spice": (
        "Pepper level",
        "ONE",
        True,
        [("No pepper", 0), ("Mild", 0), ("Hot", 0), ("Extra hot", 0)],
        "Mild",
    ),
    "done": ("How well done", "ONE", True, [("Medium", 0), ("Well done", 0)], "Medium"),
    "extras": (
        "Add extras",
        "MANY",
        False,
        [("Extra plantain", 800), ("Extra shito", 500), ("Extra soup", 1000)],
        None,
    ),
}

MENU = [
    (
        "Mains",
        "Jollof Rice with Grilled Chicken",
        "Long grain jollof, quarter chicken, salad",
        7500,
        "KITCHEN",
        ["spice", "extras"],
    ),
    (
        "Mains",
        "Waakye Special",
        "Rice & beans, wele, boiled egg, gari, shito",
        6000,
        "KITCHEN",
        ["spice", "extras"],
    ),
    (
        "Mains",
        "Banku with Grilled Tilapia",
        "Fresh banku, whole tilapia, pepper & onion",
        12000,
        "GRILL",
        ["spice", "done"],
    ),
    (
        "Mains",
        "Fufu with Light Soup",
        "Goat meat, hot light soup",
        9000,
        "KITCHEN",
        ["spice", "extras"],
    ),
    (
        "Mains",
        "Fried Rice with Chicken",
        "Vegetable fried rice, fried chicken",
        8500,
        "KITCHEN",
        ["spice", "extras"],
    ),
    (
        "Mains",
        "Red Red with Plantain",
        "Bean stew in palm oil, ripe plantain",
        5500,
        "KITCHEN",
        ["spice"],
    ),
    (
        "Mains",
        "Omo Tuo with Groundnut Soup",
        "Rice balls, groundnut soup, chicken",
        8000,
        "KITCHEN",
        ["spice"],
    ),
    (
        "Mains",
        "Yam Chips with Chicken",
        "Fried yam, grilled chicken, shito",
        7000,
        "KITCHEN",
        ["spice", "extras"],
    ),
    (
        "Grill",
        "Whole Grilled Tilapia",
        "Charcoal grilled, pepper sauce",
        13000,
        "GRILL",
        ["spice", "done"],
    ),
    (
        "Grill",
        "Chicken Wings (6 pcs)",
        "Grilled or fried, house rub",
        7000,
        "GRILL",
        ["spice", "done"],
    ),
    (
        "Grill",
        "Khebab Platter",
        "4 sticks beef suya, onions, kpakpo shito",
        8000,
        "GRILL",
        ["spice"],
    ),
    (
        "Grill",
        "Grilled Guinea Fowl",
        "Half bird, charcoal grilled",
        15000,
        "GRILL",
        ["spice", "done"],
    ),
    ("Sides", "Kelewele", "Spiced fried ripe plantain", 2500, "KITCHEN", []),
    ("Sides", "Fried Plantain", "Sweet ripe plantain", 2000, "KITCHEN", []),
    ("Sides", "Side of Jollof", "Small portion", 3500, "KITCHEN", []),
    ("Sides", "Extra Shito", "House black pepper sauce", 1000, "KITCHEN", []),
    ("Drinks", "Club Beer", "625ml, chilled", 2500, "BAR", []),
    ("Drinks", "Star Beer", "625ml, chilled", 2500, "BAR", []),
    ("Drinks", "Guinness Smooth", "330ml bottle", 3000, "BAR", []),
    ("Drinks", "Malta Guinness", "330ml, non-alcoholic", 2000, "BAR", []),
    ("Drinks", "Alvaro", "Pear or pineapple", 2200, "BAR", []),
    ("Drinks", "Sobolo", "Fresh hibiscus, served cold", 1500, "BAR", []),
    ("Drinks", "Bottled Water", "750ml", 800, "BAR", []),
    ("Drinks", "Coconut Juice", "Fresh, served in the shell", 2000, "BAR", []),
]


class Command(BaseCommand):
    help = "Seed the RENZY restaurant with tables, staff and the prototype menu (idempotent)."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--pin", default="1234", help="dev PIN for every seeded staff member")

    @transaction.atomic
    def handle(self, *args: Any, **opts: Any) -> None:
        restaurant, _ = Restaurant.objects.get_or_create(name="RENZY")
        with restaurant_context(restaurant.id):
            pin_hash = hash_pin(opts["pin"])
            for name, role in STAFF:
                Staff.objects.get_or_create(
                    full_name=name, defaults={"role": role, "pin_hash": pin_hash}
                )

            for n in range(1, 13):
                Table.objects.get_or_create(
                    number=str(n), defaults={"seats": 4, "qr_token": Table.new_qr_token()}
                )

            groups: dict[str, ModifierGroup] = {}
            for key, (label, selection, required, options, default) in MOD_GROUPS.items():
                group, _ = ModifierGroup.objects.get_or_create(
                    name=label, defaults={"selection": selection, "is_required": required}
                )
                groups[key] = group
                for sort, (opt_name, price) in enumerate(options):
                    Modifier.objects.get_or_create(
                        group=group,
                        name=opt_name,
                        defaults={
                            "price_pesewas": price,
                            "is_default": opt_name == default,
                            "sort_order": sort,
                        },
                    )

            cat_sort = {"Mains": 0, "Grill": 1, "Sides": 2, "Drinks": 3}
            for sort, (cat_name, name, desc, price, station, mod_keys) in enumerate(MENU):
                category, _ = MenuCategory.objects.get_or_create(
                    name=cat_name, defaults={"sort_order": cat_sort[cat_name]}
                )
                item, _ = MenuItem.objects.get_or_create(
                    name=name,
                    defaults={
                        "category": category,
                        "description": desc,
                        "price_pesewas": price,
                        "prep_station": station,
                        "sort_order": sort,
                    },
                )
                for gsort, key in enumerate(mod_keys):
                    MenuItemModifierGroup.objects.get_or_create(
                        menu_item=item, group=groups[key], defaults={"sort_order": gsort}
                    )

        self.stdout.write(
            self.style.SUCCESS(f"Seeded RENZY ({restaurant.id}). Staff PIN: {opts['pin']}")
        )
