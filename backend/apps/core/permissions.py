"""
RolePermission lives in its own module because DRF imports DEFAULT_PERMISSION_CLASSES while
rest_framework.views is still initialising; anything here must not import rest_framework.views.
"""

from __future__ import annotations

from typing import Any

from rest_framework.permissions import BasePermission

from .errors import ErrorCode


class RolePermission(BasePermission):
    """Allows the request if the principal's role is in the view's allowed_roles (empty = any principal)."""

    message = "This role may not perform this action."
    code = ErrorCode.ROLE_NOT_ALLOWED

    def has_permission(self, request: Any, view: Any) -> bool:
        principal = getattr(request, "principal", None)
        if principal is None:
            return False
        allowed = getattr(view, "allowed_roles", ())
        return not allowed or principal.actor_role in allowed
