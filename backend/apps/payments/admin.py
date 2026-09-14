from django.contrib import admin
from django.http import HttpRequest

from apps.core.admin import TenantAdmin

from .models import DrawerMovement, Payment, Shift


class ReadOnlyTenantAdmin(TenantAdmin):
    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: object = None) -> bool:
        return False


@admin.register(Shift)
class ShiftAdmin(ReadOnlyTenantAdmin):
    list_display = (
        "cashier",
        "opened_at",
        "closed_at",
        "opening_float_pesewas",
        "expected_cash_pesewas",
        "declared_cash_pesewas",
        "variance_pesewas",
    )


@admin.register(Payment)
class PaymentAdmin(ReadOnlyTenantAdmin):
    list_display = (
        "session",
        "method",
        "amount_pesewas",
        "recorded_by",
        "recorded_at",
        "voided_at",
    )
    list_filter = ("method",)


@admin.register(DrawerMovement)
class DrawerMovementAdmin(ReadOnlyTenantAdmin):
    list_display = (
        "shift",
        "kind",
        "amount_pesewas",
        "reason_code",
        "recorded_by",
        "authorised_by",
        "recorded_at",
    )
