---
name: extract-card-bill
description: Turn a credit card bill PDF into fproject's JSON statement format and verify it reconciles. Use when the user wants to import a credit card bill (fatura do cartão) that only exists as a PDF.
---

# Extract a credit card bill into JSON

Credit card bills are PDFs with layouts no deterministic parser in this repo
handles. You are the extractor: read the PDF, write a JSON file in the
`fproject.statements/v1` format (documented in
`src/fproject/extractors/json_statement.py`), and prove it with
`fproject check` before handing it over. The user then imports it with
`fproject import <file>.json --kind credit_card`.

## Privacy rules

- The PDF and the JSON contain personal data. Write them **only** under
  `data/` (ignored by git) or the scratchpad. Never into `tests/`, `docs/`
  or any tracked path, and never quote real values in commits or docs.
- Throwaway parsing scripts go in the scratchpad, not in the repository.

## Steps

1. **Read the text, one column at a time.** Many bills use two columns per
   page; plain text extraction interleaves them. With pdfplumber, crop each
   page into left and right halves and extract each separately:
   `page.crop((0, 0, page.width / 2, page.height)).extract_text()`.
   Run Python with `-I` and keep the PDF in its own directory.
2. **Find the bill's own summary** (e.g. "Resumo da Fatura"): previous
   balance, purchases, payments, credits, and the total due. These are the
   ground truth you reconcile against.
3. **Write one statement** for the bill:
   - `month`: the month the bill is **due/paid** (`YYYY-MM`), not the
     purchase period. Spending is counted when it leaves the checking account.
   - `opening_balance_cents`: minus the previous bill's balance.
   - `closing_balance_cents`: minus the total due of this bill.
   - Amounts are from the card's point of view: **purchases, fees, IOF and
     interest are negative; the payment of the previous bill and refunds are
     positive.** On most bills this means flipping the printed sign.
4. **One transaction per line item**, in the order printed:
   - `posted_on`: the purchase date. Bills omit the year: use the bill's year
     unless the month is after the bill's month (old installments), then
     use the previous year.
   - `description`: the merchant as printed.
   - `details`: installment as `installment 05/10`; foreign purchases as
     `USD 21,36`; join several with `; `.
   - `cardholder`: the name heading the section. Bills group purchases by
     card, including additional cards held by someone else.
5. **Watch for lines that are not transactions**: exchange rate lines
   ("COTAÇÃO DOLAR"), section subtotals ("VALOR TOTAL"), headers, limits,
   payment options, interest tables, bill history. And for transactions
   without a date of their own, such as IOF on a foreign purchase: use the
   date of the purchase above it.
6. **Cross-check every subtotal** the bill prints (per cardholder, per
   section) against the sum of what you extracted before running the check.
7. **Run the check** and iterate until it reconciles:

   ```bash
   uv run fproject check data/statements/card-YYYY-MM.json
   ```

   A difference in the output points at what is missing or misread: an amount
   equal to a single line usually means that line was skipped or its sign is
   wrong.
8. **Report** the number of transactions, the total, and that it reconciles.
   If the bill's total matches the "card bill payment" line in the checking
   account statement of the same month, say so: that is the strongest
   evidence the extraction is complete.
