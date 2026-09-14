"""
order_events — the source of truth (ADR-0001, ADR-0007) — and the order projections.
Nothing here is written except through apps.core.commands.run_command and the projectors.
"""

from __future__ import annotations

from typing import Any

from django.db import models

from apps.core.money import PesewasField
from apps.core.roles import ActorRole, AggregateType, choices
from apps.core.tenancy import TenantModel


class OrderEvent(TenantModel):
    seq = models.BigIntegerField(
        help_text="Per restaurant, gapless, assigned under an advisory lock."
    )
    aggregate_type = models.CharField(max_length=16, choices=choices(AggregateType))
    aggregate_id = models.UUIDField()
    order_id = models.UUIDField(null=True, blank=True)
    event_type = models.CharField(max_length=40)
    payload = models.JSONField(default=dict)
    actor = models.ForeignKey(
        "accounts.Staff", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    actor_role = models.CharField(max_length=16, choices=choices(ActorRole))
    authorised_by = models.ForeignKey(
        "accounts.Staff", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    reason_code = models.CharField(max_length=64, null=True, blank=True)
    device = models.ForeignKey(
        "accounts.Device", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    idempotency_key = models.UUIDField()
    client_created_at = models.DateTimeField(help_text="What the device claimed. Audit only.")
    created_at = models.DateTimeField(help_text="What the server knows. Authoritative.")

    class Meta:
        db_table = "order_events"
        ordering = ["seq"]
        constraints = [
            models.UniqueConstraint(fields=["restaurant", "seq"], name="uniq_seq"),
        ]
        indexes = [
            # One command may append several events under one key; uniqueness of the key itself is
            # enforced by idempotency_keys. This index answers "which events did request X produce".
            models.Index(fields=["restaurant", "idempotency_key"], name="oe_idem_idx"),
            models.Index(fields=["restaurant", "order_id", "seq"], name="oe_order_seq_idx"),
            models.Index(
                fields=["restaurant", "aggregate_type", "aggregate_id", "seq"],
                name="oe_aggregate_seq_idx",
            ),
            models.Index(fields=["restaurant", "-created_at"], name="oe_created_idx"),
            models.Index(
                fields=["restaurant", "event_type", "-created_at"], name="oe_type_created_idx"
            ),
            models.Index(
                fields=["restaurant", "actor", "-created_at"], name="oe_actor_created_idx"
            ),
        ]

    def __str__(self) -> str:
        return f"#{self.seq} {self.event_type}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise RuntimeError("order_events is append-only")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> None:  # type: ignore[override]
        raise RuntimeError("order_events is append-only")

    def to_envelope(self) -> dict[str, Any]:
        """The SSE `data:` object and the polling-endpoint row. docs/09 §4."""
        return {
            "id": str(self.id),
            "seq": self.seq,
            "type": self.event_type,
            "aggregate_type": self.aggregate_type,
            "aggregate_id": str(self.aggregate_id),
            "order_id": str(self.order_id) if self.order_id else None,
            "actor_role": self.actor_role,
            "actor_id": str(self.actor_id) if self.actor_id else None,
            "authorised_by": str(self.authorised_by_id) if self.authorised_by_id else None,
            "reason_code": self.reason_code,
            "created_at": self.created_at.isoformat().replace("+00:00", "Z"),
            "payload": self.payload,
        }


class OrderStatus(models.TextChoices):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    PREPARING = "PREPARING"
    READY = "READY"
    SERVED = "SERVED"
    CLOSED = "CLOSED"
    VOIDED = "VOIDED"


class OrderOrigin(models.TextChoices):
    WAITER = "WAITER"
    GUEST_TABLET = "GUEST_TABLET"
    GUEST_QR = "GUEST_QR"


class OrderCounter(TenantModel):
    """Sequential order numbers per business date, assigned at SUBMIT under a row lock."""

    business_date = models.DateField()
    next_number = models.IntegerField(default=1)

    class Meta:
        db_table = "order_counters"
        constraints = [
            models.UniqueConstraint(
                fields=["restaurant", "business_date"], name="uniq_order_counter_per_date"
            ),
        ]


class Order(TenantModel):
    """Projection. One round at a table. Belongs to a TableSession (the bill)."""

    session = models.ForeignKey(
        "floor.TableSession", on_delete=models.PROTECT, related_name="orders"
    )
    business_date = models.DateField(null=True, blank=True)
    order_number = models.IntegerField(
        null=True, blank=True, help_text="NULL while DRAFT. Gaps are an alarm."
    )
    status = models.CharField(max_length=16, choices=OrderStatus.choices, default=OrderStatus.DRAFT)
    subtotal_pesewas = PesewasField(default=0)
    discount_pesewas = PesewasField(default=0)
    total_pesewas = PesewasField(
        default=0, help_text="subtotal − discount. This is the whole calculation."
    )
    placed_by = models.ForeignKey(
        "accounts.Staff", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    origin = models.CharField(
        max_length=16, choices=OrderOrigin.choices, default=OrderOrigin.WAITER
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    ready_at = models.DateTimeField(null=True, blank=True)
    served_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    voided_at = models.DateTimeField(null=True, blank=True)
    void_reason = models.CharField(max_length=64, null=True, blank=True)
    voided_by = models.ForeignKey(
        "accounts.Staff", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    authorised_by = models.ForeignKey(
        "accounts.Staff", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField()

    class Meta:
        db_table = "orders"
        constraints = [
            models.UniqueConstraint(
                fields=["restaurant", "business_date", "order_number"],
                condition=models.Q(order_number__isnull=False),
                name="uniq_order_number_per_date",
            ),
            models.CheckConstraint(
                condition=models.Q(subtotal_pesewas__gte=0), name="order_subtotal_non_negative"
            ),
            models.CheckConstraint(
                condition=models.Q(discount_pesewas__gte=0), name="order_discount_non_negative"
            ),
            models.CheckConstraint(
                condition=models.Q(total_pesewas__gte=0), name="order_total_non_negative"
            ),
        ]
        indexes = [
            models.Index(fields=["restaurant", "status", "-created_at"], name="orders_status_idx"),
            models.Index(fields=["restaurant", "session"], name="orders_session_idx"),
        ]

    def __str__(self) -> str:
        return f"Order #{self.order_number or 'draft'} ({self.status})"


class OrderItemStatus(models.TextChoices):
    PENDING = "PENDING"
    PREPARING = "PREPARING"
    READY = "READY"
    SERVED = "SERVED"
    VOIDED = "VOIDED"


class OrderItem(TenantModel):
    """Projection. SNAPSHOTS: never join to menu_items to price or label a historical line."""

    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="items")
    menu_item_id = models.UUIDField(
        help_text="Reference only. Name and price below are the truth for this line."
    )
    name_snapshot = models.CharField(max_length=120)
    unit_price_pesewas = PesewasField()
    prep_station = models.CharField(max_length=16)
    quantity = models.PositiveIntegerField()
    modifiers = models.JSONField(
        default=list, help_text="[{id, name, price_pesewas}] — snapshots too."
    )
    notes = models.CharField(max_length=500, blank=True, default="")
    course = models.PositiveSmallIntegerField(default=1)
    status = models.CharField(
        max_length=16, choices=OrderItemStatus.choices, default=OrderItemStatus.PENDING
    )
    line_total_pesewas = PesewasField(help_text="(unit_price + Σ modifier prices) × quantity")
    sort_order = models.IntegerField(default=0)

    class Meta:
        db_table = "order_items"
        ordering = ["sort_order"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0), name="order_item_quantity_positive"
            ),
            models.CheckConstraint(
                condition=models.Q(unit_price_pesewas__gte=0), name="order_item_price_non_negative"
            ),
            models.CheckConstraint(
                condition=models.Q(line_total_pesewas__gte=0), name="order_item_total_non_negative"
            ),
        ]
        indexes = [models.Index(fields=["restaurant", "order"], name="order_items_order_idx")]
