from django.contrib import admin
from django.http import HttpRequest

from apps.core.admin import TenantAdmin

from .models import DailySales


@admin.register(DailySales)
class DailySalesAdmin(TenantAdmin):
    list_display = (
        "business_date",
        "money_taken_pesewas",
        "covers",
        "orders_closed",
        "orders_voided",
        "cash_variance_pesewas",
    )
    readonly_fields = [f.name for f in DailySales._meta.fields]

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False
