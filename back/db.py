"""PostgreSQL 커넥션 풀 + 쿼리 헬퍼.

사용 예:
    rows = query("SELECT * FROM fireguard.users WHERE user_no = %s", (1,))
    row  = query_one("SELECT ...", (...))
    new_no = execute_returning("INSERT ... RETURNING user_no", (...))
"""
import threading
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool

import config

# 이 풀은 여러 스레드가 동시에 쓴다:
#   - Flask 개발 서버가 요청마다 스레드를 하나씩 띄운다 (app.run 의 threaded=True 기본값)
#   - 에스컬레이션 스케줄러가 백그라운드 스레드로 따로 돈다
# SimpleConnectionPool 은 psycopg2 문서상 단일 스레드 전용이라 getconn/putconn 에 잠금이
# 없다 — 두 스레드가 같은 커넥션을 받아 트랜잭션이 섞일 수 있다. ThreadedConnectionPool 은
# 같은 인터페이스에 잠금만 더한 것이라 호출부는 그대로 둔다.
_pool: ThreadedConnectionPool | None = None
# 풀 생성 자체도 경쟁 대상이다 — 첫 쿼리가 동시에 두 번 들어오면 풀이 두 개 만들어져
# 한쪽 커넥션이 통째로 새는 데다 maxconn 이 사실상 두 배가 된다.
_pool_lock = threading.Lock()


def _get_pool() -> ThreadedConnectionPool:
    """첫 쿼리 때 풀을 만든다 (DB가 안 떠 있어도 서버 자체는 시작되게)."""
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:  # 잠금을 기다리는 사이 다른 스레드가 만들었을 수 있다
                _pool = ThreadedConnectionPool(
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
