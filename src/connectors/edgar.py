import os
import time

import requests

from .base import ConnectorError, FilingMetadata

TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL_TMPL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
ARCHIVE_URL_TMPL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_dashes}/{primary_document}"


class TickerNotFoundError(ConnectorError):
    pass


class NoFilingsFoundError(ConnectorError):
    pass


class _RateLimiter:
    """Keeps calls under SEC's ~10 req/sec fair-access guidance."""

    def __init__(self, min_interval: float = 0.11):
        self._min_interval = min_interval
        self._last_call: float | None = None

    def wait(self) -> None:
        now = time.monotonic()
        if self._last_call is not None:
            elapsed = now - self._last_call
            if elapsed < self._min_interval:
                time.sleep(self._min_interval - elapsed)
        self._last_call = time.monotonic()


def _filter_matching_filings(parallel_arrays: dict, form_type: str) -> list[dict]:
    """SEC returns filings.recent (and each paginated `files[]` entry) as
    parallel arrays keyed by field name, same index = same filing. Reshape
    into one dict per filing and keep only exact form_type matches."""
    forms = parallel_arrays["form"]
    return [
        {
            "form": forms[i],
            "filingDate": parallel_arrays["filingDate"][i],
            "accessionNumber": parallel_arrays["accessionNumber"][i],
            "primaryDocument": parallel_arrays["primaryDocument"][i],
        }
        for i in range(len(forms))
        if forms[i] == form_type
    ]


def _require_user_agent_from_env() -> str:
    user_agent = os.environ.get("EDGAR_USER_AGENT")
    if not user_agent:
        raise RuntimeError(
            "EDGAR_USER_AGENT is required (format: 'Name email@example.com'). "
            "See .env.example."
        )
    return user_agent


class EDGARConnector:
    """FilingConnector implementation backed by SEC EDGAR's public JSON endpoints."""

    def __init__(
        self,
        user_agent: str | None = None,
        session: requests.Session | None = None,
        min_interval: float = 0.11,
    ):
        self._user_agent = user_agent or _require_user_agent_from_env()
        self._session = session or requests.Session()
        self._rate_limiter = _RateLimiter(min_interval)
        self._cik_map: dict[str, int] | None = None

    def resolve_cik(self, ticker: str) -> int:
        ticker = ticker.upper()
        if self._cik_map is None:
            data = self._get(TICKER_MAP_URL).json()
            self._cik_map = {
                entry["ticker"].upper(): int(entry["cik_str"])
                for entry in data.values()
            }
        try:
            return self._cik_map[ticker]
        except KeyError:
            raise TickerNotFoundError(f"No CIK found for ticker {ticker!r}") from None

    def get_recent_filings(
        self, ticker: str, form_type: str = "10-K", count: int = 2
    ) -> list[FilingMetadata]:
        ticker = ticker.upper()
        cik = self.resolve_cik(ticker)
        submissions = self._get(SUBMISSIONS_URL_TMPL.format(cik=cik)).json()

        matches = _filter_matching_filings(submissions["filings"]["recent"], form_type)

        for page in submissions["filings"].get("files", []):
            if len(matches) >= count:
                break
            page_url = f"https://data.sec.gov/submissions/{page['name']}"
            page_data = self._get(page_url).json()
            matches.extend(_filter_matching_filings(page_data, form_type))

        if len(matches) < count:
            raise NoFilingsFoundError(
                f"Only found {len(matches)} {form_type!r} filings for {ticker!r}, "
                f"needed {count}"
            )

        matches.sort(key=lambda m: m["filingDate"], reverse=True)
        selected = matches[:count]

        return [
            FilingMetadata(
                ticker=ticker,
                cik=cik,
                form_type=form_type,
                filing_date=m["filingDate"],
                accession_number=m["accessionNumber"],
                primary_document=m["primaryDocument"],
                source_url=ARCHIVE_URL_TMPL.format(
                    cik=cik,
                    accession_no_dashes=m["accessionNumber"].replace("-", ""),
                    primary_document=m["primaryDocument"],
                ),
            )
            for m in selected
        ]

    def fetch_filing_document(self, filing: FilingMetadata) -> str:
        return self._get(filing.source_url).text

    def _get(self, url: str) -> requests.Response:
        self._rate_limiter.wait()
        resp = self._session.get(url, headers={"User-Agent": self._user_agent}, timeout=10)
        resp.raise_for_status()
        return resp
