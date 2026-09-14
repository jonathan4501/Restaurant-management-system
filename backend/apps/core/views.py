"""
CommandView: the DRF base every write endpoint extends. It owns the Idempotency-Key, the principal →
CommandContext mapping, the optional manager authorisation block, and the call into run_command.
Subclasses implement handle() and nothing else.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.authorisation import consume_authorisation
from apps.accounts.principals import current_principal

from .commands import CommandContext, CommandOutcome, run_command
from .errors import ApiError, ErrorCode
from .idempotency import request_hash
from .permissions import RolePermission
from .roles import ActorRole, AuthorisationPurpose
from .uuid7 import is_uuid7

__all__ = ["CommandView", "RolePermission", "parse_idempotency_key", "parse_client_time"]


class AuthorisationSerializer(serializers.Serializer):
    token = serializers.CharField()
    reason_code = serializers.CharField(max_length=64)
    note = serializers.CharField(required=False, allow_blank=True, max_length=500)


def parse_idempotency_key(request: Request) -> uuid.UUID:
    raw = request.headers.get("Idempotency-Key")
    if not raw or not is_uuid7(raw):
        raise ApiError(
            400,
            ErrorCode.IDEMPOTENCY_KEY_MISSING,
            "Every POST needs an Idempotency-Key header containing a client-generated UUIDv7.",
        )
    return uuid.UUID(raw)


def parse_client_time(request: Request) -> datetime:
    raw = request.headers.get("X-Client-Time")
    parsed = parse_datetime(raw) if raw else None
    if parsed is None:
        return timezone.now()
    return parsed if timezone.is_aware(parsed) else timezone.make_aware(parsed, UTC)


class CommandView(APIView):
    permission_classes = [RolePermission]
    allowed_roles: tuple[ActorRole, ...] = ()
    input_serializer: type[serializers.Serializer] | None = None
    authorisation_purpose: AuthorisationPurpose | None = None

    def handle(self, ctx: CommandContext, data: dict[str, Any], **kwargs: Any) -> CommandOutcome:
        raise NotImplementedError

    def needs_authorisation(
        self, data: dict[str, Any], **kwargs: Any
    ) -> AuthorisationPurpose | None:
        """Override when the requirement depends on state (e.g. void after acknowledgement)."""
        return self.authorisation_purpose

    def post(self, request: Request, **kwargs: Any) -> Response:
        principal = current_principal(request)
        key = parse_idempotency_key(request)
        body = request.data if isinstance(request.data, dict) else {}

        data: dict[str, Any]
        if self.input_serializer is not None:
            serializer = self.input_serializer(data=body, context={"request": request})
            serializer.is_valid(raise_exception=True)
            data = dict(serializer.validated_data)
        else:
            data = dict(body)

        authorised_by: uuid.UUID | None = None
        reason_code: str | None = None
        purpose = self.needs_authorisation(data, **kwargs)
        raw_auth = body.get("authorisation")
        if purpose is not None:
            if not raw_auth:
                raise ApiError(
                    403,
                    ErrorCode.AUTHORISATION_REQUIRED,
                    f"This action needs manager authorisation for purpose {purpose}.",
                )
            auth = AuthorisationSerializer(data=raw_auth)
            auth.is_valid(raise_exception=True)
            authorised_by = consume_authorisation(
                auth.validated_data["token"], device_id=principal.device_id, purpose=purpose
            )
            reason_code = auth.validated_data["reason_code"]
            data["note"] = auth.validated_data.get("note") or data.get("note")

        ctx = CommandContext(
            restaurant_id=principal.restaurant_id,
            actor_id=principal.actor_id,
            actor_role=principal.actor_role,
            device_id=principal.device_id,
            idempotency_key=key,
            request_hash=request_hash(request.method or "POST", request.path, body),
            client_created_at=parse_client_time(request),
            authorised_by=authorised_by,
            reason_code=reason_code,
        )
        result = run_command(ctx, lambda c: self.handle(c, data, **kwargs))
        response = Response(result.body, status=result.status)
        if result.replayed:
            response["Idempotent-Replayed"] = "true"
        return response
