from contextlib import contextmanager

from psycopg_pool import ConnectionPool

from .config import get_settings


pool = ConnectionPool(
    conninfo=get_settings().database_url,
    min_size=1,
    max_size=10,
    open=False,
)


def open_pool() -> None:
    pool.open(wait=True)


def close_pool() -> None:
    pool.close()


@contextmanager
def get_conn():
    with pool.connection() as conn:
        yield conn
