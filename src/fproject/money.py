"""Conversion between integer cents and Brazilian real text."""

import re

_BRL_PATTERN = re.compile(r"(-?)\s*(?:R\$)?\s*(-?)\s*(\d{1,3}(?:\.\d{3})*|\d+),(\d{2})")


def format_brl(cents: int) -> str:
    """Format cents as Brazilian reais, e.g. -123456 -> '-R$ 1.234,56'."""
    sign = "-" if cents < 0 else ""
    reais, centavos = divmod(abs(cents), 100)
    return f"{sign}R$ {reais:,}".replace(",", ".") + f",{centavos:02d}"


def parse_brl(text: str) -> int:
    """Parse Brazilian real text into cents, e.g. '-R$ 1.234,56' -> -123456.

    Accepts the sign before or after the currency symbol and an optional
    thousands separator. Anything else is rejected rather than guessed.
    """
    match = _BRL_PATTERN.fullmatch(text.strip())
    if match is None:
        raise ValueError(f"not a Brazilian real amount: {text!r}")
    sign_before, sign_after, reais, centavos = match.groups()
    if sign_before and sign_after:
        raise ValueError(f"not a Brazilian real amount: {text!r}")
    cents = int(reais.replace(".", "")) * 100 + int(centavos)
    return -cents if sign_before or sign_after else cents
