"""Guest rate limit: 60 requests per minute per table-session id."""

from __future__ import annotations

from typing import Any

from rest_framework.throttling import SimpleRateThrottle


class GuestThrottle(SimpleRateThrottle):
    scope = "guest"

    def get_cache_key(self, request: Any, view: Any) -> str | None:
        principal = getattr(request, "principal", None)
        if principal is None or getattr(principal, "kind", None) != "GUEST":
            return None
        sid = getattr(principal, "session_id", None)
        if sid is None:
            return None
        return self.cache_format % {"scope": self.scope, "ident": str(sid)}
