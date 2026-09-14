from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.accounts.models import Device, Restaurant
from apps.accounts.tokens import new_device_token
from apps.core.tenancy import restaurant_context


class Command(BaseCommand):
    help = "Enrol a device directly (dev/ops). Prints the token once."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--restaurant", required=True, help="restaurant name or id")
        parser.add_argument("--label", required=True)
        parser.add_argument("--roles", required=True, help="comma-separated, e.g. WAITER,CASHIER")

    def handle(self, *args: Any, **opts: Any) -> None:
        restaurant = (
            Restaurant.objects.filter(name=opts["restaurant"]).first()
            or Restaurant.objects.filter(id=opts["restaurant"]).first()
        )
        if restaurant is None:
            raise CommandError("restaurant not found")
        token, token_hash = new_device_token()
        with restaurant_context(restaurant.id):
            device = Device.objects.create(
                label=opts["label"],
                token_hash=token_hash,
                allowed_roles=[r.strip().upper() for r in opts["roles"].split(",")],
                enrolled_at=timezone.now(),
            )
        self.stdout.write(f"device_id={device.id}\ndevice_token={token}")
