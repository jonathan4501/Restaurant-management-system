"""
TenantAdmin: Django admin scoped to the logged-in owner's restaurant. Superusers without a linked
Staff row see nothing — the admin is a per-restaurant back office, not a cross-tenant console.
"""

from __future__ import annotations

from typing import Any

from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest

from .models import IdempotencyKey
from .tenancy import restaurant_context


def request_restaurant_id(request: HttpRequest) -> Any:
    staff = getattr(request.user, "staff", None)
    return staff.restaurant_id if staff is not None else None


class TenantAdmin(admin.ModelAdmin):
    def get_queryset(self, request: HttpRequest) -> QuerySet:
        rid = request_restaurant_id(request)
        qs = self.model.objects.unscoped()
        return qs.filter(restaurant_id=rid) if rid else qs.none()

    def save_model(self, request: HttpRequest, obj: Any, form: Any, change: bool) -> None:
        rid = request_restaurant_id(request)
        if rid is None:
            raise PermissionError("Admin user has no restaurant")
        if getattr(obj, "restaurant_id", None) is None:
            obj.restaurant_id = rid
        with restaurant_context(rid):
            super().save_model(request, obj, form, change)

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False  # nothing is ever hard-deleted


@admin.register(IdempotencyKey)
class IdempotencyKeyAdmin(TenantAdmin):
    list_display = ("key", "status", "response_status", "created_at")
    readonly_fields = (
        "key",
        "request_hash",
        "status",
        "response_status",
        "response_body",
        "created_at",
    )
    ordering = ("-created_at",)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False
