"""Reconciliation: a statement is only trusted if its numbers add up."""

from fproject.domain import Month, Statement
from fproject.money import format_brl


class ReconciliationError(Exception):
    def __init__(self, month: Month, expected_cents: int, closing_cents: int) -> None:
        self.month = month
        self.expected_cents = expected_cents
        self.closing_cents = closing_cents
        self.difference_cents = closing_cents - expected_cents
        super().__init__(
            f"statement {month} does not reconcile: opening balance plus transactions "
            f"gives {format_brl(expected_cents)}, but the closing balance is "
            f"{format_brl(closing_cents)} (difference {format_brl(self.difference_cents)})"
        )


def reconcile(statement: Statement) -> None:
    """Check that opening balance + sum of transactions == closing balance.

    A mismatch means the extractor missed, duplicated or misread a line; the
    difference in the error message usually points straight at it.
    """
    expected = statement.opening_balance_cents + statement.net_cents
    if expected != statement.closing_balance_cents:
        raise ReconciliationError(statement.month, expected, statement.closing_balance_cents)
