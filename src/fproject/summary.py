"""Monthly summary of one statement: what came in, what went out, and where."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from fproject.domain import Statement


@dataclass(frozen=True, slots=True)
class Payee:
    label: str
    total_cents: int
    count: int


@dataclass(frozen=True, slots=True)
class MonthlySummary:
    statement: Statement
    top_outflows: list[Payee]


def payee_label(description: str, details: str | None) -> str:
    return description if details is None else f"{description} · {details}"


def summarize(statement: Statement, top: int = 10) -> MonthlySummary:
    """Group outflows by payee and keep the largest ones.

    Until categorization exists, the payee (description plus details) is the
    best answer to "where is the money going".
    """
    totals: dict[str, int] = defaultdict(int)
    counts: dict[str, int] = defaultdict(int)
    for t in statement.transactions:
        if t.amount_cents < 0:
            label = payee_label(t.description, t.details)
            totals[label] += t.amount_cents
            counts[label] += 1
    payees = [Payee(label, totals[label], counts[label]) for label in totals]
    # Most negative first; label breaks ties so the output is stable.
    payees.sort(key=lambda p: (p.total_cents, p.label))
    return MonthlySummary(statement, payees[:top])
