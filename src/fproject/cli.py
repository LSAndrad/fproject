"""Command line interface: `fproject import` and `fproject summary`."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

from fproject.domain import Account, AccountKind, Month
from fproject.extractors import Extractor
from fproject.extractors.spreadsheet import SpreadsheetError, SpreadsheetExtractor
from fproject.importer import get_or_create_account, import_statements
from fproject.money import format_brl
from fproject.reconciliation import ReconciliationError
from fproject.storage import Repository, connect
from fproject.summary import summarize

DEFAULT_DB = Path("data") / "fproject.db"


class UsageError(Exception):
    pass


def main(argv: list[str] | None = None, today: date | None = None) -> int:
    args = _parser().parse_args(argv)
    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    try:
        repo = Repository(conn)
        if args.command == "import":
            _import(repo, args, today or date.today())
        else:
            _summary(repo, args)
    except (UsageError, SpreadsheetError, ReconciliationError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    finally:
        conn.close()
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fproject", description=__doc__)
    parser.add_argument(
        "--db",
        default=os.environ.get("FPROJECT_DB", str(DEFAULT_DB)),
        help="SQLite database file (default: $FPROJECT_DB or %(default)s)",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    imp = commands.add_parser("import", help="import a statement file")
    imp.add_argument("file", type=Path)
    imp.add_argument("--owner", required=True, help="whose account it is, e.g. 'lucas'")
    imp.add_argument("--institution", required=True, help="bank name, e.g. 'Acme Bank'")
    imp.add_argument(
        "--kind", choices=[k.value for k in AccountKind], default=AccountKind.CHECKING.value
    )

    summary = commands.add_parser("summary", help="show what came in and went out in a month")
    summary.add_argument("month", type=Month.parse, help="YYYY-MM")
    summary.add_argument("--top", type=int, default=10, help="how many payees to list")
    return parser


def _extractor_for(path: Path) -> Extractor:
    if path.suffix.lower() == ".xlsx":
        return SpreadsheetExtractor()
    raise UsageError(f"unsupported file type: {path.suffix or path.name} (supported: .xlsx)")


def _import(repo: Repository, args: argparse.Namespace, today: date) -> None:
    if not args.file.is_file():
        raise UsageError(f"file not found: {args.file}")
    account = get_or_create_account(
        repo,
        Account(owner=args.owner, institution=args.institution, kind=AccountKind(args.kind)),
    )
    statements = _extractor_for(args.file).extract(args.file, account.id)
    report = import_statements(repo, account, statements, today)

    print(f"{account.owner} · {account.institution} ({account.kind})")
    if not report.months:
        print("  no transactions found")
    for result in report.months:
        print(f"  {result.month}  {result.transactions:>4} transactions  {result.outcome}")


def _summary(repo: Repository, args: argparse.Namespace) -> None:
    statements = repo.list_statements(args.month)
    if not statements:
        raise UsageError(f"no statements imported for {args.month}")

    for statement in statements:
        account = repo.get_account(statement.account_id)
        summary = summarize(statement, args.top)
        print(f"\n{args.month} · {account.owner} · {account.institution} ({account.kind})\n")
        for label, cents in [
            ("Opening balance", statement.opening_balance_cents),
            ("In", statement.inflow_cents),
            ("Out", statement.outflow_cents),
            ("Net", statement.net_cents),
            ("Closing balance", statement.closing_balance_cents),
        ]:
            print(f"  {label:<18}{format_brl(cents):>16}")
        if summary.top_outflows:
            print("\n  Where the money went")
            width = max(len(p.label) for p in summary.top_outflows)
            for rank, payee in enumerate(summary.top_outflows, start=1):
                times = f"({payee.count}x)" if payee.count > 1 else ""
                amount = format_brl(payee.total_cents)
                print(f"  {rank:>3}. {payee.label:<{width}}  {amount:>15}  {times}".rstrip())
    print()


if __name__ == "__main__":
    raise SystemExit(main())
