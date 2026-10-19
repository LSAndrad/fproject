"""Core domain model: accounts, monthly statements and their transactions.

Money is always an integer number of cents, signed: negative is an outflow,
positive is an inflow. Floats are rejected so rounding errors cannot creep in.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from uuid import UUID, uuid4

_MONTH_PATTERN = re.compile(r"(\d{4})-(\d{2})")


def _require_cents(name: str, value: object) -> None:
    # bool is a subclass of int, so it must be excluded explicitly.
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{name} must be an int number of cents, got {type(value).__name__}")


@dataclass(frozen=True, order=True, slots=True)
class Month:
    """A calendar month, e.g. the reference month of a statement."""

    year: int
    month: int

    def __post_init__(self) -> None:
        if not 1 <= self.month <= 12:
            raise ValueError(f"month must be between 1 and 12, got {self.month}")

    @classmethod
    def parse(cls, text: str) -> Month:
        """Parse a month in ``YYYY-MM`` format."""
        match = _MONTH_PATTERN.fullmatch(text)
        if match is None:
            raise ValueError(f"expected YYYY-MM, got {text!r}")
        return cls(int(match[1]), int(match[2]))

    def __str__(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"


class AccountKind(StrEnum):
    CHECKING = "checking"
    CREDIT_CARD = "credit_card"


class Direction(StrEnum):
    INFLOW = "inflow"
    OUTFLOW = "outflow"


@dataclass(frozen=True, slots=True, kw_only=True)
class Account:
    """A financial account held by someone at some institution."""

    owner: str
    institution: str
    kind: AccountKind
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if not self.owner.strip():
            raise ValueError("owner must not be blank")
        if not self.institution.strip():
            raise ValueError("institution must not be blank")


@dataclass(frozen=True, slots=True, kw_only=True)
class Transaction:
    """A single line of a statement.

    The id is generated here, never taken from the bank: bank-provided
    identifiers are unreliable and cannot be trusted as keys.
    """

    posted_on: date
    description: str
    amount_cents: int
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        _require_cents("amount_cents", self.amount_cents)
        if self.amount_cents == 0:
            raise ValueError("amount_cents must not be zero")
        if not self.description.strip():
            raise ValueError("description must not be blank")

    @property
    def direction(self) -> Direction:
        return Direction.INFLOW if self.amount_cents > 0 else Direction.OUTFLOW


@dataclass(frozen=True, slots=True, kw_only=True)
class Statement:
    """Everything an account recorded in one reference month.

    A statement is the unit of import: there is at most one per account per
    month. Transactions keep the order in which they appear in the source.
    """

    account_id: UUID
    month: Month
    opening_balance_cents: int
    closing_balance_cents: int
    transactions: tuple[Transaction, ...]
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        _require_cents("opening_balance_cents", self.opening_balance_cents)
        _require_cents("closing_balance_cents", self.closing_balance_cents)
        # Accept any iterable but store an immutable tuple.
        object.__setattr__(self, "transactions", tuple(self.transactions))

    @property
    def inflow_cents(self) -> int:
        return sum(t.amount_cents for t in self.transactions if t.amount_cents > 0)

    @property
    def outflow_cents(self) -> int:
        return sum(t.amount_cents for t in self.transactions if t.amount_cents < 0)

    @property
    def net_cents(self) -> int:
        return self.inflow_cents + self.outflow_cents
