import secrets

from django.db import models

from apps.core.money import PesewasField
from apps.core.tenancy import TenantModel


class Table(TenantModel):
    number = models.CharField(max_length=16, help_text="'7', '12A', 'Terrace 2'")
    seats = models.PositiveSmallIntegerField(null=True, blank=True)
    qr_token = models.CharField(
        max_length=64, help_text="Printed on the table QR for guest-phone ordering."
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "tables"
        ordering = ["number"]
        constraints = [
            models.UniqueConstraint(
                fields=["restaurant", "number"], name="uniq_table_number_per_restaurant"
            ),
            models.UniqueConstraint(fields=["qr_token"], name="uniq_table_qr_token"),
        ]

    def __str__(self) -> str:
        return f"Table {self.number}"

    @staticmethod
    def new_qr_token() -> str:
        return secrets.token_urlsafe(24)


class TableSession(TenantModel):
    """
    The bill (ADR-0008). Projection of SESSION_* events. Accumulates order rounds and payments;
    settled when paid_pesewas >= bill_total_pesewas; closed when the table is free again.
    """

    table = models.ForeignKey(Table, on_delete=models.PROTECT, related_name="sessions")
    opened_by = models.ForeignKey("accounts.Staff", on_delete=models.PROTECT, related_name="+")
    party_size = models.PositiveSmallIntegerField(null=True, blank=True)
    opened_at = models.DateTimeField()
    closed_at = models.DateTimeField(null=True, blank=True)
    bill_total_pesewas = PesewasField(default=0, help_text="Σ non-voided orders.total_pesewas")
    paid_pesewas = PesewasField(default=0, help_text="Σ non-voided payments.amount_pesewas")
    settled_at = models.DateTimeField(null=True, blank=True)
    reopened_count = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "table_sessions"
        constraints = [
            models.UniqueConstraint(
                fields=["table"],
                condition=models.Q(closed_at__isnull=True),
                name="one_open_session_per_table",
            ),
        ]
        indexes = [models.Index(fields=["restaurant", "closed_at"], name="sessions_open_idx")]

    @property
    def balance_pesewas(self) -> int:
        return self.bill_total_pesewas - self.paid_pesewas
