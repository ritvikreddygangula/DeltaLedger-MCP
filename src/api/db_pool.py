import os
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    """Lazily built on first use, not at import time. Tests and module imports
    then never need a reachable database, and a missing DATABASE_URL shows up
    as a failed request or health check (logged, 503) instead of a crash at
    startup.

    max_size=5 is deliberately small. Supabase's free-tier session pooler
    caps client connections per project, and every request here is a
    millisecond-scale indexed SELECT.
    """
    global _pool
    if _pool is None:
        dsn = os.environ.get("DATABASE_URL")
        if not dsn:
            raise RuntimeError("DATABASE_URL is required. See .env.example.")
        _pool = ConnectionPool(
            dsn,
            min_size=1,
            max_size=5,
            kwargs={"row_factory": dict_row},
            open=True,
        )
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def connection() -> Iterator[psycopg.Connection]:
    with get_pool().connection() as conn:
        yield conn
