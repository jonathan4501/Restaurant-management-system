"""Write inputs for shifts, payments and the drawer. Money fields are integer pesewas."""

from __future__ import annotations

from rest_framework import serializers

from apps.payments.models import DrawerMovement, PaymentMethod


class OpenShiftInput(serializers.Serializer):
    id = serializers.UUIDField()
    opening_float_pesewas = serializers.IntegerField(min_value=0)


class CloseShiftInput(serializers.Serializer):
    declared_cash_pesewas = serializers.IntegerField(min_value=0)
    note = serializers.CharField(required=False, allow_blank=True, default="", max_length=500)


class DrawerMovementInput(serializers.Serializer):
    kind = serializers.ChoiceField(choices=DrawerMovement.Kind.choices)
    amount_pesewas = serializers.IntegerField(required=False, default=0, min_value=0)
    reason_code = serializers.CharField(required=False, max_length=64)
    note = serializers.CharField(required=False, allow_blank=True, default="", max_length=500)


class RecordPaymentInput(serializers.Serializer):
    id = serializers.UUIDField()
    method = serializers.ChoiceField(choices=PaymentMethod.choices)
    amount_pesewas = serializers.IntegerField(min_value=1)
    tendered_pesewas = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    external_reference = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, max_length=64
    )
    order_id = serializers.UUIDField(required=False, allow_null=True)


class VoidPaymentInput(serializers.Serializer):
    reason_code = serializers.CharField(required=False, max_length=64)
    note = serializers.CharField(required=False, allow_blank=True, default="", max_length=500)


class ReopenSessionInput(serializers.Serializer):
    reason_code = serializers.CharField(required=False, max_length=64)
    note = serializers.CharField(required=False, allow_blank=True, default="", max_length=500)
