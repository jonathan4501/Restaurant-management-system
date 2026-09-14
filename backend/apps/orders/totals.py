"""
The only money calculation in the system:

    line_total  = (unit_price + Σ modifier prices) × quantity
    order_total = Σ line_total − discounts          (never below zero)

Integers in, integers out. `Decimal` appears once, inside percent_of(), and never leaves.
"""

from collections.abc import Iterable
from decimal import ROUND_HALF_UP, Decimal


def line_total(
    unit_price_pesewas: int, modifier_prices_pesewas: Iterable[int], quantity: int
) -> int:
    if quantity <= 0:
        raise ValueError("quantity must be positive")
    if unit_price_pesewas < 0:
        raise ValueError("unit price must not be negative")
    extras = 0
    for price in modifier_prices_pesewas:
        if price < 0:
            raise ValueError("modifier price must not be negative")
        extras += price
    return (unit_price_pesewas + extras) * quantity


def order_total(line_totals_pesewas: Iterable[int], discount_pesewas: int) -> int:
    subtotal = sum(line_totals_pesewas)
    if discount_pesewas < 0:
        raise ValueError("discount must not be negative")
    return max(0, subtotal - discount_pesewas)


def percent_of(amount_pesewas: int, percent: int) -> int:
    """Half-up to the pesewa. 10% of 12345 → 1235 (1234.5 rounds up)."""
    if not 0 <= percent <= 100:
        raise ValueError("percent must be 0..100")
    value = (Decimal(amount_pesewas) * Decimal(percent) / Decimal(100)).quantize(
        Decimal(1), rounding=ROUND_HALF_UP
    )
    return int(value)
