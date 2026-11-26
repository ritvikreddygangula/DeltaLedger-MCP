import os

import pytest

from src.storage.db import get_connection, init_db


@pytest.fixture
def pg_conn():
    """A real Postgres connection with a freshly created schema.

    Points at TEST_DATABASE_URL, never DATABASE_URL, so a test run can't
    drop the tables in the real (Supabase) database. Skips locally when
    it's unset. CI sets REQUIRE_PG=1 so a missing database fails loudly
    instead of quietly skipping every integration test.
    """
    dsn = os.environ.get("TEST_DATABASE_URL")
    if not dsn:
        if os.environ.get("REQUIRE_PG") == "1":
            pytest.fail("REQUIRE_PG=1 but TEST_DATABASE_URL is not set")
        pytest.skip("TEST_DATABASE_URL not set")
    conn = get_connection(dsn)
    conn.execute("DROP TABLE IF EXISTS findings, sections, llm_cache, filings CASCADE")
    conn.commit()
    init_db(conn)
    yield conn
    conn.close()
