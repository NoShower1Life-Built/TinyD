import os
import psycopg

DB = os.environ["DATABASE_URL"]

def run(conn, sql, params=()):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()

with psycopg.connect(DB) as conn:
    run(conn, "SET ROLE tinyd")
    run(conn, "SELECT set_config('tinyd.tenant_id', %s, false)", ("tenant-a",))
    run(conn, "INSERT INTO evidence_ledger (tenant_id,sequence,evidence_id,event_id,event_type,execution_id,actor,capability,operation,idempotency_key,event_digest,record_digest,created_at) VALUES ('tenant-a',1,'ev-a','event-a','test','exec-a','ci','execute','run','idem-a',repeat('a',64),repeat('b',64),now())")
    assert run(conn, "SELECT count(*) FROM evidence_ledger WHERE tenant_id='tenant-a'")[0][0] == 1
    assert run(conn, "SELECT count(*) FROM evidence_ledger WHERE tenant_id='tenant-b'")[0][0] == 0
    run(conn, "SET LOCAL tinyd.tenant_id = 'tenant-b'")
    assert run(conn, "SELECT count(*) FROM evidence_ledger")[0][0] == 0
