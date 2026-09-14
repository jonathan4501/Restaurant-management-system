from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import Staff
from apps.accounts.pins import hash_pin


class Command(BaseCommand):
    help = "Set a staff member's PIN by staff id."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("staff_id")
        parser.add_argument("pin")

    def handle(self, *args: Any, **opts: Any) -> None:
        staff = Staff.objects.unscoped().filter(id=opts["staff_id"]).first()
        if staff is None:
            raise CommandError("staff not found")
        try:
            staff.pin_hash = hash_pin(opts["pin"])
        except ValueError as err:
            raise CommandError(str(err)) from err
        staff.save(update_fields=["pin_hash"])
        self.stdout.write(f"PIN updated for {staff.full_name}")
