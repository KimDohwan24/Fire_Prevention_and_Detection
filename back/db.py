"""PostgreSQL 커넥션 풀 + 쿼리 헬퍼.

사용 예:
    rows = query("SELECT * FROM fireguard.users WHERE user_no = %s", (1,))
    row  = query_one("SELECT ...", (...))
    new_no = execute_returning("INSERT ... RETURNING user_no", (...))
"""
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
from psycopg2.pool import SimpleConnectionPool

import config

_pool: SimpleConnectionPool | None = None


def _get_pool() -> SimpleConnectionPool:
    """첫 쿼리 때 풀을 만든다 (DB가 안 떠 있어도 서버 자체는 시작되게)."""
    global _pool
    if _pool is None:
        _pool = SimpleConnectionPool(
            minconn=1,
            maxconn=10,
            host=config.DB_HOST,
            port=config.DB_PORT,
            dbname=config.DB_NAME,
            user=config.DB_USER,
            password=config.DB_PASSWORD,
            options="-c search_path=fireguard,public",
        )
    return _pool


@contextmanager
def get_cursor(commit: bool = False):
    """dict 형태로 행을 돌려주는 커서. commit=True 면 블록 종료 시 커밋."""
    pool = _get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            yield cur
        if commit:
            conn.commit()
        else:
            conn.rollback()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def query(sql: str, params: tuple = ()) -> list[dict]:
    """SELECT 여러 행."""
    with get_cursor() as cur:
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


def query_one(sql: str, params: tuple = ()) -> dict | None:
    """SELECT 한 행 (없으면 None)."""
    with get_cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
        return dict(row) if row else None


def execute(sql: str, params: tuple = ()) -> int:
    """INSERT/UPDATE. 영향받은 행 수를 돌려준다."""
    with get_cursor(commit=True) as cur:
        cur.execute(sql, params)
        return cur.rowcount


def execute_returning(sql: str, params: tuple = ()) -> dict:
    """INSERT ... RETURNING 용. 반환된 행을 dict 로 돌려준다."""
    with get_cursor(commit=True) as cur:
        cur.execute(sql, params)
        return dict(cur.fetchone())
