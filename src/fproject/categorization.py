"""Categorization: a layer on top of the ledger, never mixed into it.

Transactions are categorized per *payee* (description, plus the
counterparty on checking accounts) rather than one by one: twelve rides
with the same merchant are one decision. Every confirmed decision becomes a
rule, so next month's statement arrives mostly categorized.

A categorization is either confirmed (by you, or by a rule you created) or
a suggestion waiting for confirmation (from an assistant).
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import Any
from uuid import UUID

from fproject import categories
from fproject.categories import Scope
from fproject.domain import AccountKind, Month

REQUEST_FORMAT = "fproject.categorization-request/v1"
SUGGESTIONS_FORMAT = "fproject.categorization-suggestions/v1"

_CATEGORY_KEYS = ", ".join(f"'{c.key}'" for c in categories.CATEGORIES)
_SCOPES = ", ".join(f"'{s}'" for s in Scope)

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS categorizations (
    transaction_id TEXT PRIMARY KEY REFERENCES transactions (id) ON DELETE CASCADE,
    category       TEXT NOT NULL CHECK (category IN ({_CATEGORY_KEYS})),
    scope          TEXT NOT NULL CHECK (scope IN ({_SCOPES})),
    source         TEXT NOT NULL CHECK (source IN ('manual', 'rule', 'assistant')),
    confirmed      INTEGER NOT NULL CHECK (confirmed IN (0, 1))
) STRICT;

CREATE TABLE IF NOT EXISTS rules (
    payee_key TEXT PRIMARY KEY,
    category  TEXT NOT NULL CHECK (category IN ({_CATEGORY_KEYS})),
    scope     TEXT NOT NULL CHECK (scope IN ({_SCOPES}))
) STRICT;
"""


class Source(StrEnum):
    MANUAL = "manual"
    RULE = "rule"
    ASSISTANT = "assistant"


class SuggestionsError(ValueError):
    """A suggestions document does not follow the format."""


@dataclass(frozen=True, slots=True)
class Entry:
    """A transaction as the categorization and closing layers see it."""

    transaction_id: UUID
    month: Month
    posted_on: date
    description: str
    details: str | None
    cardholder: str | None
    amount_cents: int
    account_owner: str
    account_institution: str
    account_kind: AccountKind
    category: str | None
    scope: Scope | None
    source: Source | None
    confirmed: bool

    @property
    def payee_label(self) -> str:
        # On credit cards, details hold installment or currency info, which
        # must not split one merchant into many payees.
        if self.account_kind is AccountKind.CREDIT_CARD or self.details is None:
            return self.description
        return f"{self.description} · {self.details}"

    @property
    def payee_key(self) -> str:
        return " ".join(self.payee_label.casefold().split())

    @property
    def needs_review(self) -> bool:
        return self.category is None or not self.confirmed


@dataclass(slots=True)
class PayeeGroup:
    payee_key: str
    label: str
    account_kind: AccountKind
    entries: list[Entry] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.entries)

    @property
    def total_cents(self) -> int:
        return sum(e.amount_cents for e in self.entries)

    @property
    def cardholders(self) -> list[str]:
        return sorted({e.cardholder for e in self.entries if e.cardholder})

    @property
    def suggestion(self) -> tuple[str, Scope] | None:
        for e in self.entries:
            if e.category is not None:
                return e.category, e.scope
        return None


class Categorizer:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        conn.executescript(SCHEMA)

    def months(self) -> list[Month]:
        rows = self._conn.execute("SELECT DISTINCT month FROM statements ORDER BY month")
        return [Month.parse(r["month"]) for r in rows]

    def entries(self, month: Month) -> list[Entry]:
        rows = self._conn.execute(
            """
            SELECT t.id, s.month, t.posted_on, t.description, t.details, t.cardholder,
                   t.amount_cents, a.owner, a.institution, a.kind,
                   c.category, c.scope, c.source, c.confirmed
            FROM transactions t
            JOIN statements s ON s.id = t.statement_id
            JOIN accounts a ON a.id = s.account_id
            LEFT JOIN categorizations c ON c.transaction_id = t.id
            WHERE s.month = ?
            ORDER BY a.kind, a.owner, a.institution, t.position
            """,
            (str(month),),
        )
        return [_entry(r) for r in rows]

    def review_groups(self, month: Month) -> list[PayeeGroup]:
        """Payees with transactions not yet confirmed, largest amounts first."""
        groups: dict[str, PayeeGroup] = {}
        for e in self.entries(month):
            if not e.needs_review:
                continue
            group = groups.setdefault(
                e.payee_key, PayeeGroup(e.payee_key, e.payee_label, e.account_kind)
            )
            group.entries.append(e)
        return sorted(groups.values(), key=lambda g: (-abs(g.total_cents), g.payee_key))

    def confirm(self, month: Month, payee_key: str, category: str, scope: Scope) -> int:
        """Confirm a category for a payee in a month and remember it as a rule.

        Returns how many transactions were categorized, including other months'
        uncategorized transactions that the new rule now covers.
        """
        categories.get(category)
        targets = [
            e.transaction_id
            for e in self.entries(month)
            if e.payee_key == payee_key and e.needs_review
        ]
        with self._conn:
            self._write(targets, category, scope, Source.MANUAL, confirmed=True)
            self._conn.execute(
                """
                INSERT INTO rules (payee_key, category, scope) VALUES (?, ?, ?)
                ON CONFLICT (payee_key) DO UPDATE SET category = excluded.category,
                                                      scope = excluded.scope
                """,
                (payee_key, category, str(scope)),
            )
        return len(targets) + self.apply_rules()

    def apply_rules(self) -> int:
        """Categorize every uncategorized transaction that matches a rule."""
        rules = {
            r["payee_key"]: (r["category"], Scope(r["scope"]))
            for r in self._conn.execute("SELECT * FROM rules")
        }
        if not rules:
            return 0
        matched: dict[tuple[str, Scope], list[UUID]] = defaultdict(list)
        for month in self.months():
            for e in self.entries(month):
                if e.category is None and e.payee_key in rules:
                    matched[rules[e.payee_key]].append(e.transaction_id)
        with self._conn:
            for (category, scope), ids in matched.items():
                self._write(ids, category, scope, Source.RULE, confirmed=True)
        return sum(len(ids) for ids in matched.values())

    def export_request(self, month: Month) -> dict[str, Any]:
        """Payees awaiting review, as a document an assistant can categorize."""
        return {
            "format": REQUEST_FORMAT,
            "month": str(month),
            "categories": [
                {"key": c.key, "label": c.label, "kind": str(c.kind)} for c in categories.CATEGORIES
            ],
            "scopes": [str(s) for s in Scope],
            "payees": [
                {
                    "payee": g.payee_key,
                    "label": g.label,
                    "account_kind": str(g.account_kind),
                    "count": g.count,
                    "total_cents": g.total_cents,
                    "cardholders": g.cardholders,
                    "dates": sorted({e.posted_on.isoformat() for e in g.entries}),
                }
                for g in self.review_groups(month)
            ],
        }

    def apply_suggestions(self, document: Any) -> int:
        """Store an assistant's suggestions, unconfirmed. Never touches confirmed ones."""
        month, suggestions = _parse_suggestions(document)
        by_payee: dict[str, list[UUID]] = defaultdict(list)
        for e in self.entries(month):
            if e.needs_review:
                by_payee[e.payee_key].append(e.transaction_id)
        written = 0
        with self._conn:
            for payee, category, scope in suggestions:
                ids = by_payee.get(payee, [])
                self._write(ids, category, scope, Source.ASSISTANT, confirmed=False)
                written += len(ids)
        return written

    def _write(
        self, ids: list[UUID], category: str, scope: Scope, source: Source, confirmed: bool
    ) -> None:
        self._conn.executemany(
            """
            INSERT INTO categorizations (transaction_id, category, scope, source, confirmed)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (transaction_id) DO UPDATE SET
                category = excluded.category, scope = excluded.scope,
                source = excluded.source, confirmed = excluded.confirmed
            """,
            [(str(i), category, str(scope), str(source), int(confirmed)) for i in ids],
        )


def _entry(r: sqlite3.Row) -> Entry:
    return Entry(
        transaction_id=UUID(r["id"]),
        month=Month.parse(r["month"]),
        posted_on=date.fromisoformat(r["posted_on"]),
        description=r["description"],
        details=r["details"],
        cardholder=r["cardholder"],
        amount_cents=r["amount_cents"],
        account_owner=r["owner"],
        account_institution=r["institution"],
        account_kind=AccountKind(r["kind"]),
        category=r["category"],
        scope=Scope(r["scope"]) if r["scope"] else None,
        source=Source(r["source"]) if r["source"] else None,
        confirmed=bool(r["confirmed"]),
    )


def _parse_suggestions(document: Any) -> tuple[Month, list[tuple[str, str, Scope]]]:
    if not isinstance(document, dict) or document.get("format") != SUGGESTIONS_FORMAT:
        raise SuggestionsError(f'expected an object with "format": "{SUGGESTIONS_FORMAT}"')
    try:
        month = Month.parse(document["month"])
        parsed = []
        for i, s in enumerate(document["suggestions"]):
            try:
                categories.get(s["category"])
                parsed.append((s["payee"], s["category"], Scope(s["scope"])))
            except (KeyError, TypeError, ValueError) as error:
                raise SuggestionsError(f"suggestions[{i}]: {error}") from error
    except (KeyError, TypeError) as error:
        raise SuggestionsError(f"missing or invalid field: {error}") from error
    return month, parsed
