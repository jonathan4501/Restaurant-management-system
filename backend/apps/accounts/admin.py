from __future__ import annotations

from typing import Any

from django.contrib import admin, messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils import timezone

from apps.core.admin import TenantAdmin
from apps.core.commands import CommandContext, CommandOutcome, EventDraft, run_command
from apps.core.idempotency import request_hash
from apps.core.roles import ActorRole, AggregateType
from apps.core.tenancy import restaurant_context
from apps.core.uuid7 import uuid7
from apps.orders.events import EventType

from .enrolment import assign_enrolment_code
from .models import Device, Restaurant, Staff
from .pins import hash_pin, validate_pin_format


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
    exclude = ("pin_hash",)  # set via action or manage.py set_pin; never shown
    actions = ("set_pin_action",)
    readonly_fields = ("created_at",)

    @admin.action(description="Set PIN for selected staff")
    def set_pin_action(self, request: HttpRequest, queryset: Any) -> HttpResponse | None:
        if "apply" in request.POST:
            pin = request.POST.get("pin", "")
            try:
                validate_pin_format(pin)
            except ValueError as err:
                self.message_user(request, str(err), level=messages.ERROR)
                return None
            hashed = hash_pin(pin)
            updated = queryset.update(pin_hash=hashed)
            self.message_user(
                request,
                f"PIN updated for {updated} staff member(s). The PIN is never displayed.",
            )
            return None

        return render(
            request,
            "admin/accounts/set_pin.html",
            context={
                **self.admin_site.each_context(request),
                "opts": self.model._meta,
                "queryset": queryset,
                "action": "set_pin_action",
                "title": "Set PIN",
            },
        )


@admin.register(Device)
class DeviceAdmin(TenantAdmin):
    list_display = (
        "label",
        "allowed_roles",
        "enrolled_at",
        "last_seen_at",
        "revoked_at",
        "is_pending",
    )
    list_filter = ("revoked_at",)
    readonly_fields = (
        "token_hash",
        "enrolled_at",
        "last_seen_at",
        "enrolment_code",
        "enrolment_expires_at",
    )
    actions = ("generate_enrolment_code", "revoke_devices")

    @admin.display(boolean=True, description="Pending enrolment")
    def is_pending(self, obj: Device) -> bool:
        return obj.token_hash is None and obj.revoked_at is None

    @admin.action(description="Generate enrolment code (15 min)")
    def generate_enrolment_code(self, request: HttpRequest, queryset: Any) -> None:
        for device in queryset:
            if device.revoked_at is not None:
                self.message_user(
                    request, f"{device.label}: revoked — skipped.", level=messages.WARNING
                )
                continue
            if device.token_hash is not None:
                self.message_user(
                    request,
                    f"{device.label}: already enrolled — revoke first to re-enrol.",
                    level=messages.WARNING,
                )
                continue
            code = assign_enrolment_code(device)
            self.message_user(
                request,
                f"{device.label}: enrolment code {code} (expires in 15 minutes).",
                level=messages.SUCCESS,
            )

    @admin.action(description="Revoke selected devices")
    def revoke_devices(self, request: HttpRequest, queryset: Any) -> None:
        now = timezone.now()
        for device in queryset.filter(revoked_at__isnull=True):
            with restaurant_context(device.restaurant_id):
                Device.objects.filter(pk=device.pk).update(revoked_at=now)

                def handler(ctx: CommandContext) -> CommandOutcome:
                    return CommandOutcome(
                        events=[
                            EventDraft(
                                AggregateType.DEVICE,
                                device.id,
                                EventType.DEVICE_REVOKED,
                                {"label": device.label, "note": "revoked via admin"},
                            )
                        ],
                        response={"revoked": True},
                    )

                run_command(
                    CommandContext(
                        restaurant_id=device.restaurant_id,
                        actor_id=None,
                        actor_role=ActorRole.SYSTEM,
                        device_id=device.id,
                        idempotency_key=uuid7(),
                        request_hash=request_hash(
                            "ADMIN", f"/admin/devices/{device.id}/revoke", {"revoked": True}
                        ),
                        client_created_at=now,
                    ),
                    handler,
                )
            self.message_user(request, f"Revoked {device.label}.", level=messages.SUCCESS)


try:
    from django_otp.plugins.otp_totp.models import TOTPDevice
except ImportError:
    pass
else:
    if not admin.site.is_registered(TOTPDevice):
        from django_otp.plugins.otp_totp.admin import TOTPDeviceAdmin

        admin.site.register(TOTPDevice, TOTPDeviceAdmin)
