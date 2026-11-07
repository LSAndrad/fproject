# 0003. Reconciliation gates every import

**Status:** accepted (2026-10)

## Context
Extractors can be wrong in silent ways: a skipped line, a flipped sign, a misread amount. This matters more once some extraction is done by an AI.

## Decision
A statement is stored only if `opening balance + Σ transactions = closing balance`, using the totals printed by the bank itself. When the export has a running balance, every row is checked. A file is all or nothing: one failing month imports nothing. `fproject check` runs the same validation without storing, as the feedback loop for whoever produces the data.

## Consequences
- The difference in the error message usually points at the faulty line.
- Any extractor, deterministic or AI, earns trust the same way.
- A bank document without usable totals cannot be imported. So far every real one has had them.
