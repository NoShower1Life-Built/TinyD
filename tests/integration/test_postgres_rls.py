import os

import psycopg

DB = os.environ["RLS_DATABASE_URL"]


def execute(conn, sql, params=()):
    with conn.cursor() as cur:
        cur.execute(sql, params)


def fetchone(conn, sql, params=()):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()


with psycopg.connect(DB) as conn:
    execute(conn, "SELECT set_config('tinyd.tenant_id', %s, false)", ("tenant-a",))
    execute(
        conn,
        "INSERT INTO evidence_ledger "
        "(tenant_id,sequence,evidence_id,event_id,event_type,execution_id,actor,capability,operation,idempotency_key,event_digest,record_digest,created_at) "
        "VALUES ('tenant-a',1,'ev-a','event-a','test','exec-a','ci','execute','run','idem-a',repeat('a',64),repeat('b',64),now())",
    )
    assert fetchone(conn, "SELECT count(*) FROM evidence_ledger WHERE tenant_id='tenant-a'")[0] == 1
    execute(conn, "SELECT set_config('tinyd.tenant_id', %s, false)", ("tenant-b",))
    assert fetchone(conn, "SELECT count(*) FROM evidence_ledger")[0] == 0
    conn.commit()
