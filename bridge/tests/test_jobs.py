"""
Which events produce paper, on which printer, and under which key.

`job_key` is the load-bearing value in this file: it is what the store's primary key rejects on a
replay, so if it is ever derived from anything the server can change between deliveries, a
reconnect double-prints.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from conftest import make_config

from renzy_bridge.config import Config
from renzy_bridge.jobs import jobs_for

EVENT_ID = "0192f5aa-0000-7000-8000-00000000abcd"
ORDER_ID = "0192f5aa-0000-7000-8000-00000000000a"
SESSION_ID = "0192f5aa-0000-7000-8000-00000000cafe"


def submitted(**payload: Any) -> dict[str, Any]:
    """An ORDER_SUBMITTED envelope in the shape apps.orders.models.OrderEvent.to_envelope emits."""
    return {
        "id": EVENT_ID,
        "seq": 412,
        "type": "ORDER_SUBMITTED",
        "aggregate_type": "ORDER",
        "aggregate_id": ORDER_ID,
        "order_id": ORDER_ID,
        "created_at": "2026-09-16T19:42:00Z",
        "payload": {
            "order_number": 42,
            "table_number": "7",
            "lines": [
                {"name": "Jollof Rice", "prep_station": "KITCHEN", "quantity": 2},
                {"name": "Club Beer", "prep_station": "BAR", "quantity": 3},
            ],
            **payload,
        },
    }


def settled(event_type: str = "SESSION_SETTLED", **payload: Any) -> dict[str, Any]:
    return {
        "id": EVENT_ID,
        "seq": 500,
        "type": event_type,
        "aggregate_type": "SESSION",
        "aggregate_id": SESSION_ID,
        "order_id": None,
        "payload": {"table_number": "7", **payload},
    }


# ------------------------------------------------------------------ what prints at all


def test_only_three_event_types_produce_paper(config: Config) -> None:
    for event_type in ("ORDER_ACKNOWLEDGED", "ITEM_READY", "PAYMENT_RECORDED", "ORDER_VOIDED"):
        assert jobs_for({**submitted(), "type": event_type}, config) == []


def test_an_envelope_with_no_event_id_produces_nothing(config: Config) -> None:
    """No id means no stable job_key, and a job without one could print twice."""
    envelope = submitted()
    del envelope["id"]
    assert jobs_for(envelope, config) == []


def test_an_order_event_with_no_order_id_produces_nothing(config: Config) -> None:
    envelope = submitted()
    envelope["order_id"] = None
    envelope["aggregate_id"] = None
    assert jobs_for(envelope, config) == []


# ------------------------------------------------------------------ kitchen tickets


def test_a_single_printer_kitchen_gets_one_whole_ticket(config: Config) -> None:
    """No [stations] in the config is the normal RENZY setup: one printer, one unsplit ticket."""
    (job,) = jobs_for(submitted(), config)
    assert job.printer == "kitchen"
    assert job.fetch_path == f"/api/v1/print/tickets/{ORDER_ID}"
    assert "station=" not in job.fetch_path
    assert job.description == "ticket #42 table 7"


def test_station_printers_split_the_ticket_one_per_station(tmp_path: Path) -> None:
    config = make_config(
        tmp_path,
        printers={"kitchen": "127.0.0.1:9100", "bar": "127.0.0.1:9102", "front": "127.0.0.1:9101"},
        stations={"KITCHEN": "kitchen", "BAR": "bar"},
    )
    jobs = sorted(jobs_for(submitted(), config), key=lambda j: j.printer)
    assert [j.printer for j in jobs] == ["bar", "kitchen"]
    assert [j.fetch_path for j in jobs] == [
        f"/api/v1/print/tickets/{ORDER_ID}?station=BAR",
        f"/api/v1/print/tickets/{ORDER_ID}?station=KITCHEN",
    ]
    assert len({j.job_key for j in jobs}) == 2


def test_a_station_with_no_printer_of_its_own_falls_back_to_the_kitchen(tmp_path: Path) -> None:
    """A misconfigured station must still produce paper somewhere rather than vanish."""
    config = make_config(
        tmp_path,
        printers={"kitchen": "127.0.0.1:9100", "front": "127.0.0.1:9101"},
        stations={"KITCHEN": "kitchen"},
    )
    jobs = jobs_for(submitted(), config)
    assert {j.printer for j in jobs} == {"kitchen"}
    assert f"/api/v1/print/tickets/{ORDER_ID}?station=BAR" in {j.fetch_path for j in jobs}


def test_station_order_does_not_change_the_job_keys(tmp_path: Path) -> None:
    """
    A replayed event must yield byte-identical keys. If the station list were emitted in the
    envelope's line order rather than sorted, a re-render with reordered lines would double-print.
    """
    config = make_config(
        tmp_path,
        printers={"kitchen": "127.0.0.1:9100", "bar": "127.0.0.1:9102"},
        stations={"KITCHEN": "kitchen", "BAR": "bar"},
    )
    forward = submitted()
    reversed_lines = submitted()
    reversed_lines["payload"]["lines"] = list(reversed(reversed_lines["payload"]["lines"]))
    assert {j.job_key for j in jobs_for(forward, config)} == {
        j.job_key for j in jobs_for(reversed_lines, config)
    }


# ------------------------------------------------------------------ receipts


def test_settlement_prints_a_receipt_on_the_front_printer(config: Config) -> None:
    (job,) = jobs_for(settled(), config)
    assert job.printer == "front"
    assert job.fetch_path == f"/api/v1/print/receipts/{SESSION_ID}"
    assert job.description == "receipt table 7"


def test_a_receipt_request_is_marked_as_a_reprint(config: Config) -> None:
    """Fraud pattern 5: paper produced a second time has to say so, and the server decides."""
    (job,) = jobs_for(settled("RECEIPT_REQUESTED", reprint=True), config)
    assert job.fetch_path.endswith("?reprint=1")
    assert job.description == "receipt reprint table 7"


def test_the_servers_reprint_flag_wins_over_the_event_type(config: Config) -> None:
    (job,) = jobs_for(settled("SESSION_SETTLED", reprint=True), config)
    assert job.fetch_path.endswith("?reprint=1")


def test_a_receipt_falls_back_to_the_kitchen_printer_when_there_is_no_front(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path, printers={"kitchen": "127.0.0.1:9100"})
    (job,) = jobs_for(settled(), config)
    assert job.printer == "kitchen"


# ------------------------------------------------------------------ idempotency


def test_the_same_event_always_yields_the_same_job_keys(config: Config) -> None:
    """This is the reconnect guarantee: replay produces keys the store already holds."""
    first = jobs_for(submitted(), config)
    second = jobs_for(submitted(), config)
    assert [j.job_key for j in first] == [j.job_key for j in second]


def test_the_job_key_ignores_everything_the_server_may_re_render(config: Config) -> None:
    """
    Only the event id, the printer and the station are allowed in the key. A replay that arrives
    with a different seq, a re-rendered table number or an extra field must not print again.
    """
    replayed = submitted(table_number="8")
    replayed["seq"] = 999
    replayed["created_at"] = "2026-09-16T19:45:00Z"
    assert [j.job_key for j in jobs_for(replayed, config)] == [
        j.job_key for j in jobs_for(submitted(), config)
    ]


def test_a_settlement_and_a_later_reprint_are_two_pieces_of_paper(config: Config) -> None:
    """Different events, different ids — the guest asked twice and gets two copies."""
    settlement = settled("SESSION_SETTLED")
    reprint = settled("RECEIPT_REQUESTED", reprint=True)
    reprint["id"] = "0192f5aa-0000-7000-8000-00000000beef"
    assert jobs_for(settlement, config)[0].job_key != jobs_for(reprint, config)[0].job_key


def test_the_bridge_never_puts_money_in_a_job(config: Config) -> None:
    """
    CLAUDE.md invariant 1. The bridge moves opaque bytes; totals are rendered server-side where
    they are golden-tested. A price reaching a job_key or a description would mean the Pi is
    formatting money, and there is no pesewas-to-cedis helper here to do it correctly.
    """
    envelope = submitted(subtotal_pesewas=19500, total_pesewas=18500, discount_pesewas=1000)
    for job in jobs_for(envelope, config) + jobs_for(settled(total_pesewas=18500), config):
        text = f"{job.job_key} {job.fetch_path} {job.description}"
        assert "195" not in text and "185" not in text
        assert "pesewas" not in text
