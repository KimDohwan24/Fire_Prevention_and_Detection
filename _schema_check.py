"""운영 DB(fireguard) vs db/schema.sql 정밀 대조.
임시 DB(fireguard_schema_check)에 schema.sql을 새로 깔아 정보 스키마를 비교한다.
운영 DB는 읽기만 한다."""
import os
import psycopg2


def load_env(path):
    env = {}
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()
    return env


ENV = load_env(os.path.join(os.getcwd(), os.pardir, ".env"))
CONN = dict(host=ENV.get("DB_HOST", "localhost"), port=ENV.get("DB_PORT", "5432"),
            user=ENV.get("DB_USER", "postgres"), password=ENV.get("DB_PASSWORD", ""))
SCRATCH = "fireguard_schema_check"

SQL_COLS = """SELECT table_name, column_name, data_type, is_nullable,
                     COALESCE(column_default,'')
              FROM information_schema.columns
              WHERE table_schema='fireguard'
              ORDER BY table_name, ordinal_position"""
SQL_IDX = """SELECT tablename || '.' || indexname, indexdef
             FROM pg_indexes WHERE schemaname='fireguard' ORDER BY 1"""
SQL_CONS = """SELECT conrelid::regclass::text, conname, pg_get_constraintdef(oid)
              FROM pg_constraint
              WHERE connamespace='fireguard'::regnamespace AND contype IN ('p','u','f','c')
              ORDER BY 1, 2"""


def conn(dbname):
    return psycopg2.connect(dbname=dbname, **CONN)


def snapshot(c):
    cur = c.cursor()
    cur.execute(SQL_COLS)
    cols = {(t, col): (dt, nl == "YES", dflt) for t, col, dt, nl, dflt in cur.fetchall()}
    cur.execute(SQL_IDX)
    idx = dict(cur.fetchall())
    cur.execute(SQL_CONS)
    cons = {(r.split(".")[-1], n): d for r, n, d in cur.fetchall()}
    tables = sorted({k[0] for k in cols})
    return tables, cols, idx, cons


# --- 임시 DB 준비: schema.sql을 그대로 적용 ---
admin = conn("postgres")
admin.autocommit = True
cur = admin.cursor()
cur.execute(f"DROP DATABASE IF EXISTS {SCRATCH} WITH (FORCE)")
cur.execute(f"CREATE DATABASE {SCRATCH}")
admin.close()

sc = conn(SCRATCH)
sc.autocommit = True
sc.cursor().execute(open(os.path.join(os.getcwd(), os.pardir, "db", "schema.sql"), encoding="utf-8").read())
sc.close()

tables_d, cols_d, idx_d, cons_d = snapshot(conn(ENV.get("DB_NAME", "fireguard")))
tables_s, cols_s, idx_s, cons_s = snapshot(conn(SCRATCH))

issues = []
for t in sorted(set(tables_d) | set(tables_s)):
    if t not in tables_s:
        issues.append(f"[테이블] {t}: 운영에만 있음 (schema.sql 에 없다)")
    elif t not in tables_d:
        issues.append(f"[테이블] {t}: 운영에 없음 (schema.sql 에만 있다)")

for key in sorted(set(cols_d) | set(cols_s)):
    t = key[0]
    if t not in tables_d or t not in tables_s:
        continue
    a, b = cols_d.get(key), cols_s.get(key)
    if a is None:
        issues.append(f"[컬럼+] {t}.{key[1]}: 운영에만 있음")
    elif b is None:
        issues.append(f"[컬럼-] {t}.{key[1]}: 운영에 없음 (schema.sql 에는 있다)")
    elif a != b:
        issues.append(f"[컬럼~] {t}.{key[1]}\n      운영={a}\n      기준={b}")

for k in sorted(set(idx_d) | set(idx_s)):
    if k not in idx_s:
        issues.append(f"[인덱스+] {k}: 운영에만 있음\n      {idx_d[k]}")
    elif k not in idx_d:
        issues.append(f"[인덱스-] {k}: 운영에 없음\n      {idx_s[k]}")
    elif idx_d[k] != idx_s[k]:
        issues.append(f"[인덱스~] {k}\n      운영={idx_d[k]}\n      기준={idx_s[k]}")

for k in sorted(set(cons_d) | set(cons_s)):
    if k not in cons_s:
        issues.append(f"[제약+] {k[0]}.{k[1]}: 운영에만 있음\n      {cons_d[k]}")
    elif k not in cons_d:
        issues.append(f"[제약-] {k[0]}.{k[1]}: 운영에 없음\n      {cons_s[k]}")
    elif cons_d[k] != cons_s[k]:
        issues.append(f"[제약~] {k[0]}.{k[1]}\n      운영={cons_d[k]}\n      기준={cons_s[k]}")

print("=" * 62)
if issues:
    print(f"차이 {len(issues)}건")
    print("=" * 62)
    print("\n".join(issues))
else:
    print(f"완전 일치 — 테이블 {len(tables_d)}개 · 컬럼 {len(cols_d)}개 · "
          f"인덱스 {len(idx_d)}개 · 제약 {len(cons_d)}개 모두 schema.sql 과 동일")

# --- 뒷정리 ---
admin = conn("postgres")
admin.autocommit = True
admin.cursor().execute(f"DROP DATABASE IF EXISTS {SCRATCH} WITH (FORCE)")
admin.close()
