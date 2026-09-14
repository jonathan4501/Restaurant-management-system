import pytest
from hypothesis import given
from hypothesis import strategies as st

from apps.orders.totals import line_total, order_total, percent_of

pesewas = st.integers(min_value=0, max_value=10_000_000)


@given(unit=pesewas, mods=st.lists(pesewas, max_size=6), qty=st.integers(min_value=1, max_value=50))
def test_line_total_is_the_documented_formula(unit: int, mods: list[int], qty: int) -> None:
    assert line_total(unit, mods, qty) == (unit + sum(mods)) * qty


@given(lines=st.lists(pesewas, max_size=30), discount=pesewas)
def test_order_total_never_negative_and_never_above_subtotal(
    lines: list[int], discount: int
) -> None:
    total = order_total(lines, discount)
    assert 0 <= total <= sum(lines)
    assert total == max(0, sum(lines) - discount)


@given(amount=pesewas, pct=st.integers(min_value=0, max_value=100))
def test_percent_of_is_an_integer_within_one_pesewa(amount: int, pct: int) -> None:
    value = percent_of(amount, pct)
    assert isinstance(value, int)
    assert abs(value - amount * pct / 100) <= 0.5


def test_percent_rounds_half_up() -> None:
    assert percent_of(12345, 10) == 1235  # 1234.5 → 1235
    assert percent_of(7500, 10) == 750
    assert percent_of(1, 50) == 1  # 0.5 → 1


@pytest.mark.parametrize("bad", [0, -1])
def test_quantity_must_be_positive(bad: int) -> None:
    with pytest.raises(ValueError):
        line_total(100, [], bad)


def test_negative_money_is_rejected() -> None:
    with pytest.raises(ValueError):
        line_total(-1, [], 1)
    with pytest.raises(ValueError):
        line_total(1, [-1], 1)
    with pytest.raises(ValueError):
        order_total([100], -1)
