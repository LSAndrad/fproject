from datetime import date
from uuid import uuid4

import pytest

from fproject.domain import Month, Statement, Transaction
from fproject.reconciliation import ReconciliationError, reconcile


def make_statement(opening: int, closing: int, amounts: list[int]) -> Statement:
    return Statement(
        account_id=uuid4(),
        month=Month(2026, 9),
        opening_balance_cents=opening,
        closing_balance_cents=closing,
        transactions=[
            Transaction(posted_on=date(2026, 9, 1), description="X", amount_cents=a)
            for a in amounts
        ],
    )


def test_accepts_balanced_statement():
    reconcile(make_statement(opening=100000, closing=145000, amounts=[500000, -455000]))


def test_accepts_empty_statement_with_unchanged_balance():
    reconcile(make_statement(opening=100000, closing=100000, amounts=[]))


def test_accepts_negative_balances():
    # A credit card statement typically runs below zero.
    reconcile(make_statement(opening=-432118, closing=-563875, amounts=[432118, -563875]))


def test_rejects_missing_transaction():
    # The statement closes 19,90 lower than its transactions explain:
    # a 19,90 outflow was not extracted.
    statement = make_statement(opening=100000, closing=78010, amounts=[-20000])
    with pytest.raises(ReconciliationError) as excinfo:
        reconcile(statement)
    assert excinfo.value.difference_cents == -1990


def test_rejects_empty_statement_with_changed_balance():
    with pytest.raises(ReconciliationError):
        reconcile(make_statement(opening=100000, closing=90000, amounts=[]))


def test_error_message_shows_amounts_in_reais():
    statement = make_statement(opening=100000, closing=78010, amounts=[-20000])
    with pytest.raises(ReconciliationError, match=r"2026-09.*R\$ 800,00.*R\$ 780,10.*-R\$ 19,90"):
        reconcile(statement)
