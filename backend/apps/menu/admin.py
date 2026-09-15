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
    autocomplete_fields = ("group",)


@admin.register(MenuCategory)
class MenuCategoryAdmin(TenantAdmin):
    list_display = ("name", "sort_order", "is_active")
    list_editable = ("sort_order", "is_active")
    search_fields = ("name",)


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
    autocomplete_fields = ("category",)


@admin.register(ModifierGroup)
class ModifierGroupAdmin(TenantAdmin):
    list_display = ("name", "selection", "is_required", "sort_order", "is_active")
    list_filter = ("selection", "is_required", "is_active")
    search_fields = ("name",)
    inlines = [ModifierInline]


@admin.register(Modifier)
class ModifierAdmin(TenantAdmin):
    list_display = (
        "name",
        "group",
        "price_pesewas",
        "is_default",
        "is_available",
        "is_active",
        "sort_order",
    )
    list_filter = ("group", "is_available", "is_active")
    search_fields = ("name",)
    autocomplete_fields = ("group",)


@admin.register(MenuItemModifierGroup)
class MenuItemModifierGroupAdmin(TenantAdmin):
    list_display = ("menu_item", "group", "sort_order")
    autocomplete_fields = ("menu_item", "group")
