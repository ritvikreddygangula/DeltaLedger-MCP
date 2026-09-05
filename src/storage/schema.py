SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS filings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cik INTEGER NOT NULL,
    ticker TEXT NOT NULL,
    form_type TEXT NOT NULL,
    filing_date TEXT NOT NULL,
    accession_number TEXT NOT NULL UNIQUE,
    source_url TEXT NOT NULL,
    fetched_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filing_id INTEGER NOT NULL REFERENCES filings(id) ON DELETE CASCADE,
    item_key TEXT NOT NULL,
    heading_text TEXT NOT NULL,
    body_text TEXT NOT NULL,
    UNIQUE(filing_id, item_key)
);

CREATE INDEX IF NOT EXISTS idx_sections_filing_id ON sections(filing_id);
CREATE INDEX IF NOT EXISTS idx_filings_ticker ON filings(ticker);
"""
