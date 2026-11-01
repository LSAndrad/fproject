from datetime import date, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from openpyxl import Workbook

from fproject.domain import Month
from fproject.extractors.spreadsheet import (
    SpreadsheetError,
    SpreadsheetExtractor,
    SpreadsheetLayout,
)
from fproject.reconciliation import reconcile

HEADER = ("Data", "Descrição", "Detalhe", "Valor", "Saldo")

# A synthetic checking account, newest first like real bank exports.
# Two lines on 05/09 test same-day ordering.
NEWEST_FIRST = [
    ("02/10/2026", "Pix enviado", "Corner Bakery", "-R$ 12,50", "R$ 5.137,50"),
    ("30/09/2026", "Pix recebido", "Acme Consulting", "R$ 4.000,00", "R$ 5.150,00"),
    ("05/09/2026", "Pagamento de boleto", "Building Condo", "-R$ 600,00", "R$ 1.150,00"),
    ("05/09/2026", "Pix enviado", "Green Grocer", "-R$ 250,00", "R$ 1.750,00"),
    ("28/08/2026", "Remuneracao aplicacao", None, "R$ 0,03", "R$ 2.000,00"),
    ("10/08/2026", "Debito fatura cartao", "Final 0000", "-R$ 1.234,56", "R$ 1.999,97"),
]
# The balance before the oldest line above: 1.999,97 + 1.234,56.
OPENING_CENTS = 323453


def write_xlsx(path: Path, rows, header=HEADER, preamble=True) -> Path:
    workbook = Workbook()
    sheet = workbook.active
    if preamble:
        sheet.append(("Checking account statement",))
        sheet.append(("Client", "Jane Doe"))
        sheet.append(())
    sheet.append(header)
    for row in rows:
        sheet.append(row)
    workbook.save(path)
    return path


def extract(path: Path, layout: SpreadsheetLayout | None = None):
    return SpreadsheetExtractor(layout).extract(path, uuid4())


@pytest.fixture
def statements(tmp_path):
    return extract(write_xlsx(tmp_path / "statement.xlsx", NEWEST_FIRST))


def test_splits_file_into_one_statement_per_month(statements):
    assert [s.month for s in statements] == [Month(2026, 8), Month(2026, 9), Month(2026, 10)]


def test_derives_opening_and_closing_balances(statements):
    august, september, october = statements
    assert august.opening_balance_cents == OPENING_CENTS
    assert august.closing_balance_cents == 200000
    assert september.opening_balance_cents == 200000
    assert september.closing_balance_cents == 515000
    assert october.opening_balance_cents == 515000
    assert october.closing_balance_cents == 513750


def test_every_statement_reconciles(statements):
    for statement in statements:
        reconcile(statement)


def test_orders_transactions_oldest_first_including_same_day(statements):
    september = statements[1]
    assert [t.details for t in september.transactions] == [
        "Green Grocer",
        "Building Condo",
        "Acme Consulting",
    ]


def test_reads_transaction_fields(statements):
    tx = statements[0].transactions[0]
    assert tx.posted_on == date(2026, 8, 10)
    assert tx.description == "Debito fatura cartao"
    assert tx.details == "Final 0000"
    assert tx.amount_cents == -123456


def test_missing_details_become_none(statements):
    assert statements[0].transactions[1].details is None


def test_accepts_oldest_first_files(tmp_path):
    path = write_xlsx(tmp_path / "statement.xlsx", NEWEST_FIRST[::-1])
    assert [s.month for s in extract(path)] == [Month(2026, 8), Month(2026, 9), Month(2026, 10)]


def test_accepts_native_date_and_number_cells(tmp_path):
    rows = [
        (datetime(2026, 9, 2), "Pix enviado", "Corner Bakery", -12.5, 987.5),
        (datetime(2026, 9, 1), "Pix recebido", "Acme Consulting", 1000, 1000.0),
    ]
    (statement,) = extract(write_xlsx(tmp_path / "statement.xlsx", rows))
    assert [t.amount_cents for t in statement.transactions] == [100000, -1250]
    assert statement.transactions[0].posted_on == date(2026, 9, 1)


def test_supports_custom_layout(tmp_path):
    layout = SpreadsheetLayout(
        date="Date",
        description="Memo",
        details=None,
        amount="Amount",
        balance="Balance",
        date_format="%Y-%m-%d",
    )
    rows = [("2026-09-01", "Salary", 1000, 1500)]
    path = write_xlsx(tmp_path / "s.xlsx", rows, header=("Date", "Memo", "Amount", "Balance"))
    (statement,) = extract(path, layout)
    assert statement.opening_balance_cents == 50000
    assert statement.transactions[0].details is None


def test_ignores_empty_rows(tmp_path):
    rows = [NEWEST_FIRST[0], (None, None, None, None, None), NEWEST_FIRST[1]]
    assert len(extract(write_xlsx(tmp_path / "s.xlsx", rows))) == 2


def test_header_only_file_has_no_statements(tmp_path):
    assert extract(write_xlsx(tmp_path / "s.xlsx", [])) == []


def test_rejects_broken_balance_chain(tmp_path):
    rows = list(NEWEST_FIRST)
    # Misread amount on the Green Grocer line (row 8 of the sheet).
    rows[3] = ("05/09/2026", "Pix enviado", "Green Grocer", "-R$ 205,00", "R$ 1.750,00")
    with pytest.raises(SpreadsheetError, match=r"row 8: balance R\$ 1\.750,00"):
        extract(write_xlsx(tmp_path / "s.xlsx", rows))


def test_rejects_file_without_expected_header(tmp_path):
    path = write_xlsx(tmp_path / "s.xlsx", NEWEST_FIRST, header=("Date", "Memo", "Amount"))
    with pytest.raises(SpreadsheetError, match="no header row"):
        extract(path)


def test_rejects_unparseable_amount(tmp_path):
    rows = [("01/09/2026", "Pix enviado", "Corner Bakery", "twelve", "R$ 0,00")]
    with pytest.raises(SpreadsheetError, match="row 5"):
        extract(write_xlsx(tmp_path / "s.xlsx", rows))


def test_rejects_fractions_of_a_cent(tmp_path):
    rows = [(datetime(2026, 9, 1), "Pix enviado", "Corner Bakery", -0.125, 10.0)]
    with pytest.raises(SpreadsheetError, match="fractions of a cent"):
        extract(write_xlsx(tmp_path / "s.xlsx", rows))
