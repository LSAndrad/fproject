"""End to end: the commands as a user runs them, against a real database file."""

import json
from datetime import date
from pathlib import Path

import pytest
from sample_statements import CARD_BILL, NEWEST_FIRST, write_xlsx

from fproject.cli import main
from fproject.domain import Month

NOVEMBER_FIRST = date(2026, 11, 1)


@pytest.fixture
def db(tmp_path):
    return str(tmp_path / "data" / "fproject.db")


@pytest.fixture
def statement_file(tmp_path):
    return str(write_xlsx(tmp_path / "statement.xlsx", NEWEST_FIRST))


def run(db, *args, today=NOVEMBER_FIRST):
    return main(["--db", db, *args], today=today)


def import_args(statement_file):
    return ["import", statement_file, "--owner", "jane", "--institution", "Acme Bank"]


def test_import_reports_each_month(db, statement_file, capsys):
    assert run(db, *import_args(statement_file)) == 0
    out = capsys.readouterr().out
    assert "jane · Acme Bank (checking)" in out
    assert "2026-08     2 transactions  imported" in out
    assert "2026-09     3 transactions  imported" in out
    assert "2026-10     1 transactions  imported" in out


def test_reimport_skips_months_already_imported(db, statement_file, capsys):
    run(db, *import_args(statement_file))
    capsys.readouterr()
    assert run(db, *import_args(statement_file)) == 0
    assert capsys.readouterr().out.count("skipped: already imported") == 3


def test_summary_after_import(db, statement_file, capsys):
    run(db, *import_args(statement_file))
    capsys.readouterr()
    assert run(db, "summary", "2026-09") == 0
    out = capsys.readouterr().out
    assert "In" in out and "R$ 4.000,00" in out
    assert "Out" in out and "-R$ 850,00" in out
    assert "Closing balance" in out and "R$ 5.150,00" in out
    assert out.index("Building Condo") < out.index("Green Grocer")


def test_summary_without_data_fails(db, capsys):
    assert run(db, "summary", "2026-09") == 1
    assert "no statements imported for 2026-09" in capsys.readouterr().err


def test_rejects_unsupported_file(db, tmp_path, capsys):
    path = tmp_path / "statement.pdf"
    path.write_bytes(b"%PDF")
    assert run(db, *import_args(str(path))) == 1
    assert "unsupported file type: .pdf" in capsys.readouterr().err


def test_reports_unreadable_spreadsheet(db, tmp_path, capsys):
    path = write_xlsx(tmp_path / "s.xlsx", NEWEST_FIRST, header=("Date", "Memo"))
    assert run(db, *import_args(str(path))) == 1
    assert "no header row" in capsys.readouterr().err


def write_card_bill(tmp_path, closing=-312345):
    statement = {**CARD_BILL["statements"][0], "closing_balance_cents": closing}
    path = tmp_path / "bill.json"
    path.write_text(json.dumps({**CARD_BILL, "statements": [statement]}), encoding="utf-8")
    return str(path)


def test_check_reports_reconciled_months_without_storing(db, statement_file, capsys):
    assert main(["--db", db, "check", statement_file]) == 0
    out = capsys.readouterr().out
    assert out.count("reconciles") == 3
    assert not Path(db).exists()


def test_check_fails_on_unbalanced_statement(db, tmp_path, capsys):
    assert main(["--db", db, "check", write_card_bill(tmp_path, closing=-312000)]) == 1
    assert "DOES NOT RECONCILE (difference R$ 3,45)" in capsys.readouterr().out


def test_imports_credit_card_bill_from_json(db, tmp_path, capsys):
    args = ["import", write_card_bill(tmp_path), "--owner", "jane", "--institution", "Acme Bank"]
    # The bill is for the current month: card bills are closed when issued.
    assert run(db, *args, "--kind", "credit_card", today=date(2026, 9, 15)) == 0
    out = capsys.readouterr().out
    assert "jane · Acme Bank (credit_card)" in out
    assert "2026-09     3 transactions  imported" in out


def test_categorize_export_and_apply(db, statement_file, tmp_path, capsys):
    run(db, *import_args(statement_file))
    request_path = tmp_path / "request.json"
    assert run(db, "categorize", "export", "2026-09", "-o", str(request_path)) == 0
    request = json.loads(request_path.read_text(encoding="utf-8"))
    payees = {p["payee"] for p in request["payees"]}
    assert "pix enviado · green grocer" in payees

    answer = tmp_path / "answer.json"
    answer.write_text(
        json.dumps(
            {
                "format": "fproject.categorization-suggestions/v1",
                "month": "2026-09",
                "suggestions": [
                    {
                        "payee": "pix enviado · green grocer",
                        "category": "groceries",
                        "scope": "household",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    capsys.readouterr()
    assert run(db, "categorize", "apply", str(answer)) == 0
    assert "1 transactions received a suggestion" in capsys.readouterr().out


def test_import_applies_existing_rules(db, tmp_path, capsys):
    from fproject.categories import Scope
    from fproject.categorization import Categorizer
    from fproject.storage import connect

    first = write_xlsx(tmp_path / "september.xlsx", NEWEST_FIRST[1:4])
    run(db, *import_args(str(first)))
    conn = connect(db)
    Categorizer(conn).confirm(
        Month(2026, 9), "pix enviado · green grocer", "groceries", Scope.HOUSEHOLD
    )
    conn.close()
    # October has a new statement with a payee that already has a rule.
    october = [("02/10/2026", "Pix enviado", "Green Grocer", "-R$ 12,50", "R$ 5.137,50")]
    capsys.readouterr()
    run(db, *import_args(str(write_xlsx(tmp_path / "october.xlsx", october))))
    assert "1 transactions categorized by your rules" in capsys.readouterr().out


def test_close_month(db, statement_file, capsys):
    run(db, *import_args(statement_file))
    capsys.readouterr()
    assert run(db, "close", "2026-09") == 0
    out = capsys.readouterr().out
    assert "3 transactions still need review" in out
    assert "Uncategorized" in out and "-R$ 850,00" in out
    assert "uncategorized inflows: R$ 4.000,00" in out
