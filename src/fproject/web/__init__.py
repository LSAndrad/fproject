"""Local web interface: import, review and close a month.

Server-rendered pages over the same layers the CLI uses. It binds to
localhost only: the data never needs to leave the machine.
"""

# No `from __future__ import annotations`: FastAPI must resolve the local
# `Conn` alias at runtime to inject the dependency.
import sqlite3
import tempfile
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from fproject import categories
from fproject.categories import Scope
from fproject.categorization import Categorizer
from fproject.closing import close_month
from fproject.domain import Account, AccountKind, Month
from fproject.extractors import ExtractionError, extractor_for
from fproject.importer import get_or_create_account, import_statements
from fproject.money import format_brl
from fproject.reconciliation import ReconciliationError
from fproject.storage import Repository, connect

_HERE = Path(__file__).parent


def create_app(db_path: Path, today: date | None = None) -> FastAPI:
    app = FastAPI(title="fproject", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=_HERE / "static"), name="static")
    templates = Jinja2Templates(directory=_HERE / "templates")
    templates.env.filters["brl"] = format_brl
    templates.env.globals["categories"] = categories.CATEGORIES
    templates.env.globals["scopes"] = list(Scope)

    def get_conn() -> Iterator[sqlite3.Connection]:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = connect(db_path, check_same_thread=False)
        try:
            yield conn
        finally:
            conn.close()

    Conn = Annotated[sqlite3.Connection, Depends(get_conn)]

    def render(request: Request, name: str, conn: sqlite3.Connection, **context) -> HTMLResponse:
        months = Categorizer(conn).months()
        return templates.TemplateResponse(
            request, name, {"months": months, "current": context.get("month"), **context}
        )

    @app.get("/")
    def home(conn: Conn) -> RedirectResponse:
        months = Categorizer(conn).months()
        target = f"/close/{months[-1]}" if months else "/import"
        return RedirectResponse(target, status_code=303)

    @app.get("/import", response_class=HTMLResponse)
    def import_form(request: Request, conn: Conn) -> HTMLResponse:
        return render(request, "import.html", conn, accounts=_accounts(conn))

    @app.post("/import", response_class=HTMLResponse)
    async def import_file(
        request: Request,
        conn: Conn,
        file: Annotated[UploadFile, File()],
        owner: Annotated[str, Form()],
        institution: Annotated[str, Form()],
        kind: Annotated[str, Form()],
    ) -> HTMLResponse:
        repo = Repository(conn)
        categorizer = Categorizer(conn)
        try:
            account = get_or_create_account(
                repo,
                Account(
                    owner=owner.strip(), institution=institution.strip(), kind=AccountKind(kind)
                ),
            )
            suffix = Path(file.filename or "").suffix
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / f"upload{suffix}"
                path.write_bytes(await file.read())
                statements = extractor_for(path).extract(path, account.id)
            report = import_statements(repo, account, statements, today or date.today())
            categorized = categorizer.apply_rules()
        except (ExtractionError, ReconciliationError, ValueError) as error:
            return render(request, "import.html", conn, accounts=_accounts(conn), error=str(error))
        return render(
            request,
            "import.html",
            conn,
            accounts=_accounts(conn),
            report=report,
            categorized=categorized,
            filename=file.filename,
        )

    @app.get("/review/{month}", response_class=HTMLResponse)
    def review(request: Request, conn: Conn, month: str, saved: int | None = None):
        m = Month.parse(month)
        groups = Categorizer(conn).review_groups(m)
        return render(request, "review.html", conn, month=m, groups=groups, saved=saved)

    @app.post("/review/{month}")
    async def save_review(request: Request, conn: Conn, month: str) -> RedirectResponse:
        m = Month.parse(month)
        form = await request.form()
        categorizer = Categorizer(conn)
        saved = 0
        for key in form:
            if not key.startswith("payee_"):
                continue
            index = key.removeprefix("payee_")
            category = form.get(f"category_{index}")
            if category:
                scope = Scope(form.get(f"scope_{index}", Scope.PERSONAL))
                saved += categorizer.confirm(m, str(form[key]), str(category), scope)
        return RedirectResponse(f"/review/{m}?saved={saved}", status_code=303)

    @app.get("/close/{month}", response_class=HTMLResponse)
    def close(request: Request, conn: Conn, month: str) -> HTMLResponse:
        m = Month.parse(month)
        closing = close_month(m, Categorizer(conn).entries(m))
        return render(request, "close.html", conn, month=m, c=closing)

    return app


def _accounts(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM accounts ORDER BY owner, institution, kind").fetchall()
