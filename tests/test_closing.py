from datetime import date
from uuid import uuid4

from fproject.categories import Scope
from fproject.categorization import Entry, Source
from fproject.closing import close_month
from fproject.domain import AccountKind, Month

SEPTEMBER = Month(2026, 9)
CHECKING, CARD = AccountKind.CHECKING, AccountKind.CREDIT_CARD


def entry(amount, category=None, scope=Scope.PERSONAL, kind=CHECKING, owner="jane", **extra):
    return Entry(
        transaction_id=uuid4(),
        month=SEPTEMBER,
        posted_on=date(2026, 9, 1),
        description=extra.get("description", "X"),
        details=None,
        cardholder=None,
        amount_cents=amount,
        account_owner=owner,
        account_institution="Acme Bank",
        account_kind=kind,
        category=category,
        scope=scope if category else None,
        source=Source.MANUAL if category else None,
        confirmed=extra.get("confirmed", category is not None),
    )


CHECKING_MONTH = [
    entry(1000000, "income"),
    entry(-250000, "housing", Scope.HOUSEHOLD),
    entry(-50000, "investment"),
    entry(-20000, "internal_transfer"),
    entry(-400000, "card_bill"),
]
CARD_MONTH = [
    entry(380000, "card_bill", kind=CARD),  # the previous bill's payment, card side
    entry(-300000, "groceries", Scope.HOUSEHOLD, kind=CARD),
    entry(-120000, "dining_out", kind=CARD, description="SUSHI"),
    entry(20000, "dining_out", kind=CARD),  # a refund
]


def test_card_items_replace_the_bill_payment():
    closing = close_month(SEPTEMBER, CHECKING_MONTH + CARD_MONTH)
    assert closing.card_detailed
    assert closing.income_cents == 1000000
    assert closing.expenses_cents == 250000 + 300000 + 120000 - 20000
    assert closing.card_bills_replaced_cents == 400000
    assert closing.saved_cents == 50000
    assert closing.transfers_cents == 20000
    assert closing.left_over_cents == 1000000 - 650000


def test_bill_payment_counts_as_one_expense_without_the_bill():
    closing = close_month(SEPTEMBER, CHECKING_MONTH)
    assert not closing.card_detailed
    assert closing.expenses_cents == 250000 + 400000
    assert [c.key for c in closing.by_category] == ["card_bill", "housing"]


def test_refunds_reduce_their_category():
    closing = close_month(SEPTEMBER, CHECKING_MONTH + CARD_MONTH)
    dining = next(c for c in closing.by_category if c.key == "dining_out")
    assert (dining.spent_cents, dining.count) == (100000, 2)


def test_splits_spending_by_scope():
    closing = close_month(SEPTEMBER, CHECKING_MONTH + CARD_MONTH)
    assert closing.by_scope == {Scope.HOUSEHOLD: 550000, Scope.PERSONAL: 100000}


def test_uncategorized_outflows_still_count_as_expenses():
    closing = close_month(SEPTEMBER, [entry(1000000, "income"), entry(-5000), entry(3000)])
    assert closing.expenses_cents == 5000
    assert closing.by_category[0].label == "Uncategorized"
    assert closing.uncategorized_inflow_cents == 3000
    assert closing.pending == 2


def test_unconfirmed_suggestions_count_but_are_pending():
    closing = close_month(SEPTEMBER, [entry(-5000, "groceries", confirmed=False)])
    assert closing.expenses_cents == 5000
    assert closing.pending == 1


def test_top_expenses_are_the_largest_outflows():
    closing = close_month(SEPTEMBER, CHECKING_MONTH + CARD_MONTH, top=2)
    assert [e.amount_cents for e in closing.top_expenses] == [-300000, -250000]


def test_account_flows_are_raw_totals():
    closing = close_month(SEPTEMBER, CHECKING_MONTH + CARD_MONTH)
    card = next(a for a in closing.accounts if a.kind is CARD)
    assert (card.inflow_cents, card.outflow_cents) == (400000, -420000)
