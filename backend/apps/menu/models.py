from django.db import models

from apps.core.money import PesewasField
from apps.core.tenancy import TenantModel


class MenuCacheInvalidatingMixin:
    """Drop the GET /menu cache whenever a configuration row is written."""

    def save(self, *args: object, **kwargs: object) -> None:
        super().save(*args, **kwargs)  # type: ignore[misc]
        from apps.menu.cache import invalidate_menu_cache

        rid = getattr(self, "restaurant_id", None)
        if rid is not None:
            invalidate_menu_cache(rid)

    def delete(self, *args: object, **kwargs: object) -> tuple[int, dict[str, int]]:
        rid = getattr(self, "restaurant_id", None)
        result = super().delete(*args, **kwargs)  # type: ignore[misc]
        if rid is not None:
            from apps.menu.cache import invalidate_menu_cache

            invalidate_menu_cache(rid)
        return result


class PrepStation(models.TextChoices):
    KITCHEN = "KITCHEN"
    GRILL = "GRILL"
    BAR = "BAR"


class MenuCategory(MenuCacheInvalidatingMixin, TenantModel):
    name = models.CharField(max_length=80)
    sort_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "menu_categories"
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return self.name


class MenuItem(MenuCacheInvalidatingMixin, TenantModel):
    category = models.ForeignKey(MenuCategory, on_delete=models.PROTECT, related_name="items")
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True, default="")
    image = models.ImageField(upload_to="menu/", null=True, blank=True)
    price_pesewas = PesewasField(help_text="What the guest pays. Tax-inclusive. Integer pesewas.")
    prep_station = models.CharField(
        max_length=16, choices=PrepStation.choices, default=PrepStation.KITCHEN
    )
    is_available = models.BooleanField(
        default=True, help_text="The 86 switch. Projection of ITEM_86ED / ITEM_RESTORED."
    )
    is_active = models.BooleanField(
        default=True, help_text="False = retired from the menu. Never deleted."
    )
    sort_order = models.IntegerField(default=0)

    class Meta:
        db_table = "menu_items"
        ordering = ["sort_order", "name"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(price_pesewas__gte=0), name="menu_item_price_non_negative"
            ),
        ]

    def __str__(self) -> str:
        return self.name


class ModifierGroup(MenuCacheInvalidatingMixin, TenantModel):
    class Selection(models.TextChoices):
        ONE = "ONE"
        MANY = "MANY"

    name = models.CharField(max_length=80)
    selection = models.CharField(max_length=4, choices=Selection.choices)
    is_required = models.BooleanField(default=False)
    sort_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "modifier_groups"
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return self.name


class Modifier(MenuCacheInvalidatingMixin, TenantModel):
    group = models.ForeignKey(ModifierGroup, on_delete=models.PROTECT, related_name="modifiers")
    name = models.CharField(max_length=80)
    price_pesewas = PesewasField(default=0, help_text="0 for free choices.")
    is_default = models.BooleanField(default=False)
    is_available = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)

    class Meta:
        db_table = "modifiers"
        ordering = ["sort_order", "name"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(price_pesewas__gte=0), name="modifier_price_non_negative"
            ),
        ]

    def __str__(self) -> str:
        return self.name


class MenuItemModifierGroup(MenuCacheInvalidatingMixin, TenantModel):
    menu_item = models.ForeignKey(MenuItem, on_delete=models.PROTECT, related_name="modifier_links")
    group = models.ForeignKey(ModifierGroup, on_delete=models.PROTECT, related_name="item_links")
    sort_order = models.IntegerField(default=0)

    class Meta:
        db_table = "menu_item_modifier_groups"
        ordering = ["sort_order"]
        constraints = [
            models.UniqueConstraint(
                fields=["menu_item", "group"], name="uniq_menu_item_modifier_group"
            ),
        ]
