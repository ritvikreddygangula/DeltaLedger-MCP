from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class FilingMetadata:
    ticker: str
    cik: int
    form_type: str
    filing_date: str  # ISO "YYYY-MM-DD"
    accession_number: str
    primary_document: str
    source_url: str


class FilingConnector(Protocol):
    def get_recent_filings(
        self, ticker: str, form_type: str, count: int
    ) -> list[FilingMetadata]: ...

    def fetch_filing_document(self, filing: FilingMetadata) -> str: ...


class ConnectorError(Exception):
    """Base class for all connector errors."""
