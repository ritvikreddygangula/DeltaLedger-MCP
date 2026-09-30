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

CREATE TABLE IF NOT EXISTS findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    older_filing_id INTEGER NOT NULL REFERENCES filings(id) ON DELETE CASCADE,
    newer_filing_id INTEGER NOT NULL REFERENCES filings(id) ON DELETE CASCADE,
    item_key TEXT NOT NULL,
    category TEXT NOT NULL,
    tier TEXT NOT NULL,
    reasoning TEXT NOT NULL,
    older_excerpt TEXT,
    newer_excerpt TEXT,
    excerpt_verified INTEGER NOT NULL,
    confidence REAL NOT NULL,
    verifier_reasoning TEXT NOT NULL,
    final_tier TEXT NOT NULL,
    classifier_model TEXT NOT NULL,
    classifier_prompt_version TEXT NOT NULL,
    verifier_model TEXT NOT NULL,
    verifier_prompt_version TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_findings_older_filing_id ON findings(older_filing_id);
CREATE INDEX IF NOT EXISTS idx_findings_newer_filing_id ON findings(newer_filing_id);

CREATE TABLE IF NOT EXISTS llm_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cache_key TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL,
    output_json TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""
