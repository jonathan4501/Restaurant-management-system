from django.db import models

from .tenancy import TenantModel


class IdempotencyKey(TenantModel):
    """
    One row per (restaurant, Idempotency-Key). Claimed before a command runs; completed with the
    response inside the command transaction. See docs/08-backend-architecture.md §3.
    """

    class Status(models.TextChoices):
        IN_PROGRESS = "IN_PROGRESS"
        DONE = "DONE"

    key = models.UUIDField()
    request_hash = models.CharField(max_length=64)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.IN_PROGRESS)
    response_status = models.PositiveSmallIntegerField(null=True, blank=True)
    response_body = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "idempotency_keys"
        constraints = [
            models.UniqueConstraint(fields=["restaurant", "key"], name="uniq_idempotency_key"),
        ]
