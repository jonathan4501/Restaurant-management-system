from django.contrib import admin

from apps.core.admin import TenantAdmin

from .models import Table, TableSession


@admin.register(Table)
class TableAdmin(TenantAdmin):
    list_display = ("number", "seats", "is_active")
    readonly_fields = ("qr_token",)


@admin.register(TableSession)
class TableSessionAdmin(TenantAdmin):
    list_display = (
        "table",
        "opened_at",
        "closed_at",
        "bill_total_pesewas",
        "paid_pesewas",
        "settled_at",
    )
    readonly_fields = [f.name for f in TableSession._meta.fields]

    def has_add_permission(self, request: object) -> bool:
        return False  # projection; written only by the command runner
