SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS filings (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cik INTEGER NOT NULL,
    ticker TEXT NOT NULL,
    form_type TEXT NOT NULL,
    filing_date TEXT NOT NULL,
    accession_number TEXT NOT NULL UNIQUE,
    source_url TEXT NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS sections (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    filing_id INTEGER NOT NULL REFERENCES filings(id) ON DELETE CASCADE,
    item_key TEXT NOT NULL,
    heading_text TEXT NOT NULL,
    body_text TEXT NOT NULL,
    UNIQUE(filing_id, item_key)
);

CREATE INDEX IF NOT EXISTS idx_sections_filing_id ON sections(filing_id);
CREATE INDEX IF NOT EXISTS idx_filings_ticker ON filings(ticker);
"""
