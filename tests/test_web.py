import json
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sample_statements import CARD_BILL, NEWEST_FIRST, write_xlsx

from fproject.web import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path / "data" / "fproject.db", today=date(2026, 11, 1))
    with TestClient(app) as client:
        yield client


@pytest.fixture
def statement(tmp_path):
    return write_xlsx(tmp_path / "statement.xlsx", NEWEST_FIRST)


def upload(client, path, kind="checking"):
    with open(path, "rb") as f:
        return client.post(
            "/import",
            data={"owner": "jane", "institution": "Acme Bank", "kind": kind},
            files={"file": (path.name, f)},
        )


def test_home_goes_to_import_when_empty(client):
    response = client.get("/", follow_redirects=False)
    assert response.headers["location"] == "/import"


def test_import_shows_each_month(client, statement):
    page = upload(client, statement).text
    assert "2026-08</span> · 2 transactions · imported" in page
    assert "/review/2026-09" in page


def test_home_goes_to_latest_closing_after_import(client, statement):
    upload(client, statement)
    response = client.get("/", follow_redirects=False)
    assert response.headers["location"] == "/close/2026-10"


def test_import_error_is_shown_and_nothing_stored(client, tmp_path):
    bad = write_xlsx(tmp_path / "bad.xlsx", NEWEST_FIRST, header=("Date", "Memo"))
    page = upload(client, bad).text
    assert "Nothing was imported." in page and "no header row" in page


def test_import_credit_card_json(client, tmp_path):
    path = tmp_path / "bill.json"
    path.write_text(json.dumps(CARD_BILL), encoding="utf-8")
    page = upload(client, path, kind="credit_card").text
    assert "2026-09</span> · 3 transactions · imported" in page


def test_review_and_close(client, statement):
    upload(client, statement)
    review = client.get("/review/2026-09").text
    assert "Pix enviado · Green Grocer" in review

    form = {}
    labels = [
        "pix recebido · acme consulting",
        "pagamento de boleto · building condo",
        "pix enviado · green grocer",
    ]
    choices = ["income", "housing", "groceries"]
    for i, (key, category) in enumerate(zip(labels, choices, strict=True), start=1):
        form |= {f"payee_{i}": key, f"category_{i}": category, f"scope_{i}": "household"}
    response = client.post("/review/2026-09", data=form, follow_redirects=False)
    assert response.headers["location"] == "/review/2026-09?saved=3"
    assert "Nothing to review" in client.get("/review/2026-09").text

    close = client.get("/close/2026-09").text
    assert "R$ 4.000,00" in close  # income
    assert "-R$ 850,00" in close  # spending
    assert "R$ 3.150,00" in close  # left over
    assert "still need review" not in close


def test_review_leaves_rows_without_category_for_later(client, statement):
    upload(client, statement)
    data = {"payee_1": "pix enviado · green grocer", "category_1": "", "scope_1": "personal"}
    client.post("/review/2026-09", data=data)
    assert "Pix enviado · Green Grocer" in client.get("/review/2026-09").text
