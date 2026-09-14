from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET

from .publisher import client


def _db_ok() -> bool:
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
        return True
    except Exception:
        return False


def _redis_ok() -> bool:
    try:
        return bool(client().ping())
    except Exception:
        return False


@require_GET
def healthz(request: HttpRequest) -> JsonResponse:
    checks = {"db": _db_ok(), "redis": _redis_ok()}
    return JsonResponse(
        {"ok": all(checks.values()), **checks}, status=200 if all(checks.values()) else 503
    )


@require_GET
def readyz(request: HttpRequest) -> JsonResponse:
    checks = {"db": _db_ok(), "redis": _redis_ok(), "migrations": False}
    if checks["db"]:
        executor = MigrationExecutor(connection)
        checks["migrations"] = not executor.migration_plan(executor.loader.graph.leaf_nodes())
    ok = all(checks.values())
    return JsonResponse({"ok": ok, **checks}, status=200 if ok else 503)
