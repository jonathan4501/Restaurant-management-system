"""
Money is an integer number of pesewas. GH₵ 75.00 == 7500.

This module is the only place that knows the word "pesewas" means money. Format to a string only in
the UI. Never a float, never a Decimal in a model, a serializer, or a JSON body.
"""

from django.db import models


class PesewasField(models.IntegerField):
    """An integer column that holds money. Exists so the invariant test can find every money column."""

    description = "Integer pesewas"

    def __init__(self, *args: object, **kwargs: object) -> None:
        kwargs.setdefault("help_text", "Integer pesewas (GH₵ x 100).")
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]


def require_pesewas(value: object, *, allow_negative: bool = False) -> int:
    """Validate an inbound money value from JSON. Booleans and floats are rejected on purpose."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("money must be an integer number of pesewas")
    if not allow_negative and value < 0:
        raise ValueError("money must not be negative")
    return value


def format_pesewas(value: int) -> str:
    """Server-side formatting for emails and receipts only. The UI has its own formatPesewas()."""
    sign = "-" if value < 0 else ""
    cedis, pesewas = divmod(abs(value), 100)
    return f"{sign}GH₵ {cedis:,}.{pesewas:02d}"
