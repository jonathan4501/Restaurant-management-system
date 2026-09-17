"""
`manage.py rollup_daily_sales [--date YYYY-MM-DD] [--restaurant <id>] [--days N] [--summary]`

For the morning after the night beat did not run, and for rebuilding a date whose projections have been
repaired. The rollup is an idempotent upsert, so running this twice is not a mistake.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_date

from apps.accounts.models import Restaurant
from apps.core.tenancy import restaurant_context
from apps.reporting.rollup import previous_business_date, rollup_daily_sales
from apps.reporting.summary import send_summary


class Command(BaseCommand):
    help = "Roll up daily_sales for one business date (default: the service that has just ended)."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--date", help="Business date, YYYY-MM-DD.")
        parser.add_argument("--restaurant", help="Restaurant id. Default: every active restaurant.")
        parser.add_argument(
            "--days", type=int, default=1, help="Roll up this many dates, ending at --date."
        )
        parser.add_argument(
            "--summary", action="store_true", help="Also send the owner's daily summary."
        )

    def handle(self, *args: Any, **options: Any) -> None:
        restaurants = Restaurant.objects.filter(is_active=True)
        if options["restaurant"]:
            restaurants = restaurants.filter(pk=options["restaurant"])
        if not restaurants:
            raise CommandError("No active restaurant matched.")

        days = max(1, int(options["days"]))
        for restaurant in restaurants:
            end = self._end_date(restaurant, options["date"])
            with restaurant_context(restaurant.id):
                for offset in reversed(range(days)):
                    day = end - timedelta(days=offset)
                    row = rollup_daily_sales(restaurant, day)
                    self.stdout.write(
                        f"{restaurant.name} {day}: money taken {row.money_taken_pesewas} pesewas, "
                        f"{row.covers} covers"
                    )
                    if options["summary"]:
                        sent = send_summary(restaurant, row)
                        self.stdout.write(f"  summary sent: {sent}")

    def _end_date(self, restaurant: Restaurant, raw: str | None) -> date:
        if not raw:
            return previous_business_date(restaurant)
        parsed = parse_date(raw)
        if parsed is None:
            raise CommandError(f"--date must be YYYY-MM-DD, got {raw!r}")
        return parsed
