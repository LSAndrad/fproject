"""The fixed set of categories and how each one counts in the monthly closing."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Kind(StrEnum):
    EXPENSE = "expense"
    INCOME = "income"
    # Money set aside (investments, savings): part of what is left, not spent.
    SAVINGS = "savings"
    # Money moving between your own accounts: neither income nor expense.
    TRANSFER = "transfer"
    # Paying a credit card bill from checking. Replaced by the bill's items when
    # the bill is imported; counted as one opaque expense when it is not.
    CARD_BILL = "card_bill"


class Scope(StrEnum):
    PERSONAL = "personal"
    HOUSEHOLD = "household"


@dataclass(frozen=True, slots=True)
class Category:
    key: str
    label: str
    kind: Kind


CATEGORIES: tuple[Category, ...] = (
    Category("housing", "Housing", Kind.EXPENSE),
    Category("groceries", "Groceries", Kind.EXPENSE),
    Category("dining_out", "Dining out", Kind.EXPENSE),
    Category("transport", "Transport", Kind.EXPENSE),
    Category("health", "Health", Kind.EXPENSE),
    Category("leisure", "Leisure", Kind.EXPENSE),
    Category("subscriptions", "Subscriptions", Kind.EXPENSE),
    Category("clothing", "Clothing", Kind.EXPENSE),
    Category("education", "Education", Kind.EXPENSE),
    Category("gifts", "Gifts and donations", Kind.EXPENSE),
    Category("household_items", "Household items", Kind.EXPENSE),
    Category("pets", "Pets", Kind.EXPENSE),
    Category("taxes_fees", "Taxes and fees", Kind.EXPENSE),
    Category("other", "Other", Kind.EXPENSE),
    Category("income", "Income", Kind.INCOME),
    Category("investment", "Investments and savings", Kind.SAVINGS),
    Category("internal_transfer", "Internal transfer", Kind.TRANSFER),
    Category("card_bill", "Credit card bill payment", Kind.CARD_BILL),
)

BY_KEY: dict[str, Category] = {c.key: c for c in CATEGORIES}


def get(key: str) -> Category:
    try:
        return BY_KEY[key]
    except KeyError:
        raise ValueError(f"unknown category {key!r}") from None
