"""Extractor for spreadsheet (.xlsx) bank exports with a running balance.

Banks typically export checking accounts as a table of date, description,
amount and the balance after each line. The running balance lets every
single row be checked, not just the monthly total.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from itertools import groupby
from pathlib import Path
from uuid import UUID

from openpyxl import load_workbook

from fproject.domain import Month, Statement, Transaction
from fproject.extractors import ExtractionError
from fproject.money import format_brl, parse_brl


class SpreadsheetError(ExtractionError):
    """The spreadsheet could not be read as a statement."""


@dataclass(frozen=True, slots=True, kw_only=True)
class SpreadsheetLayout:
    """Column headers and date format of a bank's export.

    The defaults match the Portuguese headers common in Brazilian banks.
    """

    date: str = "Data"
    description: str = "Descrição"
    details: str | None = "Detalhe"
    amount: str = "Valor"
    balance: str = "Saldo"
    date_format: str = "%d/%m/%Y"


@dataclass(frozen=True, slots=True)
class _Row:
    number: int  # spreadsheet row number, for error messages
    posted_on: date
    description: str
    details: str | None
    amount_cents: int
    balance_cents: int


class SpreadsheetExtractor:
    def __init__(self, layout: SpreadsheetLayout | None = None) -> None:
        self._layout = layout or SpreadsheetLayout()

    def extract(self, source: Path, account_id: UUID) -> list[Statement]:
        rows = _chronological(self._read_rows(source))
        return [
            _statement(account_id, month, list(group))
            for month, group in groupby(
                rows, key=lambda r: Month(r.posted_on.year, r.posted_on.month)
            )
        ]

    def _read_rows(self, source: Path) -> list[_Row]:
        workbook = load_workbook(source, read_only=True, data_only=True)
        try:
            lines = list(workbook.worksheets[0].iter_rows(values_only=True))
        finally:
            workbook.close()

        header_index, columns = self._find_header(lines)
        rows = []
        for offset, cells in enumerate(lines[header_index + 1 :], start=header_index + 2):
            if all(_is_empty(c) for c in cells):
                continue
            try:
                rows.append(self._parse_row(offset, cells, columns))
            except (ValueError, TypeError) as error:
                raise SpreadsheetError(f"row {offset}: {error}") from error
        return rows

    def _find_header(self, lines: list[tuple]) -> tuple[int, dict[str, int]]:
        layout = self._layout
        wanted = {
            "date": layout.date,
            "description": layout.description,
            "amount": layout.amount,
            "balance": layout.balance,
        }
        if layout.details is not None:
            wanted["details"] = layout.details

        for index, cells in enumerate(lines):
            labels = [str(c).strip() if c is not None else "" for c in cells]
            if all(header in labels for header in wanted.values()):
                return index, {field: labels.index(header) for field, header in wanted.items()}
        raise SpreadsheetError(f"no header row with columns {', '.join(wanted.values())}")

    def _parse_row(self, number: int, cells: tuple, columns: dict[str, int]) -> _Row:
        details = cells[columns["details"]] if "details" in columns else None
        return _Row(
            number=number,
            posted_on=_to_date(cells[columns["date"]], self._layout.date_format),
            description=str(cells[columns["description"]]).strip(),
            details=None if _is_empty(details) else str(details).strip(),
            amount_cents=_to_cents(cells[columns["amount"]]),
            balance_cents=_to_cents(cells[columns["balance"]]),
        )


def _chronological(rows: list[_Row]) -> list[_Row]:
    """Return rows oldest first, verifying the running balance on every row.

    Exports are often newest first. Dates alone cannot order lines from the
    same day, but the balance chain can: only one direction makes each
    balance equal the previous balance plus the amount.
    """
    for candidate in (rows, rows[::-1]):
        if _first_break(candidate) is None:
            break
    else:
        oldest_first = rows if rows[0].posted_on <= rows[-1].posted_on else rows[::-1]
        bad = _first_break(oldest_first)
        raise SpreadsheetError(
            f"row {bad.number}: balance {format_brl(bad.balance_cents)} does not follow "
            f"from the previous balance plus {format_brl(bad.amount_cents)}"
        )

    if any(a.posted_on > b.posted_on for a, b in zip(candidate, candidate[1:], strict=False)):
        raise SpreadsheetError("dates are out of order")
    return candidate


def _first_break(rows: list[_Row]) -> _Row | None:
    for previous, row in zip(rows, rows[1:], strict=False):
        if previous.balance_cents + row.amount_cents != row.balance_cents:
            return row
    return None


def _statement(account_id: UUID, month: Month, rows: list[_Row]) -> Statement:
    first, last = rows[0], rows[-1]
    return Statement(
        account_id=account_id,
        month=month,
        opening_balance_cents=first.balance_cents - first.amount_cents,
        closing_balance_cents=last.balance_cents,
        transactions=[
            Transaction(
                posted_on=r.posted_on,
                description=r.description,
                details=r.details,
                amount_cents=r.amount_cents,
            )
            for r in rows
        ],
    )


def _is_empty(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _to_date(value: object, date_format: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return datetime.strptime(value.strip(), date_format).date()
    raise TypeError(f"expected a date, got {value!r}")


def _to_cents(value: object) -> int:
    if isinstance(value, str):
        return parse_brl(value)
    if isinstance(value, int | float | Decimal) and not isinstance(value, bool):
        # str() first: Decimal(0.1) would carry the float's binary error.
        cents = Decimal(str(value)) * 100
        if cents != cents.to_integral_value():
            raise ValueError(f"amount has fractions of a cent: {value!r}")
        return int(cents)
    raise TypeError(f"expected an amount, got {value!r}")
