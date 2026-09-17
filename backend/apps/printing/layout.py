"""
Column arithmetic for a thermal roll. No ESC/POS here — just strings.

Everything printed is ASCII. Thermal printers negotiate a code page per byte range and the cedi
sign (U+20B5) is in none of them, so money renders as `GHS 75.00`. `format_pesewas` in
`apps.core.money` is for email and the screen; paper gets `money()` below.
"""

from __future__ import annotations

import unicodedata

# 80mm roll, font A. The 58mm roll is 32; pass the width through if RENZY ever buys one.
PAPER_WIDTH = 42

_TRANSLITERATIONS = {
    "\u20b5": "GHS",  # ₵
    "\u2018": "'",
    "\u2019": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u2013": "-",
    "\u2014": "-",
    "\u2026": "...",
}


def ascii_only(text: str) -> str:
    """Fold anything the printer cannot render. Never emits a byte above 0x7E."""
    for source, replacement in _TRANSLITERATIONS.items():
        text = text.replace(source, replacement)
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return "".join(c if 0x20 <= ord(c) <= 0x7E else "?" for c in stripped)


def money(pesewas: int) -> str:
    """7500 -> '75.00'. Integer in, string out, at the very last moment."""
    sign = "-" if pesewas < 0 else ""
    cedis, remainder = divmod(abs(int(pesewas)), 100)
    return f"{sign}{cedis:,}.{remainder:02d}"


def rule(char: str = "-", width: int = PAPER_WIDTH) -> str:
    return char * width


def centre(text: str, width: int = PAPER_WIDTH) -> str:
    """Centre in software so a line stays centred even inside a left-aligned block."""
    trimmed = ascii_only(text)[:width]
    return trimmed.center(width).rstrip()


def columns(left: str, right: str, width: int = PAPER_WIDTH) -> str:
    """`left` truncated so `right` always survives — the amount matters more than the name."""
    right = ascii_only(right)
    room = max(0, width - len(right) - 1)
    left = ascii_only(left)[:room]
    return f"{left}{' ' * (width - len(left) - len(right))}{right}"


def wrap(text: str, width: int = PAPER_WIDTH, indent: str = "") -> list[str]:
    """Greedy wrap with a hanging indent. Long unbreakable words are hard-split, not dropped."""
    body = ascii_only(text).split()
    if not body:
        return []
    room = max(1, width - len(indent))
    lines: list[str] = []
    current = ""
    for word in body:
        while len(word) > room:
            if current:
                lines.append(current)
                current = ""
            lines.append(word[:room])
            word = word[room:]
        if not current:
            current = word
        elif len(current) + 1 + len(word) <= room:
            current = f"{current} {word}"
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return [f"{indent}{line}" for line in lines]
