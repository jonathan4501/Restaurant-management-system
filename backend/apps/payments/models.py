from django.db import models

from apps.core.money import PesewasField
from apps.core.tenancy import TenantModel


class PaymentMethod(models.TextChoices):
    CASH = "CASH"
    MOMO_MTN = "MOMO_MTN"
    MOMO_TELECEL = "MOMO_TELECEL"
    MOMO_AT = "MOMO_AT"
    CARD = "CARD"
    BANK = "BANK"


class Shift(TenantModel):
    """Projection of SHIFT_* events. The variance column is the money question."""

    cashier = models.ForeignKey("accounts.Staff", on_delete=models.PROTECT, related_name="shifts")
    opened_at = models.DateTimeField()
    closed_at = models.DateTimeField(null=True, blank=True)
    opening_float_pesewas = PesewasField()
    declared_cash_pesewas = PesewasField(
        null=True, blank=True, help_text="What the cashier counted."
    )
    expected_cash_pesewas = PesewasField(
        null=True, blank=True, help_text="float + Σ cash payments − Σ paid out + Σ paid in"
    )
    variance_pesewas = models.GeneratedField(
        expression=models.F("declared_cash_pesewas") - models.F("expected_cash_pesewas"),
        output_field=models.IntegerField(),
        db_persist=True,
    )
    closed_by = models.ForeignKey(
        "accounts.Staff", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    notes = models.TextField(blank=True, default="")

    class Meta:
        db_table = "shifts"
        constraints = [
            models.UniqueConstraint(
                fields=["cashier"],
                condition=models.Q(closed_at__isnull=True),
                name="one_open_shift_per_cashier",
            ),
            models.CheckConstraint(
                condition=models.Q(opening_float_pesewas__gte=0), name="shift_float_non_negative"
            ),
        ]


class DrawerMovement(TenantModel):
    """Cash moving without a sale. Always manager-authorised."""

    class Kind(models.TextChoices):
        NO_SALE = "NO_SALE"
        PAID_OUT = "PAID_OUT"
        PAID_IN = "PAID_IN"

    shift = models.ForeignKey(Shift, on_delete=models.PROTECT, related_name="movements")
    kind = models.CharField(max_length=16, choices=Kind.choices)
    amount_pesewas = PesewasField(default=0, help_text="0 for NO_SALE")
    reason_code = models.CharField(max_length=64)
    note = models.CharField(max_length=500, blank=True, default="")
    recorded_by = models.ForeignKey("accounts.Staff", on_delete=models.PROTECT, related_name="+")
    authorised_by = models.ForeignKey("accounts.Staff", on_delete=models.PROTECT, related_name="+")
    recorded_at = models.DateTimeField()

    class Meta:
        db_table = "drawer_movements"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount_pesewas__gte=0), name="drawer_movement_non_negative"
            ),
        ]
        indexes = [models.Index(fields=["restaurant", "shift"], name="drawer_movements_shift_idx")]


class Payment(TenantModel):
    """Projection of PAYMENT_RECORDED / PAYMENT_VOIDED. Attached to the bill (session) — ADR-0008."""

    session = models.ForeignKey(
        "floor.TableSession", on_delete=models.PROTECT, related_name="payments"
    )
    order = models.ForeignKey(
        "orders.Order",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="payments",
        help_text="Set only when paying one round explicitly.",
    )
    shift = models.ForeignKey(Shift, on_delete=models.PROTECT, related_name="payments")
    method = models.CharField(max_length=16, choices=PaymentMethod.choices)
    amount_pesewas = PesewasField()
    tendered_pesewas = PesewasField(null=True, blank=True, help_text="Cash only.")
    change_pesewas = PesewasField(null=True, blank=True, help_text="Cash only.")
    external_reference = models.CharField(
        max_length=64, null=True, blank=True, help_text="MoMo transaction id, keyed by the cashier."
    )
    recorded_by = models.ForeignKey("accounts.Staff", on_delete=models.PROTECT, related_name="+")
    recorded_at = models.DateTimeField()
    voided_at = models.DateTimeField(null=True, blank=True)
    void_reason = models.CharField(max_length=64, null=True, blank=True)
    voided_by = models.ForeignKey(
        "accounts.Staff", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    void_authorised_by = models.ForeignKey(
        "accounts.Staff", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        db_table = "payments"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount_pesewas__gt=0), name="payment_amount_positive"
            ),
        ]
        indexes = [
            models.Index(fields=["restaurant", "shift"], name="payments_shift_idx"),
            models.Index(fields=["restaurant", "session"], name="payments_session_idx"),
            models.Index(fields=["restaurant", "-recorded_at"], name="payments_recorded_idx"),
        ]
