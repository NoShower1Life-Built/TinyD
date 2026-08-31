import hashlib
import json
import os

import psycopg

DB = os.environ["DATABASE_URL"]
TENANT = os.environ.get("TEST_TENANT_ID", "tenant-evidence")


def digest(body):
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


with psycopg.connect(DB) as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT set_config('tinyd.tenant_id', %s, false)", (TENANT,))
        event1 = "1" * 64
        record1 = digest({"tenant_id": TENANT, "sequence": 1, "event_digest": event1, "previous_digest": None})
        cur.execute(
            "INSERT INTO evidence_ledger (tenant_id,sequence,evidence_id,event_id,event_type,execution_id,actor,capability,operation,idempotency_key,event_digest,record_digest,created_at) VALUES (%s,1,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())",
            (TENANT, "ev-1", "event-1", "execution.completed", "exec-1", "ci", "execute", "run", "idem-1", event1, record1),
        )
        event2 = "2" * 64
        record2 = digest({"tenant_id": TENANT, "sequence": 2, "event_digest": event2, "previous_digest": record1})
        cur.execute(
            "INSERT INTO evidence_ledger (tenant_id,sequence,evidence_id,event_id,event_type,execution_id,actor,capability,operation,idempotency_key,event_digest,record_digest,created_at) VALUES (%s,2,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())",
            (TENANT, "ev-2", "event-2", "execution.completed", "exec-1", "ci", "execute", "run", "idem-2", event2, record2),
        )
        cur.execute(
            "INSERT INTO verification_evidence (verification_id,tenant_id,subject_digest,evidence_digest,verifier_id,verifier_version,result,reason,verification_digest) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            ("verify-1", TENANT, event2, record2, "tinyd-replay-verifier", "1.0.0", "VERIFIED", "chain verified", "3" * 64),
        )
        cur.execute("SELECT sequence,record_digest,previous_record_digest FROM evidence_ledger WHERE execution_id='exec-1' ORDER BY sequence")
        rows = cur.fetchall()
        assert rows == [(1, record1, None), (2, record2, record1)]
        cur.execute("SELECT result,evidence_digest FROM verification_evidence WHERE verification_id='verify-1'")
        assert cur.fetchone() == ("VERIFIED", record2)
    conn.commit()
