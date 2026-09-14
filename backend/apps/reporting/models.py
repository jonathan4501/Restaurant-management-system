from django.db import models

from apps.core.money import PesewasField
from apps.core.tenancy import TenantModel


class DailySales(TenantModel):
    """
    Nightly rollup written by the Celery task (WS06). Read by the owner dashboard.
    money_taken_pesewas is gross cash through the till. It is NOT revenue and NOT profit. Keep the name.
    """

    business_date = models.DateField()
    money_taken_pesewas = PesewasField(
        help_text="Money taken — gross cash through the till. Not revenue."
    )
    covers = models.IntegerField(default=0)
    orders_closed = models.IntegerField(default=0)
    orders_voided = models.IntegerField(default=0)
    void_value_pesewas = PesewasField(default=0)
    discount_pesewas = PesewasField(default=0)
    cash_variance_pesewas = models.IntegerField(default=0)  # may be negative; still integer pesewas
    computed_at = models.DateTimeField()

    class Meta:
        db_table = "daily_sales"
        constraints = [
            models.UniqueConstraint(
                fields=["restaurant", "business_date"], name="uniq_daily_sales_per_date"
            ),
        ]
        verbose_name_plural = "daily sales"
