from django.contrib import admin
from django.http import HttpRequest

from apps.core.admin import TenantAdmin

from .models import Order, OrderEvent, OrderItem


class ReadOnlyTenantAdmin(TenantAdmin):
    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: object = None) -> bool:
        return False


@admin.register(OrderEvent)
class OrderEventAdmin(ReadOnlyTenantAdmin):
    list_display = (
        "seq",
        "event_type",
        "aggregate_type",
        "order_id",
        "actor_role",
        "actor",
        "authorised_by",
        "reason_code",
        "created_at",
    )
    list_filter = ("event_type", "aggregate_type", "actor_role")
    search_fields = ("order_id", "aggregate_id")
    ordering = ("-seq",)


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    readonly_fields = [f.name for f in OrderItem._meta.fields]


@admin.register(Order)
class OrderAdmin(ReadOnlyTenantAdmin):
    list_display = (
        "order_number",
        "business_date",
        "status",
        "session",
        "total_pesewas",
        "origin",
        "created_at",
    )
    list_filter = ("status", "origin")
    inlines = [OrderItemInline]
