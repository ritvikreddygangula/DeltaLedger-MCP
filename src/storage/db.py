from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from .schema import SCHEMA_DDL

if TYPE_CHECKING:
    # Pipeline-only types, needed here only for annotations on
    # pipeline-only functions (insert_findings, upsert_filing,
    # insert_sections). This module is also imported by the read-only
    # API/MCP layer, which deliberately excludes the heavy pipeline
    # dependencies (openai, beautifulsoup4, etc.) to stay under Lambda's
    # package size limit -- importing these eagerly at module load would
    # break that Lambda at cold start with ModuleNotFoundError.
    from ..agents.verifier import VerifiedFinding
    from ..connectors.base import FilingMetadata
    from ..connectors.section_parser import TaggedSection

# Local-only storage for ingestion intermediates (parsed sections, the LLM
# cache) -- never read by the deployed API/MCP Lambda, which serves
# `findings` from S3 instead (see docs/DROP_RDS_SPEC.md). One person, one
# machine, no concurrent writers, so SQLite is simpler than a real database
# server for this without giving anything up.
DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "materiality.db"


def get_connection(db_path: str | Path | None = None) -> sqlite3.Connection:
    db_path = db_path or os.environ.get("DATABASE_PATH") or DEFAULT_DB_PATH
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")  # off by default in SQLite, unlike Postgres
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_DDL)
    conn.commit()


def upsert_filing(conn: sqlite3.Connection, filing: FilingMetadata) -> int:
    row = conn.execute(
        """INSERT INTO filings
               (cik, ticker, form_type, filing_date, accession_number, source_url, fetched_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT (accession_number) DO UPDATE SET fetched_at = excluded.fetched_at
           RETURNING id""",
        (
            filing.cik,
            filing.ticker,
            filing.form_type,
            filing.filing_date,
            filing.accession_number,
            filing.source_url,
            datetime.now(timezone.utc).isoformat(),
        ),
    ).fetchone()
    conn.commit()
    return row["id"]


def insert_sections(
    conn: sqlite3.Connection, filing_id: int, sections: list[TaggedSection]
) -> None:
    cur = conn.cursor()
    cur.execute("DELETE FROM sections WHERE filing_id = ?", (filing_id,))
    cur.executemany(
        "INSERT INTO sections (filing_id, item_key, heading_text, body_text) VALUES (?, ?, ?, ?)",
        [(filing_id, s.item_key, s.heading_text, s.body_text) for s in sections],
    )
    conn.commit()


def get_filing_sections(conn: sqlite3.Connection, filing_id: int) -> list[dict]:
    rows = conn.execute("SELECT * FROM sections WHERE filing_id = ?", (filing_id,)).fetchall()
    return [dict(r) for r in rows]


def get_filings_for_ticker(
    conn: sqlite3.Connection, ticker: str, form_type: str = "10-K", limit: int = 2
) -> list[dict]:
    rows = conn.execute(
        """SELECT * FROM filings WHERE ticker = ? AND form_type = ?
           ORDER BY filing_date DESC LIMIT ?""",
        (ticker.upper(), form_type, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def insert_findings(
    conn: sqlite3.Connection,
    older_filing_id: int,
    newer_filing_id: int,
    verified_findings: list[VerifiedFinding],
) -> None:
    """Append-only: unlike upsert_filing (a filing is an immutable external
    document, safe to dedup) or insert_sections (replaces a filing's own
    sections wholesale), a findings row is evidence from one specific run
    with one specific model/prompt version. Overwriting on rerun would
    destroy the audit trail this table exists to build.
    """
    cur = conn.cursor()
    cur.executemany(
        """INSERT INTO findings
               (older_filing_id, newer_filing_id, item_key, category, tier, reasoning,
                older_excerpt, newer_excerpt, excerpt_verified, confidence,
                verifier_reasoning, final_tier, classifier_model, classifier_prompt_version,
                verifier_model, verifier_prompt_version, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            (
                older_filing_id,
                newer_filing_id,
                vf.finding.item_key,
                vf.finding.category,
                vf.finding.tier,
                vf.finding.reasoning,
                vf.finding.older_excerpt,
                vf.finding.newer_excerpt,
                vf.excerpt_verified,
                vf.confidence,
                vf.verifier_reasoning,
                vf.final_tier,
                vf.classifier_model,
                vf.classifier_prompt_version,
                vf.verifier_model,
                vf.verifier_prompt_version,
                datetime.now(timezone.utc).isoformat(),
            )
            for vf in verified_findings
        ],
    )
    conn.commit()


def get_findings_for_filing_pair(
    conn: sqlite3.Connection, older_filing_id: int, newer_filing_id: int
) -> list[dict]:
    """Returns only the most recent pipeline run's findings for this filing
    pair, not the full history. insert_findings is deliberately append-only
    (see its docstring) so every run's findings stay around as an audit
    trail, but a live API/MCP consumer wants current results, not every
    findings row from every historical rerun of the pipeline stacked
    together. "Most recent run" = every finding within 10 seconds of the
    latest created_at for this pair -- one run's insert_findings call is a
    single batch INSERT, so a real run's rows land within microseconds of
    each other, while separate runs are reliably minutes apart.
    """
    rows = conn.execute(
        """WITH latest AS (
               SELECT MAX(created_at) AS max_created_at FROM findings
               WHERE older_filing_id = ? AND newer_filing_id = ?
           )
           SELECT f.* FROM findings f, latest
           WHERE f.older_filing_id = ? AND f.newer_filing_id = ?
             AND datetime(f.created_at) >= datetime(latest.max_created_at, '-10 seconds')
           ORDER BY f.id""",
        (older_filing_id, newer_filing_id, older_filing_id, newer_filing_id),
    ).fetchall()
    findings = [dict(r) for r in rows]
    for f in findings:
        if "excerpt_verified" in f:
            f["excerpt_verified"] = bool(f["excerpt_verified"])  # SQLite has no native boolean
    return findings
