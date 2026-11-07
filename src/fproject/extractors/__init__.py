"""The extractor contract: every statement format implements it."""

from pathlib import Path
from typing import Protocol
from uuid import UUID

from fproject.domain import Statement


class ExtractionError(ValueError):
    """A file could not be read as a statement."""


class Extractor(Protocol):
    def extract(self, source: Path, account_id: UUID) -> list[Statement]:
        """Read a statement file and return one Statement per month it covers.

        Extractors only parse; they never touch the database. Every returned
        statement is reconciled before it is stored.
        """
        ...


def extractor_for(path: Path) -> Extractor:
    """Pick the extractor from the file extension."""
    # Imported here: the extractor modules import ExtractionError from this one.
    from fproject.extractors.json_statement import JsonStatementExtractor
    from fproject.extractors.spreadsheet import SpreadsheetExtractor

    suffix = path.suffix.lower()
    if suffix == ".xlsx":
        return SpreadsheetExtractor()
    if suffix == ".json":
        return JsonStatementExtractor()
    raise ExtractionError(f"unsupported file type: {suffix or path.name} (supported: .xlsx, .json)")
