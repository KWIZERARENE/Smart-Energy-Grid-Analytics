"""Shared connection pool and a timed query helper.

One pool serves both dashboards, so Raw and Aggregate use the same server,
credentials and connection settings (7.4: same machine and connection).
"""
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import psycopg2
from django.conf import settings
from psycopg2.pool import ThreadedConnectionPool

CAT = timezone(timedelta(hours=2), "CAT")
_pool = None


def _get_pool():
    global _pool
    if _pool is None:
        _pool = ThreadedConnectionPool(1, 10, options="-c timezone=Africa/Kigali", **settings.PG)
    return _pool


def cat_midnight(text):
    """'YYYY-MM-DD' -> midnight CAT as an aware datetime."""
    y, m, d = (int(x) for x in text.split("-"))
    return datetime(y, m, d, tzinfo=CAT)


def _plain(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def timed_query(sql, params):
    """Run one query; return (columns, rows, query_ms).

    query_ms covers execute plus fetching every row, i.e. until the last result
    row is received. No result is cached anywhere.
    """
    pool = _get_pool()
    conn = pool.getconn()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            t0 = time.perf_counter()
            cur.execute(sql, params)
            rows = cur.fetchall()
            query_ms = (time.perf_counter() - t0) * 1000.0
            columns = [c.name for c in cur.description]
    finally:
        pool.putconn(conn)
    return columns, [[_plain(v) for v in row] for row in rows], query_ms
