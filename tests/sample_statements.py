"""Synthetic bank exports shared by the tests. No real data."""

from pathlib import Path

from openpyxl import Workbook

from fproject.extractors.json_statement import FORMAT

HEADER = ("Data", "Descrição", "Detalhe", "Valor", "Saldo")

# A checking account, newest first like real bank exports.
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


def write_xlsx(path: Path, rows=NEWEST_FIRST, header=HEADER, preamble=True) -> Path:
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


# A credit card bill in the JSON interchange format; reconciles.
CARD_BILL = {
    "format": FORMAT,
    "statements": [
        {
            "month": "2026-09",
            "opening_balance_cents": -250000,
            "closing_balance_cents": -312345,
            "transactions": [
                {
                    "posted_on": "2026-08-10",
                    "description": "PAYMENT RECEIVED",
                    "amount_cents": 250000,
                },
                {
                    "posted_on": "2026-08-12",
                    "description": "CORNER BAKERY",
                    "details": "installment 2/3",
                    "cardholder": "JANE DOE",
                    "amount_cents": -300000,
                },
                {
                    "posted_on": "2026-08-20",
                    "description": "BOOKSTORE",
                    "cardholder": "JOHN DOE",
                    "amount_cents": -12345,
                },
            ],
        }
    ],
}
