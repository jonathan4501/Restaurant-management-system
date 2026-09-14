from apps.core.roles import AggregateType
from apps.orders.events import (
    AGGREGATE_OF,
    PAYLOADS,
    EventType,
    OrderVoided,
    SessionOpened,
    is_flagged,
)


def test_payload_roundtrip_is_plain_json() -> None:
    p = SessionOpened(table_id="t", table_number="7", party_size=None)
    assert p.to_payload() == {"table_id": "t", "table_number": "7", "party_size": None}
    assert PAYLOADS[EventType.SESSION_OPENED] is SessionOpened
    assert SessionOpened.event_type is EventType.SESSION_OPENED


def test_aggregate_mapping_is_sane() -> None:
    assert AGGREGATE_OF[EventType.ORDER_SUBMITTED] is AggregateType.ORDER
    assert AGGREGATE_OF[EventType.ITEM_86ED] is AggregateType.MENU_ITEM
    assert AGGREGATE_OF[EventType.PAYMENT_RECORDED] is AggregateType.SESSION
    assert AGGREGATE_OF[EventType.PIN_FAILED] is AggregateType.DEVICE
    assert AGGREGATE_OF[EventType.SHIFT_CLOSED] is AggregateType.SHIFT
    assert AGGREGATE_OF[EventType.MANAGER_AUTHORISED] is AggregateType.STAFF


def test_flagging() -> None:
    assert is_flagged("DISCOUNT_APPLIED")
    assert is_flagged("PIN_FAILED")
    assert not is_flagged("ORDER_SERVED")
    assert not is_flagged("ORDER_VOIDED", OrderVoided(1, "SUBMITTED", 5000).to_payload())
    assert is_flagged("ORDER_VOIDED", OrderVoided(1, "PREPARING", 5000).to_payload())
    assert not is_flagged("NOT_AN_EVENT")
