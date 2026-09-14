"""drf-spectacular post-processing: document the headers every client must send."""

from typing import Any

IDEMPOTENCY_HEADER = {
    "name": "Idempotency-Key",
    "in": "header",
    "required": True,
    "description": "Client-generated UUIDv7, unique per command. Replays return the original response "
    "with `Idempotent-Replayed: true`.",
    "schema": {"type": "string", "format": "uuid"},
}
CLIENT_TIME_HEADER = {
    "name": "X-Client-Time",
    "in": "header",
    "required": False,
    "description": "The device's clock at send time (ISO 8601). Stored for audit; never used for ordering.",
    "schema": {"type": "string", "format": "date-time"},
}
DEVICE_HEADER = {
    "name": "X-Device-Token",
    "in": "header",
    "required": False,
    "description": "Enrolled device token. Required for every staff request.",
    "schema": {"type": "string"},
}


def add_standard_headers(
    result: dict[str, Any], generator: Any, request: Any, public: bool
) -> dict[str, Any]:
    for path, methods in result.get("paths", {}).items():
        for method, op in methods.items():
            if not isinstance(op, dict):
                continue
            params = op.setdefault("parameters", [])
            names = {p.get("name") for p in params if isinstance(p, dict)}
            if method.lower() == "post" and "Idempotency-Key" not in names:
                params.append(IDEMPOTENCY_HEADER)
                params.append(CLIENT_TIME_HEADER)
            if not path.startswith("/api/v1/guest") and "X-Device-Token" not in names:
                params.append(DEVICE_HEADER)
    return result
