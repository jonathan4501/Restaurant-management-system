from django.contrib import admin

from apps.core.admin import TenantAdmin

from .models import MenuCategory, MenuItem, MenuItemModifierGroup, Modifier, ModifierGroup


class ModifierInline(admin.TabularInline):
    model = Modifier
    extra = 0
    fields = ("name", "price_pesewas", "is_default", "is_available", "is_active", "sort_order")


class MenuItemModifierGroupInline(admin.TabularInline):
    model = MenuItemModifierGroup
    extra = 0
    fields = ("group", "sort_order")


@admin.register(MenuCategory)
class MenuCategoryAdmin(TenantAdmin):
    list_display = ("name", "sort_order", "is_active")


@admin.register(MenuItem)
class MenuItemAdmin(TenantAdmin):
    list_display = (
        "name",
        "category",
        "price_pesewas",
        "prep_station",
        "is_available",
        "is_active",
        "sort_order",
    )
    list_filter = ("category", "prep_station", "is_available", "is_active")
    search_fields = ("name",)
    inlines = [MenuItemModifierGroupInline]
    readonly_fields = ("is_available",)  # flipped by the 86 / restore commands, not by hand


@admin.register(ModifierGroup)
class ModifierGroupAdmin(TenantAdmin):
    list_display = ("name", "selection", "is_required", "sort_order", "is_active")
    inlines = [ModifierInline]
