"""SQLite persistence for the ledger.

The schema mirrors the domain model. Rules that protect the data (one
statement per account per month, no zero amounts, cascading deletes) are
enforced by the database itself, not only by Python code.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path
from uuid import UUID

from fproject.domain import Account, AccountKind, Month, Statement, Transaction

_ACCOUNT_KINDS = ", ".join(f"'{kind}'" for kind in AccountKind)

# STRICT tables make SQLite reject values of the wrong type instead of
# silently coercing them (e.g. a float into an INTEGER column).
SCHEMA = f"""
CREATE TABLE IF NOT EXISTS accounts (
    id          TEXT PRIMARY KEY,
    owner       TEXT NOT NULL,
    institution TEXT NOT NULL,
    kind        TEXT NOT NULL CHECK (kind IN ({_ACCOUNT_KINDS})),
    UNIQUE (owner, institution, kind)
) STRICT;

CREATE TABLE IF NOT EXISTS statements (
    id                    TEXT PRIMARY KEY,
    account_id            TEXT NOT NULL REFERENCES accounts (id),
    month                 TEXT NOT NULL,  -- YYYY-MM
    opening_balance_cents INTEGER NOT NULL,
    closing_balance_cents INTEGER NOT NULL,
    UNIQUE (account_id, month)
) STRICT;

CREATE TABLE IF NOT EXISTS transactions (
    id           TEXT PRIMARY KEY,
    statement_id TEXT NOT NULL REFERENCES statements (id) ON DELETE CASCADE,
    position     INTEGER NOT NULL,  -- order of appearance in the statement
    posted_on    TEXT NOT NULL,     -- ISO date
    description  TEXT NOT NULL,
    amount_cents INTEGER NOT NULL CHECK (amount_cents <> 0),
    UNIQUE (statement_id, position)
) STRICT;
"""


class StatementAlreadyImported(Exception):
    def __init__(self, account_id: UUID, month: Month) -> None:
        super().__init__(f"a statement for {month} was already imported for account {account_id}")
        self.account_id = account_id
        self.month = month


def connect(path: str | Path = ":memory:") -> sqlite3.Connection:
    """Open a database and make sure the schema exists."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    # SQLite does not enforce foreign keys unless asked to, per connection.
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


class Repository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def save_account(self, account: Account) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO accounts (id, owner, institution, kind) VALUES (?, ?, ?, ?)",
                (str(account.id), account.owner, account.institution, account.kind.value),
            )

    def get_account(self, account_id: UUID) -> Account | None:
        row = self._conn.execute(
            "SELECT * FROM accounts WHERE id = ?", (str(account_id),)
        ).fetchone()
        if row is None:
            return None
        return Account(
            id=UUID(row["id"]),
            owner=row["owner"],
            institution=row["institution"],
            kind=AccountKind(row["kind"]),
        )

    def save_statement(self, statement: Statement) -> None:
        """Store a statement and its transactions atomically.

        Raises StatementAlreadyImported if the account already has a
        statement for that month.
        """
        if self._statement_exists(statement.account_id, statement.month):
            raise StatementAlreadyImported(statement.account_id, statement.month)

        # The context manager commits on success and rolls back on any error,
        # so a statement is never stored with only part of its transactions.
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO statements
                    (id, account_id, month, opening_balance_cents, closing_balance_cents)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    str(statement.id),
                    str(statement.account_id),
                    str(statement.month),
                    statement.opening_balance_cents,
                    statement.closing_balance_cents,
                ),
            )
            self._conn.executemany(
                """
                INSERT INTO transactions
                    (id, statement_id, position, posted_on, description, amount_cents)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        str(t.id),
                        str(statement.id),
                        position,
                        t.posted_on.isoformat(),
                        t.description,
                        t.amount_cents,
                    )
                    for position, t in enumerate(statement.transactions)
                ],
            )

    def get_statement(self, account_id: UUID, month: Month) -> Statement | None:
        row = self._conn.execute(
            "SELECT * FROM statements WHERE account_id = ? AND month = ?",
            (str(account_id), str(month)),
        ).fetchone()
        if row is None:
            return None
        transactions = self._conn.execute(
            "SELECT * FROM transactions WHERE statement_id = ? ORDER BY position",
            (row["id"],),
        ).fetchall()
        return Statement(
            id=UUID(row["id"]),
            account_id=UUID(row["account_id"]),
            month=Month.parse(row["month"]),
            opening_balance_cents=row["opening_balance_cents"],
            closing_balance_cents=row["closing_balance_cents"],
            transactions=[
                Transaction(
                    id=UUID(t["id"]),
                    posted_on=date.fromisoformat(t["posted_on"]),
                    description=t["description"],
                    amount_cents=t["amount_cents"],
                )
                for t in transactions
            ],
        )

    def _statement_exists(self, account_id: UUID, month: Month) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM statements WHERE account_id = ? AND month = ?",
            (str(account_id), str(month)),
        ).fetchone()
        return row is not None
