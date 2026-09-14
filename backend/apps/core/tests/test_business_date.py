from datetime import UTC, date, datetime

import pytest

from apps.core.business_date import business_date


@pytest.mark.parametrize(
    ("utc", "expected"),
    [
        (datetime(2026, 9, 14, 19, 42, tzinfo=UTC), date(2026, 9, 14)),  # 19:42 Accra → same day
        (
            datetime(2026, 9, 15, 2, 30, tzinfo=UTC),
            date(2026, 9, 14),
        ),  # 02:30 → still the 14th's service
        (datetime(2026, 9, 15, 3, 59, tzinfo=UTC), date(2026, 9, 14)),  # 03:59 → 14th
        (datetime(2026, 9, 15, 4, 0, tzinfo=UTC), date(2026, 9, 15)),  # 04:00 → new business date
    ],
)
def test_accra_cutover_at_four(utc: datetime, expected: date) -> None:
    # Africa/Accra is UTC+0 year-round.
    assert business_date(utc, "Africa/Accra", 4) == expected


def test_timezone_is_applied_before_cutover() -> None:
    # 01:00 UTC is 04:00 in Nairobi (UTC+3): exactly at cutover → new date.
    assert business_date(datetime(2026, 9, 15, 1, 0, tzinfo=UTC), "Africa/Nairobi", 4) == date(
        2026, 9, 15
    )
    assert business_date(datetime(2026, 9, 15, 0, 59, tzinfo=UTC), "Africa/Nairobi", 4) == date(
        2026, 9, 14
    )


def test_rejects_naive_datetimes() -> None:
    with pytest.raises(ValueError):
        business_date(datetime(2026, 9, 14, 19, 42), "Africa/Accra", 4)  # noqa: DTZ001
