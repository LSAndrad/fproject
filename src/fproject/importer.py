"""Import use case: extracted statements -> reconciled -> stored."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum

from fproject.domain import Account, Month, Statement
from fproject.reconciliation import reconcile
from fproject.storage import Repository, StatementAlreadyImported


class Outcome(StrEnum):
    IMPORTED = "imported"
    ALREADY_IMPORTED = "skipped: already imported"
    MONTH_NOT_OVER = "skipped: month not over yet"


@dataclass(frozen=True, slots=True)
class MonthResult:
    month: Month
    transactions: int
    outcome: Outcome


@dataclass(frozen=True, slots=True)
class ImportReport:
    account: Account
    months: list[MonthResult] = field(default_factory=list)


def import_statements(
    repo: Repository, account: Account, statements: list[Statement], today: date
) -> ImportReport:
    """Store every statement of a file, skipping months that can't be imported yet.

    All statements are reconciled before any is stored, so a file with one bad
    month imports nothing. A month that has not ended is skipped: importing it
    now would block importing the complete month later.
    """
    for statement in statements:
        reconcile(statement)

    current = Month(today.year, today.month)
    report = ImportReport(account)
    for statement in statements:
        if statement.month >= current:
            outcome = Outcome.MONTH_NOT_OVER
        else:
            try:
                repo.save_statement(statement)
                outcome = Outcome.IMPORTED
            except StatementAlreadyImported:
                outcome = Outcome.ALREADY_IMPORTED
        report.months.append(MonthResult(statement.month, len(statement.transactions), outcome))
    return report


def get_or_create_account(repo: Repository, account: Account) -> Account:
    existing = repo.find_account(account.owner, account.institution, account.kind)
    if existing is not None:
        return existing
    repo.save_account(account)
    return account
