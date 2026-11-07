# 0001. One statement per account per month

**Status:** accepted (2026-10)

## Context
The first prototype deduplicated individual transactions, by bank id and then by position within a day. Bank ids proved unreliable (some banks emit the same placeholder for every line), and positional matching broke as soon as a bank reordered lines. Most of the prototype's complexity came from this.

## Decision
The unit of import is a **statement**: everything one account recorded in one reference month. It is unique per *(account, month)*, enforced by the database. Transactions get a UUID generated at import; no bank-provided identifier is a key.

## Consequences
- No per-transaction deduplication at all. Re-importing a month is refused as a whole.
- Overlapping exports work: months already imported are skipped.
- A partial month must never be imported, or it blocks the complete one: the current month of a checking account is skipped until it ends.
- Replacing a month (e.g. after a bank correction) needs an explicit command. Not built yet; `ON DELETE CASCADE` from statement to transactions makes it cheap.
