"""Extractor for statements already structured as JSON.

This is the interchange format for anything that cannot be parsed
deterministically, such as credit card bill PDFs: an assistant (today
Claude Code following .claude/skills/extract-card-bill, later an API-based
extractor) writes this JSON, and the usual reconciliation decides whether
it is trusted.

    {
      "format": "fproject.statements/v1",
      "statements": [
        {
          "month": "2026-09",
          "opening_balance_cents": -250000,
          "closing_balance_cents": -312345,
          "transactions": [
            {"posted_on": "2026-08-10", "description": "PAYMENT RECEIVED",
             "amount_cents": 250000},
            {"posted_on": "2026-08-12", "description": "CORNER BAKERY",
             "details": "installment 2/3", "cardholder": "JANE DOE",
             "amount_cents": -1250}
          ]
        }
      ]
    }

Amounts are signed integer cents from the account's point of view: on a
credit card, purchases are negative; payments and refunds are positive.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any
from uuid import UUID

from fproject.domain import Month, Statement, Transaction
from fproject.extractors import ExtractionError

FORMAT = "fproject.statements/v1"

_STATEMENT_KEYS = {"month", "opening_balance_cents", "closing_balance_cents", "transactions"}
_TRANSACTION_REQUIRED = {"posted_on", "description", "amount_cents"}
_TRANSACTION_OPTIONAL = {"details", "cardholder"}


class JsonStatementError(ExtractionError):
    """The JSON does not follow the statement format."""


class JsonStatementExtractor:
    def extract(self, source: Path, account_id: UUID) -> list[Statement]:
        try:
            document = json.loads(source.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise JsonStatementError(f"invalid JSON: {error}") from error
        return parse_document(document, account_id)


def parse_document(document: Any, account_id: UUID) -> list[Statement]:
    if not isinstance(document, dict) or document.get("format") != FORMAT:
        raise JsonStatementError(f'expected an object with "format": "{FORMAT}"')
    statements = document.get("statements")
    if not isinstance(statements, list):
        raise JsonStatementError('"statements" must be a list')
    return [_statement(raw, account_id, f"statements[{i}]") for i, raw in enumerate(statements)]


def _statement(raw: Any, account_id: UUID, where: str) -> Statement:
    _check_keys(raw, _STATEMENT_KEYS, set(), where)
    transactions = raw["transactions"]
    if not isinstance(transactions, list):
        raise JsonStatementError(f"{where}.transactions must be a list")
    try:
        return Statement(
            account_id=account_id,
            month=Month.parse(raw["month"]),
            opening_balance_cents=raw["opening_balance_cents"],
            closing_balance_cents=raw["closing_balance_cents"],
            transactions=[
                _transaction(t, f"{where}.transactions[{i}]") for i, t in enumerate(transactions)
            ],
        )
    except (TypeError, ValueError) as error:
        if isinstance(error, JsonStatementError):
            raise
        raise JsonStatementError(f"{where}: {error}") from error


def _transaction(raw: Any, where: str) -> Transaction:
    _check_keys(raw, _TRANSACTION_REQUIRED, _TRANSACTION_OPTIONAL, where)
    try:
        return Transaction(
            posted_on=date.fromisoformat(raw["posted_on"]),
            description=raw["description"],
            details=raw.get("details"),
            cardholder=raw.get("cardholder"),
            amount_cents=raw["amount_cents"],
        )
    except (TypeError, ValueError, AttributeError) as error:
        raise JsonStatementError(f"{where}: {error}") from error


def _check_keys(raw: Any, required: set[str], optional: set[str], where: str) -> None:
    if not isinstance(raw, dict):
        raise JsonStatementError(f"{where} must be an object")
    missing = required - raw.keys()
    unknown = raw.keys() - required - optional
    if missing:
        raise JsonStatementError(f"{where} is missing {', '.join(sorted(missing))}")
    if unknown:
        raise JsonStatementError(f"{where} has unknown keys {', '.join(sorted(unknown))}")
