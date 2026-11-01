from datetime import date
from uuid import uuid4

import pytest

from fproject.domain import Account, AccountKind, Month, Statement, Transaction
from fproject.importer import Outcome, get_or_create_account, import_statements
from fproject.reconciliation import ReconciliationError
from fproject.storage import Repository, connect

NOVEMBER_FIRST = date(2026, 11, 1)


@pytest.fixture
def repo():
    conn = connect(":memory:")
    yield Repository(conn)
    conn.close()


@pytest.fixture
def account(repo):
    return get_or_create_account(
        repo, Account(owner="alice", institution="Acme Bank", kind=AccountKind.CHECKING)
    )


def make_statement(account: Account, month: Month, closing: int = 90000) -> Statement:
    return Statement(
        account_id=account.id,
        month=month,
        opening_balance_cents=100000,
        closing_balance_cents=closing,
        transactions=[
            Transaction(
                posted_on=date(month.year, month.month, 1), description="X", amount_cents=-10000
            )
        ],
    )


def outcomes(report):
    return {str(r.month): r.outcome for r in report.months}


def test_imports_every_finished_month(repo, account):
    statements = [make_statement(account, Month(2026, m)) for m in (8, 9, 10)]
    report = import_statements(repo, account, statements, NOVEMBER_FIRST)
    assert set(outcomes(report).values()) == {Outcome.IMPORTED}
    assert repo.get_statement(account.id, Month(2026, 10)) is not None


def test_skips_month_that_has_not_ended(repo, account):
    statements = [make_statement(account, Month(2026, m)) for m in (9, 10)]
    report = import_statements(repo, account, statements, date(2026, 10, 31))
    assert outcomes(report) == {"2026-09": Outcome.IMPORTED, "2026-10": Outcome.MONTH_NOT_OVER}
    assert repo.get_statement(account.id, Month(2026, 10)) is None


def test_skips_months_already_imported(repo, account):
    import_statements(repo, account, [make_statement(account, Month(2026, 9))], NOVEMBER_FIRST)
    overlapping = [make_statement(account, Month(2026, m)) for m in (9, 10)]
    report = import_statements(repo, account, overlapping, NOVEMBER_FIRST)
    assert outcomes(report) == {
        "2026-09": Outcome.ALREADY_IMPORTED,
        "2026-10": Outcome.IMPORTED,
    }


def test_one_unbalanced_month_imports_nothing(repo, account):
    statements = [
        make_statement(account, Month(2026, 9)),
        make_statement(account, Month(2026, 10), closing=12345),
    ]
    with pytest.raises(ReconciliationError):
        import_statements(repo, account, statements, NOVEMBER_FIRST)
    assert repo.get_statement(account.id, Month(2026, 9)) is None


def test_get_or_create_reuses_existing_account(repo, account):
    again = get_or_create_account(
        repo, Account(owner="alice", institution="Acme Bank", kind=AccountKind.CHECKING)
    )
    assert again.id == account.id


def test_get_or_create_saves_new_account(repo):
    new = Account(id=uuid4(), owner="bob", institution="Acme Bank", kind=AccountKind.CHECKING)
    assert get_or_create_account(repo, new) == new
    assert repo.get_account(new.id) == new
