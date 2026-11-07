import json
from datetime import date
from uuid import uuid4

import pytest
from sample_statements import CARD_BILL

from fproject.domain import Month
from fproject.extractors.json_statement import JsonStatementError, JsonStatementExtractor
from fproject.reconciliation import reconcile


def write(tmp_path, document):
    path = tmp_path / "bill.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def extract(path):
    return JsonStatementExtractor().extract(path, uuid4())


def test_reads_statement_and_transactions(tmp_path):
    (statement,) = extract(write(tmp_path, CARD_BILL))
    assert statement.month == Month(2026, 9)
    assert statement.opening_balance_cents == -250000
    tx = statement.transactions[1]
    assert tx.posted_on == date(2026, 8, 12)
    assert tx.details == "installment 2/3"
    assert tx.cardholder == "JANE DOE"
    assert tx.amount_cents == -300000
    reconcile(statement)


def test_optional_fields_default_to_none(tmp_path):
    (statement,) = extract(write(tmp_path, CARD_BILL))
    assert statement.transactions[0].details is None
    assert statement.transactions[0].cardholder is None


def test_rejects_wrong_format_marker(tmp_path):
    with pytest.raises(JsonStatementError, match="format"):
        extract(write(tmp_path, {**CARD_BILL, "format": "something/v9"}))


def test_rejects_invalid_json(tmp_path):
    path = tmp_path / "bill.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(JsonStatementError, match="invalid JSON"):
        extract(path)


def with_transaction(**fields):
    statement = {**CARD_BILL["statements"][0]}
    statement["transactions"] = [{**statement["transactions"][0], **fields}]
    return {**CARD_BILL, "statements": [statement]}


def test_rejects_float_amounts_with_location(tmp_path):
    document = with_transaction(amount_cents=2500.0)
    with pytest.raises(JsonStatementError, match=r"statements\[0\]\.transactions\[0\]"):
        extract(write(tmp_path, document))


def test_rejects_unknown_keys(tmp_path):
    with pytest.raises(JsonStatementError, match="unknown keys category"):
        extract(write(tmp_path, with_transaction(category="food")))


def test_rejects_missing_keys(tmp_path):
    statement = {**CARD_BILL["statements"][0]}
    del statement["closing_balance_cents"]
    with pytest.raises(JsonStatementError, match="missing closing_balance_cents"):
        extract(write(tmp_path, {**CARD_BILL, "statements": [statement]}))


def test_rejects_bad_date(tmp_path):
    with pytest.raises(JsonStatementError, match="transactions\\[0\\]"):
        extract(write(tmp_path, with_transaction(posted_on="10/08/2026")))
