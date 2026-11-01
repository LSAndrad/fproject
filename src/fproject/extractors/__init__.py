"""The extractor contract: every statement format implements it."""

from pathlib import Path
from typing import Protocol
from uuid import UUID

from fproject.domain import Statement


class Extractor(Protocol):
    def extract(self, source: Path, account_id: UUID) -> list[Statement]:
        """Read a statement file and return one Statement per month it covers.

        Extractors only parse; they never touch the database. Every returned
        statement is reconciled before it is stored.
        """
        ...
