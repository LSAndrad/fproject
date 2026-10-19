from datetime import date
from uuid import uuid4

import pytest

from fproject.domain import Account, AccountKind, Direction, Month, Statement, Transaction


def make_transaction(amount_cents: int = -1990, description: str = "COFFEE SHOP") -> Transaction:
    return Transaction(
        posted_on=date(2026, 9, 3), description=description, amount_cents=amount_cents
    )


class TestMonth:
    def test_parse_and_format_round_trip(self):
        month = Month.parse("2026-09")
        assert month == Month(2026, 9)
        assert str(month) == "2026-09"

    @pytest.mark.parametrize("text", ["2026-9", "2026/09", "09-2026", "2026-09-01", ""])
    def test_parse_rejects_other_formats(self, text):
        with pytest.raises(ValueError):
            Month.parse(text)

    @pytest.mark.parametrize("month", [0, 13])
    def test_rejects_invalid_month(self, month):
        with pytest.raises(ValueError):
            Month(2026, month)

    def test_orders_chronologically(self):
        assert sorted([Month(2026, 1), Month(2025, 12), Month(2026, 2)]) == [
            Month(2025, 12),
            Month(2026, 1),
            Month(2026, 2),
        ]


class TestAccount:
    def test_generates_unique_ids(self):
        a = Account(owner="alice", institution="Acme Bank", kind=AccountKind.CHECKING)
        b = Account(owner="alice", institution="Acme Bank", kind=AccountKind.CHECKING)
        assert a.id != b.id

    @pytest.mark.parametrize("field", ["owner", "institution"])
    def test_rejects_blank_fields(self, field):
        values = {"owner": "alice", "institution": "Acme Bank", field: "  "}
        with pytest.raises(ValueError):
            Account(**values, kind=AccountKind.CHECKING)


class TestTransaction:
    def test_negative_amount_is_outflow(self):
        assert make_transaction(-1990).direction is Direction.OUTFLOW

    def test_positive_amount_is_inflow(self):
        assert make_transaction(500000).direction is Direction.INFLOW

    def test_generates_unique_ids(self):
        assert make_transaction().id != make_transaction().id

    @pytest.mark.parametrize("amount", [19.90, "1990", True])
    def test_rejects_non_integer_amounts(self, amount):
        with pytest.raises(TypeError):
            make_transaction(amount)

    def test_rejects_zero_amount(self):
        with pytest.raises(ValueError):
            make_transaction(0)

    def test_rejects_blank_description(self):
        with pytest.raises(ValueError):
            make_transaction(description="   ")


class TestStatement:
    def make_statement(self, amounts: list[int]) -> Statement:
        return Statement(
            account_id=uuid4(),
            month=Month(2026, 9),
            opening_balance_cents=100000,
            closing_balance_cents=100000 + sum(amounts),
            transactions=[make_transaction(a) for a in amounts],
        )

    def test_totals(self):
        statement = self.make_statement([500000, -1990, -120000, 3000])
        assert statement.inflow_cents == 503000
        assert statement.outflow_cents == -121990
        assert statement.net_cents == 381010

    def test_stores_transactions_as_tuple(self):
        assert isinstance(self.make_statement([-1990]).transactions, tuple)

    def test_preserves_transaction_order(self):
        amounts = [-300, -100, -200]
        statement = self.make_statement(amounts)
        assert [t.amount_cents for t in statement.transactions] == amounts

    def test_rejects_float_balances(self):
        with pytest.raises(TypeError):
            Statement(
                account_id=uuid4(),
                month=Month(2026, 9),
                opening_balance_cents=1000.0,
                closing_balance_cents=1000,
                transactions=(),
            )
