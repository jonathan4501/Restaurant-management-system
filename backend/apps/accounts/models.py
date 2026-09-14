from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models

from apps.core.roles import DeviceRole, StaffRole, choices
from apps.core.tenancy import TenantModel
from apps.core.uuid7 import uuid7


class Restaurant(models.Model):
    """The tenant. The only table without restaurant_id, because it is the restaurant."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    name = models.CharField(max_length=120)
    timezone = models.CharField(max_length=64, default="Africa/Accra")
    currency = models.CharField(max_length=3, default="GHS")
    day_cutover_hour = models.PositiveSmallIntegerField(default=4)
    service_start = models.TimeField(default="11:00")
    service_end = models.TimeField(default="23:00")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "restaurants"

    def __str__(self) -> str:
        return self.name


class Staff(TenantModel):
    full_name = models.CharField(max_length=120)
    role = models.CharField(max_length=16, choices=choices(StaffRole))
    pin_hash = models.CharField(max_length=255)  # argon2id. Never plaintext.
    email = models.EmailField(null=True, blank=True)  # MANAGER / OWNER only
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="staff",
        help_text="Django user for owner login and admin. OWNER / MANAGER only.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "staff"
        constraints = [
            models.UniqueConstraint(
                fields=["restaurant", "email"],
                condition=models.Q(email__isnull=False),
                name="uniq_staff_email_per_restaurant",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.full_name} ({self.role})"


class Device(TenantModel):
    label = models.CharField(max_length=80)
    token_hash = models.CharField(
        max_length=64, null=True, blank=True
    )  # sha256; NULL until enrolled
    enrolment_code = models.CharField(max_length=16, null=True, blank=True)
    enrolment_expires_at = models.DateTimeField(null=True, blank=True)
    allowed_roles = ArrayField(
        models.CharField(max_length=16, choices=choices(DeviceRole)), default=list
    )
    last_seen_at = models.DateTimeField(null=True, blank=True)
    enrolled_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "devices"
        indexes = [models.Index(fields=["token_hash"], name="devices_token_hash_idx")]

    def __str__(self) -> str:
        return self.label

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None
