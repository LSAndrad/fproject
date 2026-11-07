# 0004. Credit card PDFs become JSON written by an assistant

**Status:** accepted (2026-11)

## Context
Credit card bills only exist as PDFs with complex layouts (two interleaved columns, several cardholders, installments, foreign currency lines). A layout parser per bank is brittle; an API-based LLM extractor needs an API account, which was not available.

## Decision
Define a JSON statement format (`fproject.statements/v1`) and treat it as just another extractor input. Today Claude Code produces it by following a versioned skill (`.claude/skills/extract-card-bill`), iterating with `fproject check` until it reconciles. An API-based extractor will later write the same format.

## Consequences
- The import path does not care who wrote the JSON; reconciliation decides.
- Extraction needs a human-in-the-loop session for now: fine for one or two bills a month.
- The PDF content is sent to the assistant's provider either way; the README says which paths send data out.
