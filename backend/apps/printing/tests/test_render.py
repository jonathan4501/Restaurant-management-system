"""
Byte-level golden tests for the two things that reach paper.

The renderers take every timestamp from their input, so these comparisons are exact: if a byte
changes, a real printer's output changed. Regenerate the goldens deliberately with

    RENZY_REGENERATE_GOLDENS=1 pytest apps/printing/tests/test_render.py

and read `git diff --stat` on the .bin files before committing.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from apps.printing.render import WIDTH, amount, method_label, render_kitchen_ticket, render_receipt

GOLDENS = Path(__file__).parent / "goldens"
REGENERATE = os.environ.get("RENZY_REGENERATE_GOLDENS") == "1"


def golden(name: str, produced: bytes) -> None:
    path = GOLDENS / name
    if REGENERATE or not path.exists():
        GOLDENS.mkdir(parents=True, exist_ok=True)
        path.write_bytes(produced)
        if not REGENERATE:
            pytest.fail(f"Golden {name} did not exist; it has been written. Review and re-run.")
        return
    expected = path.read_bytes()
    assert produced == expected, (
        f"{name} changed. If the new output is correct, re-run with "
        f"RENZY_REGENERATE_GOLDENS=1 and review the diff.\n"
        f"Expected {len(expected)} bytes, got {len(produced)}."
    )


TICKET_ENVELOPE = {
    "id": "0192f5aa-0000-7000-8000-00000000abcd",
    "type": "ORDER_SUBMITTED",
    "aggregate_type": "ORDER",
    "aggregate_id": "0192f5aa-0000-7000-8000-00000000000a",
    "order_id": "0192f5aa-0000-7000-8000-00000000000a",
    "created_at": "2026-09-16T19:42:00Z",
    "payload": {
        "order_number": 42,
        "table_number": "7",
        "origin": "WAITER",
        "lines": [
            {
                "name": "Jollof Rice with Grilled Chicken",
                "quantity": 2,
                "prep_station": "KITCHEN",
                "modifiers": [{"name": "Extra shito"}, {"name": "No salad"}],
                "notes": "very little pepper",
                "course": 1,
                "line_total_pesewas": 15000,
            },
            {
                "name": "Club Beer",
                "quantity": 3,
                "prep_station": "BAR",
                "modifiers": [],
                "notes": "",
                "course": 1,
                "line_total_pesewas": 4500,
            },
        ],
        "subtotal_pesewas": 19500,
        "discount_pesewas": 0,
        "total_pesewas": 19500,
    },
}

RECEIPT_BILL = {
    "restaurant_name": "RENZY",
    "address_lines": ["Shiashi, Accra"],
    "session_id": "0192f5aa-0000-7000-8000-00000000cafe",
    "table_number": "7",
    "served_by": "Kofi Mensah",
    "opened_at": "2026-09-16T18:10:00Z",
    "settled_at": "2026-09-16T20:15:00Z",
    "printed_at": "2026-09-16T20:15:04Z",
    "reprint": False,
    "lines": [
        {
            "name_snapshot": "Jollof Rice with Grilled Chicken",
            "quantity": 2,
            "modifiers": [{"name": "Extra shito"}],
            "line_total_pesewas": 15000,
        },
        {
            "name_snapshot": "Club Beer",
            "quantity": 3,
            "modifiers": [],
            "line_total_pesewas": 4500,
        },
    ],
    "discounts": [{"label": "Discount (#42)", "discount_pesewas": 1000}],
    "subtotal_pesewas": 19500,
    "total_pesewas": 18500,
    "payments": [
        {"method": "CASH", "amount_pesewas": 10000, "external_reference": None},
        {"method": "MOMO_MTN", "amount_pesewas": 8500, "external_reference": "MP2609ABC"},
    ],
    "paid_pesewas": 18500,
    "change_pesewas": 500,
    "balance_pesewas": 0,
}


# ------------------------------------------------------------------ goldens


def test_kitchen_ticket_bytes() -> None:
    golden("kitchen_ticket.bin", render_kitchen_ticket(TICKET_ENVELOPE))


def test_kitchen_ticket_for_one_station_bytes() -> None:
    golden("kitchen_ticket_bar.bin", render_kitchen_ticket(TICKET_ENVELOPE, station="BAR"))


def test_receipt_bytes() -> None:
    golden("receipt.bin", render_receipt(RECEIPT_BILL))


def test_receipt_reprint_bytes() -> None:
    golden("receipt_reprint.bin", render_receipt({**RECEIPT_BILL, "reprint": True}))


# ------------------------------------------------------------------ determinism and content


def test_renderers_are_deterministic() -> None:
    """Called twice, byte-identical. A clock read inside a renderer would break this."""
    assert render_kitchen_ticket(TICKET_ENVELOPE) == render_kitchen_ticket(TICKET_ENVELOPE)
    assert render_receipt(RECEIPT_BILL) == render_receipt(RECEIPT_BILL)


def test_ticket_carries_the_order_number_table_and_items() -> None:
    text = render_kitchen_ticket(TICKET_ENVELOPE).decode("cp437", errors="replace")
    assert "#42" in text
    assert "Table 7" in text
    assert "19:42" in text  # 19:42 UTC is 19:42 in Accra; UTC+0 all year
    assert "2 x Jollof Rice with Grilled Chicken" in text
    assert "+ Extra shito" in text
    assert "** very little pepper" in text


def test_station_ticket_only_carries_that_station() -> None:
    text = render_kitchen_ticket(TICKET_ENVELOPE, station="BAR").decode("cp437", errors="replace")
    assert "3 x Club Beer" in text
    assert "Jollof" not in text
    assert "BAR" in text


def test_ticket_prints_no_prices() -> None:
    """The cook does not need money on paper, and it is one more thing to leak."""
    text = render_kitchen_ticket(TICKET_ENVELOPE).decode("cp437", errors="replace")
    assert "150.00" not in text
    assert "195.00" not in text


def test_receipt_is_a_sales_record_with_no_tax_and_no_fiscal_fields() -> None:
    """ADR-0005: no tax engine. Nothing on this paper may imply one."""
    text = render_receipt(RECEIPT_BILL).decode("cp437", errors="replace").upper()
    assert "SALES RECORD" in text
    for forbidden in (
        "VAT",
        "NHIL",
        "GETFUND",
        "TOURISM",
        "LEVY",
        "TAX",
        "INVOICE",
        "GRA",
        "IRN",
        "FISCAL",
    ):
        assert forbidden not in text, f"receipt must not mention {forbidden} (ADR-0005)"


def test_receipt_totals_and_payments() -> None:
    text = render_receipt(RECEIPT_BILL).decode("cp437", errors="replace")
    assert "195.00" in text  # subtotal
    assert "-10.00" in text  # discount
    assert "185.00" in text  # total and paid
    assert "Cash" in text
    assert "MoMo MTN" in text
    assert "ref MP2609ABC" in text
    assert "Change" in text
    assert "Thank you" in text


def test_receipt_marks_a_reprint() -> None:
    """A reprint must be obvious on the paper: fraud pattern 5 in docs/01-product-spec.md."""
    original = render_receipt(RECEIPT_BILL).decode("cp437", errors="replace")
    reprint = render_receipt({**RECEIPT_BILL, "reprint": True}).decode("cp437", errors="replace")
    assert "REPRINT" not in original
    assert "* REPRINT *" in reprint


def test_receipt_shows_balance_when_the_bill_is_not_settled() -> None:
    part_paid = {
        **RECEIPT_BILL,
        "payments": [{"method": "CASH", "amount_pesewas": 10000, "external_reference": None}],
        "paid_pesewas": 10000,
        "change_pesewas": 0,
        "balance_pesewas": 8500,
    }
    text = render_receipt(part_paid).decode("cp437", errors="replace")
    assert "Balance due" in text
    assert "85.00" in text


def test_long_dish_names_wrap_instead_of_being_cut_off() -> None:
    """The guest must be able to read what they were charged for."""
    name = "Grilled Tilapia with Banku, Pepper Sauce and Fried Yam on the Side"
    bill = {
        **RECEIPT_BILL,
        "lines": [
            {
                "name_snapshot": name,
                "quantity": 1,
                "modifiers": [],
                "line_total_pesewas": 9000,
            }
        ],
    }
    text = render_receipt(bill).decode("cp437", errors="replace")
    for word in name.split():
        assert word.strip(",") in text
    for line in text.splitlines():
        assert len(line) <= WIDTH + 8, f"line overflows the paper: {line!r}"


# ------------------------------------------------------------------ money formatting


@pytest.mark.parametrize(
    ("pesewas", "expected"),
    [
        (0, "0.00"),
        (5, "0.05"),
        (50, "0.50"),
        (100, "1.00"),
        (7500, "75.00"),
        (123456, "1,234.56"),
        (100000000, "1,000,000.00"),
        (-1000, "-10.00"),
    ],
)
def test_amount_formats_integer_pesewas(pesewas: int, expected: str) -> None:
    """Money is int pesewas everywhere and becomes a string only here (CLAUDE.md invariant 1)."""
    assert amount(pesewas) == expected


def test_amount_never_sees_a_float() -> None:
    """Money reaches printing as int pesewas (CLAUDE.md invariant 1); floats round silently."""
    assert amount(7500) == "75.00"


@pytest.mark.parametrize(
    ("method", "expected"),
    [
        ("CASH", "Cash"),
        ("MOMO_MTN", "MoMo MTN"),
        ("MOMO_TELECEL", "MoMo Telecel"),
        ("MOMO_AT", "MoMo AT"),
        ("CARD", "Card"),
        ("BANK", "Bank transfer"),
        ("SOMETHING_NEW", "Something New"),
    ],
)
def test_payment_methods_read_as_words(method: str, expected: str) -> None:
    assert method_label(method) == expected
