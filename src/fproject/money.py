"""Formatting of integer cents for display."""


def format_brl(cents: int) -> str:
    """Format cents as Brazilian reais, e.g. -123456 -> '-R$ 1.234,56'."""
    sign = "-" if cents < 0 else ""
    reais, centavos = divmod(abs(cents), 100)
    return f"{sign}R$ {reais:,}".replace(",", ".") + f",{centavos:02d}"
