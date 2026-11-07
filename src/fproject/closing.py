"""Monthly closing: what came in, where it went, and what was left.

This is the consumption view over every account of a month. Rules:

- Income is what you categorized as income; other inflows in an expense
  category (a friend paying you back) reduce that category instead.
- A credit card bill payment in checking is replaced by the bill's items
  when that owner's card statement for the month is imported. Otherwise it
  counts as one opaque expense, so no money silently disappears.
- Internal transfers count nowhere. Money sent to investments is "saved":
  part of what was left over, not spending.
- Uncategorized outflows still count as expenses (under "Uncategorized"),
  so the leftover is never overstated while you are still reviewing.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from fproject import categories
from fproject.categories import Kind, Scope
from fproject.categorization import Entry
from fproject.domain import AccountKind, Month

UNCATEGORIZED = "uncategorized"


@dataclass(frozen=True, slots=True)
class CategoryTotal:
    key: str
    label: str
    spent_cents: int
    count: int


@dataclass(frozen=True, slots=True)
class AccountFlow:
    owner: str
    institution: str
    kind: AccountKind
    inflow_cents: int
    outflow_cents: int


@dataclass(slots=True)
class Closing:
    month: Month
    income_cents: int = 0
    expenses_cents: int = 0
    saved_cents: int = 0
    transfers_cents: int = 0
    card_bills_replaced_cents: int = 0
    uncategorized_inflow_cents: int = 0
    pending: int = 0
    card_detailed: bool = False
    by_category: list[CategoryTotal] = field(default_factory=list)
    by_scope: dict[Scope, int] = field(default_factory=dict)
    top_expenses: list[Entry] = field(default_factory=list)
    accounts: list[AccountFlow] = field(default_factory=list)

    @property
    def left_over_cents(self) -> int:
        return self.income_cents - self.expenses_cents


def close_month(month: Month, entries: list[Entry], top: int = 10) -> Closing:
    closing = Closing(month)
    owners_with_card = {
        e.account_owner for e in entries if e.account_kind is AccountKind.CREDIT_CARD
    }
    closing.card_detailed = bool(owners_with_card)
    spent: dict[str, int] = defaultdict(int)
    counts: dict[str, int] = defaultdict(int)
    by_scope: dict[Scope, int] = defaultdict(int)
    expense_entries: list[Entry] = []

    for e in entries:
        if e.needs_review:
            closing.pending += 1
        category = categories.get(e.category) if e.category else None
        kind = category.kind if category else None

        if kind is Kind.INCOME:
            closing.income_cents += e.amount_cents
            continue
        if kind is Kind.SAVINGS:
            closing.saved_cents -= e.amount_cents
            continue
        if kind is Kind.TRANSFER:
            closing.transfers_cents += max(-e.amount_cents, 0)
            continue
        # The card side of a payment, or a payment whose bill is imported.
        replaced = e.account_kind is AccountKind.CREDIT_CARD or e.account_owner in owners_with_card
        if kind is Kind.CARD_BILL and replaced:
            closing.card_bills_replaced_cents += max(-e.amount_cents, 0)
            continue
        if category is None and e.amount_cents > 0:
            closing.uncategorized_inflow_cents += e.amount_cents
            continue

        key = category.key if category else UNCATEGORIZED
        spent[key] -= e.amount_cents
        counts[key] += 1
        if e.scope is not None:
            by_scope[e.scope] -= e.amount_cents
        if e.amount_cents < 0:
            expense_entries.append(e)

    closing.expenses_cents = sum(spent.values())
    closing.by_category = sorted(
        (
            CategoryTotal(
                key,
                "Uncategorized" if key == UNCATEGORIZED else categories.get(key).label,
                cents,
                counts[key],
            )
            for key, cents in spent.items()
        ),
        key=lambda c: (-c.spent_cents, c.key),
    )
    closing.by_scope = dict(by_scope)
    closing.top_expenses = sorted(expense_entries, key=lambda e: e.amount_cents)[:top]
    closing.accounts = _account_flows(entries)
    return closing


def _account_flows(entries: list[Entry]) -> list[AccountFlow]:
    flows: dict[tuple[str, str, AccountKind], list[int]] = defaultdict(lambda: [0, 0])
    for e in entries:
        flow = flows[(e.account_owner, e.account_institution, e.account_kind)]
        flow[0 if e.amount_cents > 0 else 1] += e.amount_cents
    return [
        AccountFlow(owner, institution, kind, inflow, outflow)
        for (owner, institution, kind), (inflow, outflow) in flows.items()
    ]
