import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from ..connectors.base import FilingMetadata
from ..connectors.section_parser import TaggedSection
from .schema import SCHEMA_DDL

DEFAULT_DB_PATH = Path("data/materiality.db")


def get_connection(db_path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_DDL)
    conn.commit()


def upsert_filing(conn: sqlite3.Connection, filing: FilingMetadata) -> int:
    conn.execute(
        """INSERT INTO filings
               (cik, ticker, form_type, filing_date, accession_number, source_url, fetched_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(accession_number) DO UPDATE SET fetched_at = excluded.fetched_at""",
        (
            filing.cik,
            filing.ticker,
            filing.form_type,
            filing.filing_date,
            filing.accession_number,
            filing.source_url,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    row = conn.execute(
        "SELECT id FROM filings WHERE accession_number = ?",
        (filing.accession_number,),
    ).fetchone()
    conn.commit()
    return row["id"]


def insert_sections(
    conn: sqlite3.Connection, filing_id: int, sections: list[TaggedSection]
) -> None:
    conn.execute("DELETE FROM sections WHERE filing_id = ?", (filing_id,))
    conn.executemany(
        "INSERT INTO sections (filing_id, item_key, heading_text, body_text) VALUES (?, ?, ?, ?)",
        [
            (filing_id, s.item_key, s.heading_text, s.body_text)
            for s in sections
        ],
    )
    conn.commit()


def get_filing_sections(conn: sqlite3.Connection, filing_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM sections WHERE filing_id = ?", (filing_id,)
    ).fetchall()
