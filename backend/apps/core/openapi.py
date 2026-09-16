"""drf-spectacular post-processing: document the headers every client must send."""

from typing import Any

from drf_spectacular.extensions import OpenApiAuthenticationExtension
from drf_spectacular.openapi import AutoSchema

IDEMPOTENCY_HEADER = {
    "name": "Idempotency-Key",
    "in": "header",
    # The server rejects a command without it (400 idempotency_key_missing). Marked optional here only
    # because the typed client adds it in middleware (frontend/lib/api/client.ts), not per call.
    "required": False,
    "description": "**Required by the server.** Client-generated UUIDv7, unique per command. Replays "
    "return the original response with `Idempotent-Replayed: true`.",
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


class CommandAutoSchema(AutoSchema):
    """Document a CommandView's `input_serializer` as its request body without a per-view decorator."""

    def get_request_serializer(self) -> Any:
        declared = getattr(self.view, "input_serializer", None)
        if self.method == "POST" and declared is not None:
            return declared
        return super().get_request_serializer()


class PrincipalAuthScheme(OpenApiAuthenticationExtension):
    """Documents PrincipalAuthentication: a bearer JWT (staff or guest) plus X-Device-Token for staff."""

    target_class = "apps.accounts.principals.PrincipalAuthentication"
    name = "bearerAuth"

    def get_security_definition(self, auto_schema: Any) -> dict[str, Any]:
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Staff JWT (with X-Device-Token) or guest JWT. See docs/09-api-contract.md §1.",
        }
