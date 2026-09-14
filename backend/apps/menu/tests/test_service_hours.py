"""service_hours helper."""

from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

import pytest

from apps.menu.service_hours import is_during_service


@pytest.mark.django_db
def test_inside_same_day_window(restaurant) -> None:
    restaurant.service_start = time(11, 0)
    restaurant.service_end = time(23, 0)
    restaurant.timezone = "Africa/Accra"
    restaurant.save()
    noon = datetime(2026, 9, 14, 12, 0, tzinfo=ZoneInfo("Africa/Accra"))
    assert is_during_service(restaurant, noon) is True
    morning = datetime(2026, 9, 14, 9, 0, tzinfo=ZoneInfo("Africa/Accra"))
    assert is_during_service(restaurant, morning) is False


@pytest.mark.django_db
def test_overnight_window(restaurant) -> None:
    restaurant.service_start = time(18, 0)
    restaurant.service_end = time(2, 0)
    restaurant.timezone = "UTC"
    restaurant.save()
    assert is_during_service(restaurant, datetime(2026, 9, 14, 20, 0, tzinfo=ZoneInfo("UTC")))
    assert is_during_service(restaurant, datetime(2026, 9, 15, 1, 0, tzinfo=ZoneInfo("UTC")))
    assert not is_during_service(restaurant, datetime(2026, 9, 14, 12, 0, tzinfo=ZoneInfo("UTC")))
