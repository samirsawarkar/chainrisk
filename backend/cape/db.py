import os

import redis

try:
    import psycopg
except ImportError as exc:  # pragma: no cover
    raise ImportError("psycopg is required for CAPE. Install with `pip install psycopg[binary]`.") from exc


def get_pg_conn():
    return psycopg.connect(
        host=os.environ.get("CAPE_PG_HOST", "localhost"),
        port=int(os.environ.get("CAPE_PG_PORT", "5432")),
        dbname=os.environ.get("CAPE_PG_DB", "cape"),
        user=os.environ.get("CAPE_PG_USER", "postgres"),
        password=os.environ.get("CAPE_PG_PASSWORD", ""),
        autocommit=False,
    )


def get_redis_client():
    return redis.Redis(
        host=os.environ.get("CAPE_REDIS_HOST", "localhost"),
        port=int(os.environ.get("CAPE_REDIS_PORT", "6379")),
        db=int(os.environ.get("CAPE_REDIS_DB", "0")),
        decode_responses=True,
    )
