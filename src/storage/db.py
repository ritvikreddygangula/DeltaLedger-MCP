from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import psycopg
from psycopg.rows import dict_row

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


def _require_database_url_from_env() -> str:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is required (format: 'postgresql://user:pass@host:5432/dbname'). "
            "See .env.example."
        )
    return database_url


def get_connection(database_url: str | None = None) -> psycopg.Connection:
    database_url = database_url or _require_database_url_from_env()
    return psycopg.connect(database_url, row_factory=dict_row)


def init_db(conn: psycopg.Connection) -> None:
    conn.execute(SCHEMA_DDL)
    conn.commit()


def upsert_filing(conn: psycopg.Connection, filing: FilingMetadata) -> int:
    row = conn.execute(
        """INSERT INTO filings
               (cik, ticker, form_type, filing_date, accession_number, source_url, fetched_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (accession_number) DO UPDATE SET fetched_at = EXCLUDED.fetched_at
           RETURNING id""",
        (
            filing.cik,
            filing.ticker,
            filing.form_type,
            filing.filing_date,
            filing.accession_number,
            filing.source_url,
            datetime.now(timezone.utc),
        ),
    ).fetchone()
    conn.commit()
    return row["id"]


def insert_sections(
    conn: psycopg.Connection, filing_id: int, sections: list[TaggedSection]
) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM sections WHERE filing_id = %s", (filing_id,))
        cur.executemany(
            "INSERT INTO sections (filing_id, item_key, heading_text, body_text) VALUES (%s, %s, %s, %s)",
            [(filing_id, s.item_key, s.heading_text, s.body_text) for s in sections],
        )
    conn.commit()


def get_filing_sections(conn: psycopg.Connection, filing_id: int) -> list[dict]:
    return conn.execute(
        "SELECT * FROM sections WHERE filing_id = %s", (filing_id,)
    ).fetchall()


def get_filings_for_ticker(
    conn: psycopg.Connection, ticker: str, form_type: str = "10-K", limit: int = 2
) -> list[dict]:
    return conn.execute(
        """SELECT * FROM filings WHERE ticker = %s AND form_type = %s
           ORDER BY filing_date DESC LIMIT %s""",
        (ticker.upper(), form_type, limit),
    ).fetchall()


def insert_findings(
    conn: psycopg.Connection,
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
    with conn.cursor() as cur:
        cur.executemany(
            """INSERT INTO findings
                   (older_filing_id, newer_filing_id, item_key, category, tier, reasoning,
                    older_excerpt, newer_excerpt, excerpt_verified, confidence,
                    verifier_reasoning, final_tier, classifier_model, classifier_prompt_version,
                    verifier_model, verifier_prompt_version, created_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
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
                    datetime.now(timezone.utc),
                )
                for vf in verified_findings
            ],
        )
    conn.commit()


def get_findings_for_filing_pair(
    conn: psycopg.Connection, older_filing_id: int, newer_filing_id: int
) -> list[dict]:
    """Returns only the most recent pipeline run's findings for this filing
    pair, not the full history. insert_findings is deliberately append-only
    (see its docstring) so every run's findings stay in Postgres as an audit
    trail, but a live API/MCP consumer wants current results, not every
    findings row from every historical rerun of the pipeline stacked
    together. "Most recent run" = every finding within 10 seconds of the
    latest created_at for this pair -- one run's insert_findings call is a
    single batch INSERT, so a real run's rows land within microseconds of
    each other, while separate runs are reliably minutes apart.
    """
    return conn.execute(
        """WITH latest AS (
               SELECT MAX(created_at) AS max_created_at FROM findings
               WHERE older_filing_id = %s AND newer_filing_id = %s
           )
           SELECT f.* FROM findings f, latest
           WHERE f.older_filing_id = %s AND f.newer_filing_id = %s
             AND f.created_at >= latest.max_created_at - INTERVAL '10 seconds'
           ORDER BY f.id""",
        (older_filing_id, newer_filing_id, older_filing_id, newer_filing_id),
    ).fetchall()
