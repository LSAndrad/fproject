import sqlite3
from datetime import date
from uuid import uuid4

import pytest

from fproject.domain import Account, AccountKind, Month, Statement, Transaction
from fproject.storage import Repository, StatementAlreadyImported, connect


@pytest.fixture
def conn():
    conn = connect(":memory:")
    yield conn
    conn.close()


@pytest.fixture
def repo(conn):
    return Repository(conn)


@pytest.fixture
def account(repo):
    account = Account(owner="alice", institution="Acme Bank", kind=AccountKind.CHECKING)
    repo.save_account(account)
    return account


SEPTEMBER = Month(2026, 9)


def make_statement(account: Account, month: Month = SEPTEMBER, **overrides) -> Statement:
    transactions = [
        Transaction(posted_on=date(2026, 9, 1), description="SALARY", amount_cents=500000),
        Transaction(posted_on=date(2026, 9, 5), description="RENT", amount_cents=-180000),
        Transaction(posted_on=date(2026, 9, 5), description="GROCERIES", amount_cents=-35090),
    ]
    values = {
        "account_id": account.id,
        "month": month,
        "opening_balance_cents": 120000,
        "closing_balance_cents": 404910,
        "transactions": transactions,
    } | overrides
    return Statement(**values)


def count(conn: sqlite3.Connection, table: str) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


class TestAccounts:
    def test_round_trip(self, repo, account):
        assert repo.get_account(account.id) == account

    def test_missing_account_returns_none(self, repo):
        assert repo.get_account(uuid4()) is None

    def test_rejects_duplicate_owner_institution_kind(self, repo, account):
        duplicate = Account(owner="alice", institution="Acme Bank", kind=AccountKind.CHECKING)
        with pytest.raises(sqlite3.IntegrityError):
            repo.save_account(duplicate)


class TestStatements:
    def test_round_trip_preserves_everything(self, repo, account):
        statement = make_statement(account)
        repo.save_statement(statement)
        assert repo.get_statement(account.id, statement.month) == statement

    def test_preserves_order_of_same_day_transactions(self, repo, account):
        statement = make_statement(account)
        repo.save_statement(statement)
        stored = repo.get_statement(account.id, statement.month)
        assert [t.description for t in stored.transactions] == ["SALARY", "RENT", "GROCERIES"]

    def test_missing_statement_returns_none(self, repo, account):
        assert repo.get_statement(account.id, Month(2026, 9)) is None

    def test_rejects_second_statement_for_same_account_and_month(self, repo, account):
        repo.save_statement(make_statement(account))
        with pytest.raises(StatementAlreadyImported):
            repo.save_statement(make_statement(account))

    def test_allows_same_month_for_another_account(self, repo, account):
        other = Account(owner="bob", institution="Acme Bank", kind=AccountKind.CHECKING)
        repo.save_account(other)
        repo.save_statement(make_statement(account))
        repo.save_statement(make_statement(other))
        assert repo.get_statement(other.id, Month(2026, 9)) is not None

    def test_allows_other_months_for_same_account(self, repo, account):
        repo.save_statement(make_statement(account, Month(2026, 9)))
        repo.save_statement(make_statement(account, Month(2026, 10)))
        assert repo.get_statement(account.id, Month(2026, 10)) is not None

    def test_requires_existing_account(self, repo):
        orphan = Account(owner="carol", institution="Acme Bank", kind=AccountKind.CHECKING)
        with pytest.raises(sqlite3.IntegrityError):
            repo.save_statement(make_statement(orphan))

    def test_is_atomic(self, conn, repo, account):
        # The same transaction twice collides on its primary key midway
        # through the insert; nothing from the statement may remain.
        tx = Transaction(posted_on=date(2026, 9, 1), description="SALARY", amount_cents=500000)
        with pytest.raises(sqlite3.IntegrityError):
            repo.save_statement(make_statement(account, transactions=[tx, tx]))
        assert count(conn, "statements") == 0
        assert count(conn, "transactions") == 0


class TestSchema:
    def test_deleting_statement_deletes_its_transactions(self, conn, repo, account):
        statement = make_statement(account)
        repo.save_statement(statement)
        with conn:
            conn.execute("DELETE FROM statements WHERE id = ?", (str(statement.id),))
        assert count(conn, "transactions") == 0

    def test_rejects_zero_amount(self, conn, repo, account):
        statement = make_statement(account, transactions=[])
        repo.save_statement(statement)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO transactions VALUES (?, ?, 0, '2026-09-01', 'X', 0)",
                (str(uuid4()), str(statement.id)),
            )

    def test_rejects_float_amount(self, conn, repo, account):
        statement = make_statement(account, transactions=[])
        repo.save_statement(statement)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO transactions VALUES (?, ?, 0, '2026-09-01', 'X', 19.9)",
                (str(uuid4()), str(statement.id)),
            )

    def test_rejects_unknown_account_kind(self, conn):
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO accounts VALUES (?, 'alice', 'Acme Bank', 'crypto')",
                (str(uuid4()),),
            )
