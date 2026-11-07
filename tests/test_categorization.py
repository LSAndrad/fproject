from datetime import date

import pytest

from fproject.categories import Scope
from fproject.categorization import (
    REQUEST_FORMAT,
    SUGGESTIONS_FORMAT,
    Categorizer,
    Source,
    SuggestionsError,
)
from fproject.domain import Account, AccountKind, Month, Statement, Transaction
from fproject.storage import Repository, connect

SEPTEMBER, OCTOBER = Month(2026, 9), Month(2026, 10)


def tx(amount, description, details=None, cardholder=None, day=1, month=9):
    return Transaction(
        posted_on=date(2026, month, day),
        description=description,
        details=details,
        cardholder=cardholder,
        amount_cents=amount,
    )


def save(repo, account, month, transactions):
    total = sum(t.amount_cents for t in transactions)
    repo.save_statement(
        Statement(
            account_id=account.id,
            month=month,
            opening_balance_cents=0,
            closing_balance_cents=total,
            transactions=transactions,
        )
    )


@pytest.fixture
def conn():
    conn = connect(":memory:")
    yield conn
    conn.close()


@pytest.fixture
def categorizer(conn):
    repo = Repository(conn)
    checking = Account(owner="jane", institution="Acme Bank", kind=AccountKind.CHECKING)
    card = Account(owner="jane", institution="Acme Bank", kind=AccountKind.CREDIT_CARD)
    repo.save_account(checking)
    repo.save_account(card)
    save(
        repo,
        checking,
        SEPTEMBER,
        [
            tx(500000, "Pix received", "Acme Consulting"),
            tx(-180000, "Boleto", "Building Condo"),
            tx(-5000, "Pix sent", "Green Grocer"),
            tx(-7000, "Pix sent", "Green Grocer", day=2),
        ],
    )
    save(
        repo,
        card,
        SEPTEMBER,
        [
            tx(-1200, "RIDE APP", cardholder="JANE DOE"),
            tx(-3000, "RIDE  app", details="USD 5,00", cardholder="JOHN DOE"),
            tx(-9000, "BOOKSTORE", details="installment 2/3", cardholder="JANE DOE"),
        ],
    )
    save(repo, checking, OCTOBER, [tx(-6000, "Pix sent", "Green Grocer", month=10)])
    return Categorizer(conn)


def group(categorizer, label, month=SEPTEMBER):
    return next(g for g in categorizer.review_groups(month) if g.label == label)


def test_groups_by_payee_with_counterparty_on_checking(categorizer):
    grocer = group(categorizer, "Pix sent · Green Grocer")
    assert grocer.count == 2
    assert grocer.total_cents == -12000


def test_card_details_do_not_split_merchants(categorizer):
    rides = next(g for g in categorizer.review_groups(SEPTEMBER) if g.payee_key == "ride app")
    assert rides.count == 2
    assert rides.cardholders == ["JANE DOE", "JOHN DOE"]


def test_largest_amounts_come_first(categorizer):
    labels = [g.label for g in categorizer.review_groups(SEPTEMBER)]
    assert labels[:2] == ["Pix received · Acme Consulting", "Boleto · Building Condo"]


def test_confirm_categorizes_every_transaction_of_the_payee(categorizer):
    count = categorizer.confirm(SEPTEMBER, "boleto · building condo", "housing", Scope.HOUSEHOLD)
    assert count == 1
    (entry,) = [e for e in categorizer.entries(SEPTEMBER) if e.description == "Boleto"]
    assert (entry.category, entry.scope, entry.source, entry.confirmed) == (
        "housing",
        Scope.HOUSEHOLD,
        Source.MANUAL,
        True,
    )
    assert all(g.label != "Boleto · Building Condo" for g in categorizer.review_groups(SEPTEMBER))


def test_confirmed_payee_becomes_a_rule_for_other_months(categorizer):
    # September has 2 grocer transactions, October 1: the rule covers it.
    key = "pix sent · green grocer"
    assert categorizer.confirm(SEPTEMBER, key, "groceries", Scope.HOUSEHOLD) == 3
    (october,) = categorizer.entries(OCTOBER)
    assert (october.category, october.source, october.confirmed) == ("groceries", Source.RULE, True)


def test_rejects_unknown_category(categorizer):
    with pytest.raises(ValueError, match="unknown category"):
        categorizer.confirm(SEPTEMBER, "ride app", "crypto", Scope.PERSONAL)


def test_export_request_lists_payees_to_review(categorizer):
    request = categorizer.export_request(SEPTEMBER)
    assert request["format"] == REQUEST_FORMAT
    assert {"key": "groceries", "label": "Groceries", "kind": "expense"} in request["categories"]
    rides = next(p for p in request["payees"] if p["payee"] == "ride app")
    assert rides == {
        "payee": "ride app",
        "label": "RIDE APP",
        "account_kind": "credit_card",
        "count": 2,
        "total_cents": -4200,
        "cardholders": ["JANE DOE", "JOHN DOE"],
        "dates": ["2026-09-01"],
    }


def suggestions(*items, month="2026-09"):
    return {
        "format": SUGGESTIONS_FORMAT,
        "month": month,
        "suggestions": [{"payee": p, "category": c, "scope": s} for p, c, s in items],
    }


def test_suggestions_are_stored_unconfirmed_and_stay_in_review(categorizer):
    written = categorizer.apply_suggestions(suggestions(("ride app", "transport", "personal")))
    assert written == 2
    rides = next(g for g in categorizer.review_groups(SEPTEMBER) if g.payee_key == "ride app")
    assert rides.suggestion == ("transport", Scope.PERSONAL)
    assert all(e.source is Source.ASSISTANT and not e.confirmed for e in rides.entries)


def test_suggestions_never_override_confirmed_categories(categorizer):
    categorizer.confirm(SEPTEMBER, "ride app", "transport", Scope.PERSONAL)
    assert categorizer.apply_suggestions(suggestions(("ride app", "leisure", "personal"))) == 0
    rides = [e for e in categorizer.entries(SEPTEMBER) if e.payee_key == "ride app"]
    assert {e.category for e in rides} == {"transport"}


def test_confirming_a_suggestion(categorizer):
    categorizer.apply_suggestions(suggestions(("ride app", "transport", "personal")))
    categorizer.confirm(SEPTEMBER, "ride app", "transport", Scope.PERSONAL)
    rides = [e for e in categorizer.entries(SEPTEMBER) if e.payee_key == "ride app"]
    assert all(e.confirmed and e.source is Source.MANUAL for e in rides)


@pytest.mark.parametrize(
    "document",
    [
        {"format": "nope"},
        {"format": SUGGESTIONS_FORMAT, "month": "2026-09"},
        suggestions(("ride app", "crypto", "personal")),
        suggestions(("ride app", "transport", "everyone")),
    ],
)
def test_rejects_invalid_suggestions(categorizer, document):
    with pytest.raises(SuggestionsError):
        categorizer.apply_suggestions(document)
