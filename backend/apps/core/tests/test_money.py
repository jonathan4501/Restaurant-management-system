import pytest

from apps.core.money import format_pesewas, require_pesewas


def test_format() -> None:
    assert format_pesewas(7500) == "GH₵ 75.00"
    assert format_pesewas(1234567) == "GH₵ 12,345.67"
    assert format_pesewas(5) == "GH₵ 0.05"
    assert format_pesewas(-2000) == "-GH₵ 20.00"


@pytest.mark.parametrize("bad", [75.0, "7500", True, None, -1])
def test_require_rejects_non_integers_and_negatives(bad: object) -> None:
    with pytest.raises(ValueError):
        require_pesewas(bad)


def test_require_accepts_integers() -> None:
    assert require_pesewas(0) == 0
    assert require_pesewas(7500) == 7500
    assert require_pesewas(-100, allow_negative=True) == -100
