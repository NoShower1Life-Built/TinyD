import hashlib
import json
import os
import psycopg

DB = os.environ["DATABASE_URL"]

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

with psycopg.connect(DB) as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT set_config('tinyd.tenant_id','tenant-a',false)")
        cur.execute("SELECT current_setting('tinyd.tenant_id')")
        assert cur.fetchone()[0] == "tenant-a"

        event_digest = digest({"event_id":"boundary-event-1","tenant":"tenant-a","execution":"exec-boundary"})
        record_digest = digest({"tenant_id":"tenant-a","sequence":1,"event_digest":event_digest,"previous_digest":None})
        cur.execute("INSERT INTO evidence_ledger (tenant_id,sequence,evidence_id,event_id,event_type,execution_id,actor,capability,operation,idempotency_key,event_digest,record_digest,created_at) VALUES (%s,1,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())", ("tenant-a","boundary-ev-1","boundary-event-1","execution.completed","exec-boundary","ci","execute","run","boundary-idem",event_digest,record_digest))
        cur.execute("SELECT record_digest, previous_record_digest FROM evidence_ledger WHERE evidence_id='boundary-ev-1'")
        assert cur.fetchone() == (record_digest, None)

        cur.execute("SET LOCAL tinyd.tenant_id = 'tenant-b'")
        cur.execute("SELECT count(*) FROM evidence_ledger WHERE evidence_id='boundary-ev-1'")
        assert cur.fetchone()[0] == 0
