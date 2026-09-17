"""
What the top and bottom of a piece of RENZY paper says.

Kept apart from the renderers so changing the address does not touch the layout code, and so the
golden-file tests have one obvious thing to patch.
"""

from __future__ import annotations

# 42 columns is font A on an 80mm roll, which is what the kitchen and front printers are.
RECEIPT_WIDTH = 42

HEADER_NAME = "RENZY"
HEADER_LINES: tuple[str, ...] = ("Shiashi, Accra", "Ghana")

# ADR-0005: this is a record of what was charged and collected, not a tax invoice. The word
# "Invoice" and anything resembling a VAT or fiscal line must never appear on it.
RECEIPT_TITLE = "Sales record"

FOOTER_LINES: tuple[str, ...] = ("Thank you", "Please come again")

# The cedi sign U+20B5 has no ESC/POS code page, so a thermal printer renders it as "?".
# "GHS" is the ISO code and prints identically on every roll we will ever buy.
CURRENCY = "GHS"

# Restaurant-local time. Accra is UTC+0 all year, but deriving it beats assuming it.
TIMEZONE = "Africa/Accra"
