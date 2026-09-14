"""Request/response serializers for accounts endpoints."""

from __future__ import annotations

from rest_framework import serializers

from apps.core.roles import AuthorisationPurpose, choices


class EnrolDeviceInput(serializers.Serializer):
    enrolment_code = serializers.CharField(max_length=16)


class PinLoginInput(serializers.Serializer):
    staff_id = serializers.UUIDField()
    pin = serializers.CharField(min_length=4, max_length=6)


class AuthoriseInput(serializers.Serializer):
    pin = serializers.CharField(min_length=4, max_length=6)
    purpose = serializers.ChoiceField(choices=choices(AuthorisationPurpose))


class OwnerLoginInput(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField()


class OwnerTotpInput(serializers.Serializer):
    code = serializers.CharField(min_length=6, max_length=8)


class GuestTokenInput(serializers.Serializer):
    mode = serializers.ChoiceField(choices=[("guest", "guest")], default="guest")
