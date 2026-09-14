from django.contrib import admin
from django.http import HttpRequest

from apps.core.admin import TenantAdmin

from .models import Device, Restaurant, Staff


@admin.register(Restaurant)
class RestaurantAdmin(admin.ModelAdmin):
    list_display = ("name", "timezone", "day_cutover_hour", "is_active")

    def has_delete_permission(self, request: HttpRequest, obj: object = None) -> bool:
        return False


@admin.register(Staff)
class StaffAdmin(TenantAdmin):
    list_display = ("full_name", "role", "email", "is_active", "created_at")
    list_filter = ("role", "is_active")
    search_fields = ("full_name", "email")
    exclude = ("pin_hash",)  # set via `manage.py set_pin` or the WS01 admin action; never shown


@admin.register(Device)
class DeviceAdmin(TenantAdmin):
    list_display = ("label", "allowed_roles", "enrolled_at", "last_seen_at", "revoked_at")
    readonly_fields = ("token_hash", "enrolled_at", "last_seen_at")
    exclude = ("enrolment_code",)
