"""Serializers for floor + orders write endpoints."""

from __future__ import annotations

from rest_framework import serializers


class OpenSessionInput(serializers.Serializer):
    id = serializers.UUIDField()
    table_id = serializers.UUIDField()
    party_size = serializers.IntegerField(required=False, allow_null=True, min_value=1)


class OpenOrderInput(serializers.Serializer):
    id = serializers.UUIDField()
    session_id = serializers.UUIDField()


class AddItemInput(serializers.Serializer):
    id = serializers.UUIDField()
    menu_item_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1)
    modifier_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, default=list
    )
    notes = serializers.CharField(required=False, allow_blank=True, default="", max_length=500)
    course = serializers.IntegerField(required=False, default=1, min_value=1)


class ModifyItemInput(serializers.Serializer):
    quantity = serializers.IntegerField(required=False, min_value=1)
    modifier_ids = serializers.ListField(child=serializers.UUIDField(), required=False)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=500)
    course = serializers.IntegerField(required=False, min_value=1)


class VoidInput(serializers.Serializer):
    reason_code = serializers.CharField(max_length=64)
    note = serializers.CharField(required=False, allow_blank=True, default="", max_length=500)


class DiscountInput(serializers.Serializer):
    kind = serializers.ChoiceField(choices=["PERCENT", "AMOUNT"])
    value = serializers.IntegerField(min_value=0)
    reason_code = serializers.CharField(required=False, max_length=64)
    note = serializers.CharField(required=False, allow_blank=True, default="", max_length=500)


class CompInput(serializers.Serializer):
    reason_code = serializers.CharField(required=False, max_length=64)
    note = serializers.CharField(required=False, allow_blank=True, default="", max_length=500)


class PriceOverrideInput(serializers.Serializer):
    unit_price_pesewas = serializers.IntegerField(min_value=0)
    reason_code = serializers.CharField(required=False, max_length=64)
    note = serializers.CharField(required=False, allow_blank=True, default="", max_length=500)


class EmptyInput(serializers.Serializer):
    pass
