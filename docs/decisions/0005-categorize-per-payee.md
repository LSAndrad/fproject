# 0005. Categorize per payee; rules; unconfirmed suggestions

**Status:** accepted (2026-11)

## Context
The prototype categorized transaction by transaction with hand-written substring rules. Reviewing a month meant over a hundred decisions, and the rules were never maintained.

## Decision
- Decisions are made per **payee**: the description, plus the counterparty column on checking accounts. On credit cards, details (installment, currency) are left out so one merchant stays one payee.
- Every confirmed decision becomes an exact-match rule, applied to new imports automatically.
- An assistant can categorize too (`categorize export` / `categorize apply`). Its answers are stored as **unconfirmed suggestions**, shown prefilled in the review screen, and never overwrite a confirmed category.
- Categories are a fixed list in code; scope is personal or household.

## Consequences
- A month with ~120 transactions becomes ~80 decisions the first time and far fewer after.
- One payee with genuinely different categories (a marketplace) gets a single category. Accepted for v0.1.
- Changing a confirmed category is not supported yet.
- Confirmed decisions are labeled data for a future classifier.
