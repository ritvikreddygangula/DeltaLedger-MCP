import hashlib
import json
from datetime import datetime, timezone

import psycopg


def compute_cache_key(**parts) -> str:
    """Deterministic key over arbitrary JSON-serializable parts -- callers
    pass exactly the inputs that determine an LLM call's output (section
    text, claims, model, prompt version, reasoning effort) so an identical
    call, on an identical filing pair, is always a cache hit.
    """
    canonical = json.dumps(parts, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def get_cached(conn: psycopg.Connection, cache_key: str) -> str | None:
    row = conn.execute(
        "SELECT output_json FROM llm_cache WHERE cache_key = %s", (cache_key,)
    ).fetchone()
    return row["output_json"] if row else None


def set_cached(
    conn: psycopg.Connection,
    cache_key: str,
    kind: str,
    output_json: str,
    model: str,
    prompt_version: str,
) -> None:
    conn.execute(
        """INSERT INTO llm_cache (cache_key, kind, output_json, model, prompt_version, created_at)
           VALUES (%s, %s, %s, %s, %s, %s)
           ON CONFLICT (cache_key) DO NOTHING""",
        (cache_key, kind, output_json, model, prompt_version, datetime.now(timezone.utc)),
    )
    conn.commit()
