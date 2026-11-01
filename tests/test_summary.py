from datetime import date
from uuid import uuid4

from fproject.domain import Month, Statement, Transaction
from fproject.summary import Payee, summarize


def tx(amount: int, description: str, details: str | None = None) -> Transaction:
    return Transaction(
        posted_on=date(2026, 9, 1), description=description, details=details, amount_cents=amount
    )


def make_statement(transactions: list[Transaction]) -> Statement:
    return Statement(
        account_id=uuid4(),
        month=Month(2026, 9),
        opening_balance_cents=0,
        closing_balance_cents=sum(t.amount_cents for t in transactions),
        transactions=transactions,
    )


def test_groups_outflows_by_payee_largest_first():
    statement = make_statement(
        [
            tx(500000, "Pix received", "Acme Consulting"),
            tx(-20000, "Pix sent", "Green Grocer"),
            tx(-180000, "Boleto", "Landlord"),
            tx(-15000, "Pix sent", "Green Grocer"),
            tx(-990, "Bank fee"),
        ]
    )
    assert summarize(statement).top_outflows == [
        Payee("Boleto · Landlord", -180000, 1),
        Payee("Pix sent · Green Grocer", -35000, 2),
        Payee("Bank fee", -990, 1),
    ]


def test_limits_to_top_n():
    statement = make_statement([tx(-100 * (i + 1), f"Shop {i}") for i in range(5)])
    assert [p.label for p in summarize(statement, top=2).top_outflows] == ["Shop 4", "Shop 3"]


def test_ignores_inflows():
    statement = make_statement([tx(500000, "Salary")])
    assert summarize(statement).top_outflows == []
