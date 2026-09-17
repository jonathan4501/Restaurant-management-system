"""
ESC/POS byte rendering (WS12). Pure functions: a dict in, bytes out.

Both renderers are deterministic — they take every timestamp from the dict they are given, never
from the clock — so the golden-file tests in tests/test_render.py compare exact bytes.

The receipt is titled "Sales record". It is not an invoice and it carries no tax line, no VAT, no
NHIL/GETFund/Tourism levy and no GRA fiscal field (ADR-0005). There is nothing to print: the menu
price is what the guest pays.

Amounts are formatted from integer pesewas at this last moment only. The cedi sign (GH\u20b5) is not in
any ESC/POS code page a cheap thermal printer supports, so paper says "GHS".
"""

from __future__ import annotations

import textwrap
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from escpos.printer import Dummy

# 80mm paper, font A: 42 glyphs to the line. Everything is laid out against this.
WIDTH = 42
DEFAULT_TZ = "Africa/Accra"

# The guest should read a method, not an enum member.
METHOD_LABELS = {
    "CASH": "Cash",
    "MOMO_MTN": "MoMo MTN",
    "MOMO_TELECEL": "MoMo Telecel",
    "MOMO_AT": "MoMo AT",
    "CARD": "Card",
    "BANK": "Bank transfer",
}


def amount(pesewas: int) -> str:
    """Integer pesewas -> '75.00'. The only place printing turns money into a string."""
    cedis, rest = divmod(abs(int(pesewas)), 100)
    sign = "-" if int(pesewas) < 0 else ""
    return f"{sign}{cedis:,}.{rest:02d}"


def method_label(method: str) -> str:
    return METHOD_LABELS.get(str(method).upper(), str(method).replace("_", " ").title())


def _row(left: str, right: str, width: int = WIDTH) -> str:
    """'Jollof Rice            75.00' — left text, right amount, padded to the paper width."""
    room = width - len(right)
    if room < 1:
        return right[:width]
    return f"{left[: room - 1].ljust(room)}{right}"


def _wrap(text: str, width: int, subsequent_indent: str = "    ") -> list[str]:
    """A dish name too long for the paper continues on the next line; it is never cut short."""
    wrapped = textwrap.wrap(
        text,
        width=width,
        subsequent_indent=subsequent_indent,
        break_long_words=True,
        break_on_hyphens=False,
    )
    return wrapped or [""]


def _priced_rows(label: str, right: str, width: int = WIDTH) -> list[str]:
    """A priced line: amount hard right on the first row, the name wrapping under it if it must."""
    room = width - len(right) - 1
    lines = _wrap(label, room)
    rows = [f"{lines[0].ljust(width - len(right))}{right}"]
    rows.extend(lines[1:])
    return rows


def _rule(char: str = "-") -> str:
    return char * WIDTH


def _local_time(iso: str | None, tz: str) -> str:
    """Server ISO timestamp -> '19:42' in restaurant-local time. Server clock is authoritative."""
    if not iso:
        return "--:--"
    parsed = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return parsed.astimezone(ZoneInfo(tz)).strftime("%H:%M")


def _local_datetime(iso: str | None, tz: str) -> str:
    if not iso:
        return "--"
    parsed = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return parsed.astimezone(ZoneInfo(tz)).strftime("%d %b %Y  %H:%M")


def _modifier_lines(modifiers: list[dict[str, Any]]) -> list[str]:
    """Modifiers are indented under their line so the cook reads the dish first."""
    out = []
    for modifier in modifiers or []:
        name = str(modifier.get("name", "")).strip()
        if name:
            out.append(f"  + {name}")
    return out


# ------------------------------------------------------------------ kitchen ticket


def render_kitchen_ticket(
    envelope: dict[str, Any], *, station: str | None = None, tz: str = DEFAULT_TZ
) -> bytes:
    """
    The paper backup for the kitchen display. Takes an ORDER_SUBMITTED SSE envelope as-is.

    `station` prints only the lines for that prep station, so a restaurant with a grill printer and
    a bar printer gets one ticket each with only its own work on it.
    """
    payload = envelope.get("payload") or {}
    printer = Dummy()

    printer.set(align="center", bold=True, double_width=True, double_height=True)
    printer.textln(f"#{payload.get('order_number', '?')}")

    printer.set(align="center", bold=True, double_width=False, double_height=False)
    printer.textln(station or "KITCHEN")

    printer.set(align="left", bold=False)
    printer.textln(_rule("="))
    printer.textln(
        _row(
            f"Table {payload.get('table_number', '?')}", _local_time(envelope.get("created_at"), tz)
        )
    )
    origin = str(payload.get("origin") or "").strip()
    if origin and origin != "WAITER":
        printer.textln(f"Ordered: {origin.replace('_', ' ').title()}")
    printer.textln(_rule("="))

    lines = [
        line
        for line in payload.get("lines") or []
        if station is None or line.get("prep_station") == station
    ]
    for line in lines:
        printer.set(bold=True)
        for row in _wrap(f"{line.get('quantity', 1)} x {line.get('name', '')}", WIDTH):
            printer.textln(row)
        printer.set(bold=False)
        for modifier_line in _modifier_lines(line.get("modifiers") or []):
            printer.textln(modifier_line)
        notes = str(line.get("notes") or "").strip()
        if notes:
            printer.textln(f"  ** {notes}")
        course = line.get("course")
        if isinstance(course, int) and course > 1:
            printer.textln(f"  (course {course})")

    printer.textln(_rule())
    printer.set(align="center")
    # No prices on a kitchen ticket: the cook does not need them and it is one more thing to leak.
    printer.textln(f"{len(lines)} item(s) to cook")
    printer.cut()
    return bytes(printer.output)


# ------------------------------------------------------------------ guest receipt


def render_receipt(bill: dict[str, Any], *, tz: str = DEFAULT_TZ) -> bytes:
    """
    The guest's copy at settlement. Takes the dict from payloads.receipt_payload().

    Deliberately absent: any tax line, any VAT/NHIL/GETFund/levy split, any GRA invoice reference
    or fiscal QR code (ADR-0005). The total is the sum of the menu prices, less discounts.
    """
    printer = Dummy()

    printer.set(align="center", bold=True, double_width=True, double_height=True)
    printer.textln(bill.get("restaurant_name", "RENZY"))
    printer.set(align="center", bold=False, double_width=False, double_height=False)
    for header_line in bill.get("address_lines") or []:
        printer.textln(str(header_line))
    printer.textln("")
    printer.set(bold=True)
    printer.textln("SALES RECORD")
    printer.set(bold=False)
    if bill.get("reprint"):
        printer.textln("* REPRINT *")

    printer.set(align="left")
    printer.textln(_rule("="))
    printer.textln(
        _row(
            f"Table {bill.get('table_number', '?')}",
            _local_datetime(bill.get("settled_at") or bill.get("printed_at"), tz),
        )
    )
    printer.textln(f"Bill: {str(bill.get('session_id', ''))[:8]}")
    served_by = str(bill.get("served_by") or "").strip()
    if served_by:
        printer.textln(f"Served by: {served_by}")
    printer.textln(_rule("="))

    for line in bill.get("lines") or []:
        quantity = int(line.get("quantity", 1))
        name = line.get("name_snapshot", line.get("name", ""))
        for row in _priced_rows(f"{quantity} x {name}", amount(line.get("line_total_pesewas", 0))):
            printer.textln(row)
        for modifier_line in _modifier_lines(line.get("modifiers") or []):
            printer.textln(modifier_line)

    printer.textln(_rule())
    printer.textln(_row("Subtotal", amount(bill.get("subtotal_pesewas", 0))))
    for discount in bill.get("discounts") or []:
        label = str(discount.get("label") or "Discount")
        printer.textln(_row(label, f"-{amount(discount.get('discount_pesewas', 0))}"))

    printer.set(bold=True, double_height=True)
    printer.textln(_row("TOTAL GHS", amount(bill.get("total_pesewas", 0)), WIDTH // 2))
    printer.set(bold=False, double_height=False)

    printer.textln(_rule())
    for payment in bill.get("payments") or []:
        reference = str(payment.get("external_reference") or "").strip()
        printer.textln(
            _row(method_label(payment.get("method", "")), amount(payment.get("amount_pesewas", 0)))
        )
        if reference:
            printer.textln(f"  ref {reference}")

    paid = int(bill.get("paid_pesewas", 0))
    printer.textln(_row("Paid", amount(paid)))
    change = int(bill.get("change_pesewas", 0) or 0)
    if change:
        printer.textln(_row("Change", amount(change)))
    balance = int(bill.get("balance_pesewas", 0) or 0)
    if balance:
        printer.textln(_row("Balance due", amount(balance)))

    printer.textln(_rule("="))
    printer.set(align="center")
    printer.textln("Thank you")
    printer.textln("")
    printer.cut()
    return bytes(printer.output)
