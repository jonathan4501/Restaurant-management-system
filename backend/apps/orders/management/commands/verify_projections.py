import json
import sys
import uuid
from typing import Any

from django.core.management.base import BaseCommand

from apps.orders.rebuild import verify


class Command(BaseCommand):
    help = "Rebuild projections in a rolled-back transaction and report any drift. Exit 1 on drift."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--restaurant", required=True, help="restaurant id")

    def handle(self, *args: Any, **opts: Any) -> None:
        diffs = verify(uuid.UUID(opts["restaurant"]))
        if not diffs:
            self.stdout.write(self.style.SUCCESS("Projections match the event stream."))
            return
        self.stdout.write(json.dumps(diffs, indent=2, default=str))
        self.stderr.write(self.style.ERROR(f"Drift in {len(diffs)} table(s)."))
        sys.exit(1)
