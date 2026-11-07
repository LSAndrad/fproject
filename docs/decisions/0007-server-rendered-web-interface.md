# 0007. Server-rendered web interface for v0.1

**Status:** accepted (2026-11)

## Context
A design prototype exists for a fuller app (import, review, rules, closing, agents, settings). The goal of v0.1 is to find out whether the product is useful, as fast as possible.

## Decision
FastAPI + Jinja2 templates, no JavaScript build, bound to localhost: three screens (import, review, closing) over the same layers the CLI uses. The visual language follows the prototype; the UI is in English, like the code.

Differences from the prototype, on purpose:
- Import results are per **month** (imported / already imported / month not over), not per transaction, following [0001](0001-one-statement-per-account-month.md).
- Review is one table per payee with suggestions prefilled, instead of a card-by-card flow.
- Rules, agents and settings screens are left for later.

## Consequences
A richer client (Vite + TypeScript) can replace the templates later behind a JSON API; the domain layers do not change.
