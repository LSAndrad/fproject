# 0006. How the monthly closing counts money

**Status:** accepted (2026-11)

## Context
Counting raw cash flow double counts: a credit card bill shows up once as a payment in checking and again as the bill's purchases. Transfers between own accounts and money sent to investments are not spending either.

## Decision
- **Card bills:** the payment in checking is replaced by the bill's items when that owner's card statement for the month is imported; otherwise the payment counts as one expense, so money never silently disappears.
- **Which month:** the bill counts in the month it is paid (cash basis), so the closing matches what left the checking account. Each item keeps its purchase date for detail. Installments make an accrual view by purchase date misleading.
- **Income** is what is categorized as income. Other inflows in an expense category (a friend paying back) reduce that category.
- **Transfers** count nowhere; **investments** count as saved, part of what was left over.
- **Uncategorized** outflows still count as spending, so the leftover is never overstated during review; the closing says how many transactions are pending.

## Consequences
The closing is a consumption view, not a bank balance; the per-account table keeps the raw flows visible.
