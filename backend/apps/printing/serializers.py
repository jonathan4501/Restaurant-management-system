from __future__ import annotations

from rest_framework import serializers


class RequestReceiptInput(serializers.Serializer):
    session_id = serializers.UUIDField(help_text="The bill to print a sales record for.")
