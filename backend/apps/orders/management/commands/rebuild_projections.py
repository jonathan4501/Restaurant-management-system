import uuid
from typing import Any

from django.core.management.base import BaseCommand

from apps.orders.rebuild import rebuild


class Command(BaseCommand):
    help = "Clear and rebuild every projection table for a restaurant from order_events."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--restaurant", required=True, help="restaurant id")

    def handle(self, *args: Any, **opts: Any) -> None:
        count = rebuild(uuid.UUID(opts["restaurant"]))
        self.stdout.write(self.style.SUCCESS(f"Replayed {count} events."))
