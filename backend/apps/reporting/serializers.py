"""
Request and response schemas for the four owner endpoints.

These exist so the OpenAPI describes every field and `openapi-typescript` can generate a real type for
it. Each response serializer is also what actually renders the response, so a field that drifts out of
`queries.py` fails a test rather than quietly disappearing from the schema.

Every gross money field is described as "Money taken (gross cash through the till)". Not revenue, not
profit — see CLAUDE.md and ADR-0005.
"""

from __future__ import annotations

from rest_framework import serializers

from apps.core.roles import AggregateType, choices
from apps.orders.events import EventType

MONEY_TAKEN = "Money taken (gross cash through the till). Integer pesewas. Not revenue, not profit."
PESEWAS = "Integer pesewas."


# ---------------------------------------------------------------- query parameters


class WindowQuery(serializers.Serializer):
    """A window of business dates. A restaurant's day runs to the cutover hour, not to midnight."""

    date_from = serializers.DateField(
        required=False,
        source="from",
        help_text="First business date, YYYY-MM-DD. Default: six dates before `to`.",
    )
    date_to = serializers.DateField(
        required=False,
        source="to",
        help_text="Last business date, YYYY-MM-DD. Default: the current business date.",
    )


class EventLogQuery(serializers.Serializer):
    cursor = serializers.IntegerField(
        required=False, help_text="`next_cursor` from the previous page. Pages run newest first."
    )
    limit = serializers.IntegerField(
        required=False, min_value=1, max_value=200, help_text="Rows per page (1–200, default 100)."
    )
    actor_id = serializers.UUIDField(required=False, help_text="Only this staff member's actions.")
    type = serializers.ChoiceField(
        choices=choices(EventType), required=False, help_text="One event type."
    )
    aggregate_type = serializers.ChoiceField(choices=choices(AggregateType), required=False)
    date_from = serializers.DateTimeField(
        required=False, source="from", help_text="Server time, inclusive (ISO 8601)."
    )
    date_to = serializers.DateTimeField(
        required=False, source="to", help_text="Server time, exclusive (ISO 8601)."
    )
    flagged = serializers.BooleanField(
        required=False,
        help_text="Only the actions the owner is asked to look at: voids after the kitchen "
        "acknowledged, discounts, comps, price overrides, reopens, payment voids, drawer movements, "
        "PIN failures and lockouts, and price changes.",
    )


# ---------------------------------------------------------------- 1. variance


class VoidAfterAckSerializer(serializers.Serializer):
    order_id = serializers.UUIDField(allow_null=True)
    order_number = serializers.IntegerField(allow_null=True)
    table_number = serializers.CharField(allow_null=True)
    value_pesewas = serializers.IntegerField(
        help_text=f"Order total when the void was authorised. {PESEWAS}"
    )
    status_at_void = serializers.CharField(allow_null=True)
    reason_code = serializers.CharField(allow_null=True)
    actor = serializers.CharField(allow_null=True, help_text="Who voided it.")
    actor_role = serializers.CharField(allow_null=True)
    authorised_by = serializers.CharField(
        allow_null=True, help_text="The manager whose PIN allowed it."
    )
    at = serializers.DateTimeField(help_text="Server time.")


class DiscountsByStaffSerializer(serializers.Serializer):
    staff = serializers.CharField()
    staff_id = serializers.UUIDField(allow_null=True)
    discount_count = serializers.IntegerField()
    discount_pesewas = serializers.IntegerField(help_text=PESEWAS)
    comp_count = serializers.IntegerField()
    comp_pesewas = serializers.IntegerField(help_text=PESEWAS)
    value_pesewas = serializers.IntegerField(help_text=f"Discounts and comps together. {PESEWAS}")


class ReopenedBillSerializer(serializers.Serializer):
    session_id = serializers.UUIDField()
    table_number = serializers.CharField(allow_null=True)
    trigger = serializers.ChoiceField(
        choices=[("MANAGER", "MANAGER"), ("PAYMENT_VOID", "PAYMENT_VOID")],
        help_text="MANAGER: someone reopened the bill on purpose. PAYMENT_VOID: voiding a payment "
        "took a settled bill back below its total.",
    )
    orders_reopened = serializers.IntegerField()
    reason_code = serializers.CharField(allow_null=True)
    actor = serializers.CharField(allow_null=True)
    authorised_by = serializers.CharField(allow_null=True)
    at = serializers.DateTimeField()


class ShiftVarianceSerializer(serializers.Serializer):
    shift_id = serializers.UUIDField()
    cashier = serializers.CharField()
    cashier_id = serializers.UUIDField()
    opened_at = serializers.DateTimeField()
    closed_at = serializers.DateTimeField(allow_null=True)
    expected_cash_pesewas = serializers.IntegerField(allow_null=True, help_text=PESEWAS)
    declared_cash_pesewas = serializers.IntegerField(
        allow_null=True, help_text=f"What the cashier counted. {PESEWAS}"
    )
    variance_pesewas = serializers.IntegerField(
        allow_null=True, help_text=f"Declared − expected. Negative is a short count. {PESEWAS}"
    )


class OrderNumberGapSerializer(serializers.Serializer):
    business_date = serializers.DateField()
    missing = serializers.ListField(
        child=serializers.IntegerField(),
        help_text="Ticket numbers that were issued but are not in the projections.",
    )


class VarianceSerializer(serializers.Serializer):
    """Every way money can leave without a sale behind it."""

    date_from = serializers.DateField(source="from")
    date_to = serializers.DateField(source="to")
    voids_after_acknowledgement = VoidAfterAckSerializer(many=True)
    void_value_pesewas = serializers.IntegerField(
        help_text=f"Food that was cooked and thrown away. {PESEWAS}"
    )
    discounts_by_staff = DiscountsByStaffSerializer(many=True)
    discount_pesewas = serializers.IntegerField(help_text=PESEWAS)
    comp_pesewas = serializers.IntegerField(help_text=PESEWAS)
    reopened_bills = ReopenedBillSerializer(many=True)
    reopened_count = serializers.IntegerField()
    manager_reopens = serializers.IntegerField(
        help_text="Of those, the ones a manager reopened deliberately."
    )
    cash_variance_by_shift = ShiftVarianceSerializer(many=True)
    cash_variance_pesewas = serializers.IntegerField(help_text=PESEWAS)
    order_number_gaps = OrderNumberGapSerializer(many=True)


# ---------------------------------------------------------------- 2. today


class TodaySerializer(serializers.Serializer):
    """The service so far, live from the projections. Today is not rolled up until after cutover."""

    business_date = serializers.DateField()
    money_taken_pesewas = serializers.IntegerField(help_text=MONEY_TAKEN)
    covers = serializers.IntegerField(help_text="Σ party size of the bills settled today.")
    bills_settled = serializers.IntegerField()
    average_bill_pesewas = serializers.IntegerField(
        help_text="Money taken ÷ bills settled, integer pesewas, floored. Never a float."
    )
    open_bills = serializers.IntegerField(help_text="Bills still owing money right now.")
    open_balance_pesewas = serializers.IntegerField(
        help_text=f"Still to be collected on open bills. {PESEWAS}"
    )
    orders_closed = serializers.IntegerField()


# ---------------------------------------------------------------- 3. patterns


class HourlyMoneySerializer(serializers.Serializer):
    hour = serializers.IntegerField(help_text="Hour 0–23 in the restaurant's own timezone.")
    money_taken_pesewas = serializers.IntegerField(help_text=MONEY_TAKEN)


class BestSellerSerializer(serializers.Serializer):
    name = serializers.CharField(help_text="The name snapshotted onto the line when it was ordered.")
    quantity = serializers.IntegerField()
    value_pesewas = serializers.IntegerField(help_text=f"Σ line totals. {PESEWAS}")


class StationTimingSerializer(serializers.Serializer):
    station = serializers.CharField()
    average_seconds = serializers.IntegerField(help_text="Acknowledged → ready, mean over the window.")
    lines = serializers.IntegerField()


class PatternsSerializer(serializers.Serializer):
    date_from = serializers.DateField(source="from")
    date_to = serializers.DateField(source="to")
    money_taken_pesewas = serializers.IntegerField(help_text=MONEY_TAKEN)
    money_taken_by_hour = HourlyMoneySerializer(many=True)
    payment_method_mix = serializers.DictField(
        child=serializers.IntegerField(),
        help_text=f"Payment method → money taken. {PESEWAS}",
    )
    best_sellers_by_value = BestSellerSerializer(many=True)
    station_timing = StationTimingSerializer(many=True)


# ---------------------------------------------------------------- 4. the event log


class EventLogRowSerializer(serializers.Serializer):
    seq = serializers.IntegerField(help_text="Per restaurant, gapless. Cursor for the next page.")
    type = serializers.CharField()
    aggregate_type = serializers.CharField()
    aggregate_id = serializers.UUIDField()
    order_id = serializers.UUIDField(allow_null=True)
    actor_id = serializers.UUIDField(allow_null=True)
    actor = serializers.CharField(allow_null=True)
    actor_role = serializers.CharField()
    authorised_by = serializers.CharField(
        allow_null=True, help_text="The manager who authorised the override, where there was one."
    )
    reason_code = serializers.CharField(allow_null=True)
    flagged = serializers.BooleanField(
        help_text="Rendered distinctly in the owner's log. Derived from the event type, never stored; "
        "a void counts only once the kitchen has acknowledged the order."
    )
    created_at = serializers.DateTimeField(help_text="Server time. Authoritative.")
    payload = serializers.DictField()


class EventLogSerializer(serializers.Serializer):
    events = EventLogRowSerializer(many=True)
    next_cursor = serializers.IntegerField(
        allow_null=True, help_text="Pass as `cursor` for the next page. Null on the last page."
    )
    has_more = serializers.BooleanField()


# ---------------------------------------------------------------- the rollup


class DailySalesSerializer(serializers.Serializer):
    business_date = serializers.DateField()
    money_taken_pesewas = serializers.IntegerField(help_text=MONEY_TAKEN)
    covers = serializers.IntegerField()
    orders_closed = serializers.IntegerField()
    orders_voided = serializers.IntegerField(help_text="Every void, before or after acknowledgement.")
    void_value_pesewas = serializers.IntegerField(
        help_text=f"Value of voids after acknowledgement only — food that was cooked. {PESEWAS}"
    )
    discount_pesewas = serializers.IntegerField(
        help_text=f"Money given away: discounts and comps together. {PESEWAS}"
    )
    cash_variance_pesewas = serializers.IntegerField(
        help_text=f"Σ shift variances. Negative is a short drawer. {PESEWAS}"
    )
    computed_at = serializers.DateTimeField()


class DailySalesListSerializer(serializers.Serializer):
    days = DailySalesSerializer(many=True)
    money_taken_pesewas = serializers.IntegerField(help_text=f"{MONEY_TAKEN} Summed over the window.")
    covers = serializers.IntegerField()
