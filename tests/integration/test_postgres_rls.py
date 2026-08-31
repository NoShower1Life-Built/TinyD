import os

import psycopg

DB = os.environ["RLS_DATABASE_URL"]
TENANT = os.environ.get("TEST_TENANT_ID", "tenant-rls")


def execute(conn, sql, params=()):
    with conn.cursor() as cur:
        cur.execute(sql, params)


def fetchone(conn, sql, params=()):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()


with psycopg.connect(DB) as conn:
    # Missing tenant context must not expose or permit evidence.
    assert fetchone(conn, "SELECT count(*) FROM evidence_ledger")[0] == 0
    try:
        execute(
            conn,
            "INSERT INTO evidence_ledger "
            "(tenant_id,sequence,evidence_id,event_id,event_type,execution_id,actor,capability,operation,idempotency_key,event_digest,record_digest,created_at) "
            "VALUES (%s,1,'ev-missing','event-missing','test','exec-missing','ci','execute','run','idem-missing',repeat('a',64),repeat('b',64),now())",
            (TENANT,),
        )
    except psycopg.errors.InsufficientPrivilege:
        conn.rollback()
    else:
        raise AssertionError("evidence insert succeeded without tenant context")

    execute(conn, "SELECT set_config('tinyd.tenant_id', %s, false)", (TENANT,))
    execute(
        conn,
        "INSERT INTO evidence_ledger "
        "(tenant_id,sequence,evidence_id,event_id,event_type,execution_id,actor,capability,operation,idempotency_key,event_digest,record_digest,created_at) "
        "VALUES (%s,1,'ev-a','event-a','test','exec-a','ci','execute','run','idem-a',repeat('a',64),repeat('b',64),now())",
        (TENANT,),
    )
    assert fetchone(conn, "SELECT count(*) FROM evidence_ledger WHERE tenant_id=%s", (TENANT,))[0] == 1
    execute(conn, "SELECT set_config('tinyd.tenant_id', %s, false)", ("tenant-other",))
    assert fetchone(conn, "SELECT count(*) FROM evidence_ledger")[0] == 0
    conn.commit()
