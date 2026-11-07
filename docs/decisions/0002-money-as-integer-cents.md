# 0002. Money as signed integer cents

**Status:** accepted (2026-10)

## Context
Binary floats cannot represent 0.10 exactly; sums of many amounts drift.

## Decision
Every amount is an `int` number of cents, negative for outflows. The domain rejects floats and booleans; SQLite tables are `STRICT` so the database rejects them too. Conversion to reais happens only for display (`format_brl`) and when parsing text (`parse_brl`, which rejects anything ambiguous instead of guessing).

## Consequences
Extractors must convert explicitly, including assistant-written JSON: a float there is a validation error, not a rounding question.
