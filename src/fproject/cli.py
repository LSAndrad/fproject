"""Command line interface: check, import, categorize and summarize statements."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path
from uuid import uuid4

from fproject.categorization import Categorizer, SuggestionsError
from fproject.closing import close_month
from fproject.domain import Account, AccountKind, Month
from fproject.extractors import ExtractionError, extractor_for
from fproject.importer import get_or_create_account, import_statements
from fproject.money import format_brl
from fproject.reconciliation import ReconciliationError, reconcile
from fproject.storage import Repository, connect
from fproject.summary import summarize

DEFAULT_DB = Path("data") / "fproject.db"


class UsageError(Exception):
    pass


def main(argv: list[str] | None = None, today: date | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "check":
            return _check(args)
        if args.command == "web":
            return _web(args)
        db_path = Path(args.db)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = connect(db_path)
        try:
            repo = Repository(conn)
            if args.command == "import":
                _import(repo, Categorizer(conn), args, today or date.today())
            elif args.command == "categorize":
                _categorize(Categorizer(conn), args)
            elif args.command == "close":
                _close(Categorizer(conn), args)
            else:
                _summary(repo, args)
        finally:
            conn.close()
    except (UsageError, ExtractionError, ReconciliationError, SuggestionsError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fproject", description=__doc__)
    parser.add_argument(
        "--db",
        default=os.environ.get("FPROJECT_DB", str(DEFAULT_DB)),
        help="SQLite database file (default: $FPROJECT_DB or %(default)s)",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    web = commands.add_parser("web", help="open the local web interface")
    web.add_argument("--port", type=int, default=8000)

    check = commands.add_parser(
        "check", help="extract and reconcile a statement file without storing it"
    )
    check.add_argument("file", type=Path)

    imp = commands.add_parser("import", help="import a statement file")
    imp.add_argument("file", type=Path)
    imp.add_argument("--owner", required=True, help="whose account it is, e.g. 'lucas'")
    imp.add_argument("--institution", required=True, help="bank name, e.g. 'Acme Bank'")
    imp.add_argument(
        "--kind", choices=[k.value for k in AccountKind], default=AccountKind.CHECKING.value
    )

    categorize = commands.add_parser(
        "categorize", help="hand payees to an assistant for categorization and apply its answer"
    )
    steps = categorize.add_subparsers(dest="step", required=True)
    export = steps.add_parser("export", help="write the payees awaiting review as JSON")
    export.add_argument("month", type=Month.parse, help="YYYY-MM")
    export.add_argument("-o", "--output", type=Path, help="file to write (default: stdout)")
    apply = steps.add_parser("apply", help="store suggestions (unconfirmed) from a JSON file")
    apply.add_argument("file", type=Path)

    close = commands.add_parser(
        "close", help="monthly closing across accounts: income, spending, what was left"
    )
    close.add_argument("month", type=Month.parse, help="YYYY-MM")

    summary = commands.add_parser("summary", help="show what came in and went out in a month")
    summary.add_argument("month", type=Month.parse, help="YYYY-MM")
    summary.add_argument("--top", type=int, default=10, help="how many payees to list")
    return parser


def _web(args: argparse.Namespace) -> int:
    import uvicorn

    from fproject.web import create_app

    print(f"fproject on http://127.0.0.1:{args.port}  (database: {args.db})")
    # Localhost only: the data never needs to leave the machine.
    uvicorn.run(create_app(Path(args.db)), host="127.0.0.1", port=args.port, log_level="warning")
    return 0


def _check(args: argparse.Namespace) -> int:
    """Print each month's totals and whether it reconciles. Exit 1 if any does not."""
    if not args.file.is_file():
        raise UsageError(f"file not found: {args.file}")
    statements = extractor_for(args.file).extract(args.file, uuid4())
    failures = 0
    for s in statements:
        try:
            reconcile(s)
            status = "reconciles"
        except ReconciliationError as error:
            failures += 1
            status = f"DOES NOT RECONCILE (difference {format_brl(error.difference_cents)})"
        print(
            f"{s.month}  {len(s.transactions):>4} transactions  "
            f"opening {format_brl(s.opening_balance_cents)}  in {format_brl(s.inflow_cents)}  "
            f"out {format_brl(s.outflow_cents)}  closing {format_brl(s.closing_balance_cents)}  "
            f"{status}"
        )
    if not statements:
        print("no transactions found")
    return 1 if failures else 0


def _import(
    repo: Repository, categorizer: Categorizer, args: argparse.Namespace, today: date
) -> None:
    if not args.file.is_file():
        raise UsageError(f"file not found: {args.file}")
    account = get_or_create_account(
        repo,
        Account(owner=args.owner, institution=args.institution, kind=AccountKind(args.kind)),
    )
    statements = extractor_for(args.file).extract(args.file, account.id)
    report = import_statements(repo, account, statements, today)

    print(f"{account.owner} · {account.institution} ({account.kind})")
    if not report.months:
        print("  no transactions found")
    for result in report.months:
        print(f"  {result.month}  {result.transactions:>4} transactions  {result.outcome}")
    categorized = categorizer.apply_rules()
    if categorized:
        print(f"  {categorized} transactions categorized by your rules")


def _categorize(categorizer: Categorizer, args: argparse.Namespace) -> None:
    if args.step == "export":
        text = json.dumps(categorizer.export_request(args.month), ensure_ascii=False, indent=1)
        if args.output:
            args.output.write_text(text + "\n", encoding="utf-8")
        else:
            print(text)
        return
    if not args.file.is_file():
        raise UsageError(f"file not found: {args.file}")
    try:
        document = json.loads(args.file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise UsageError(f"invalid JSON: {error}") from error
    written = categorizer.apply_suggestions(document)
    print(f"{written} transactions received a suggestion; confirm them in the review screen")


def _close(categorizer: Categorizer, args: argparse.Namespace) -> None:
    entries = categorizer.entries(args.month)
    if not entries:
        raise UsageError(f"no statements imported for {args.month}")
    c = close_month(args.month, entries)

    print(f"\nClosing {args.month}\n")
    if c.pending:
        print(f"  {c.pending} transactions still need review: numbers are partial\n")
    for label, cents in [
        ("Income", c.income_cents),
        ("Spending", -c.expenses_cents),
        ("Left over", c.left_over_cents),
        ("  of which saved", c.saved_cents),
    ]:
        print(f"  {label:<18}{format_brl(cents):>16}")

    print("\n  Spending by category")
    for cat in c.by_category:
        share = f"{cat.spent_cents * 100 // c.expenses_cents:>3}%" if c.expenses_cents else ""
        print(f"    {cat.label:<26}{format_brl(-cat.spent_cents):>16}  {share}")

    notes = []
    if c.card_detailed:
        notes.append(
            f"card bills replaced by their items: {format_brl(c.card_bills_replaced_cents)}"
        )
    if c.transfers_cents:
        notes.append(f"internal transfers left out: {format_brl(c.transfers_cents)}")
    if c.uncategorized_inflow_cents:
        notes.append(f"uncategorized inflows: {format_brl(c.uncategorized_inflow_cents)}")
    for note in notes:
        print(f"\n  {note}", end="")
    print("\n")


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
