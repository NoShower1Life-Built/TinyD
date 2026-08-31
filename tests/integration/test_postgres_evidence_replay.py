import hashlib
import json
import os

import psycopg

DB = os.environ["DATABASE_URL"]
TENANT = os.environ.get("TEST_TENANT_ID", "tenant-evidence")
EXECUTION_ID = f"exec-{TENANT}"


def digest(body):
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def record_digest(tenant, sequence, event_digest, previous_digest):
    return digest({
        "tenant_id": tenant,
        "sequence": sequence,
        "event_digest": event_digest,
        "previous_record_digest": previous_digest,
    })


with psycopg.connect(DB) as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT set_config('tinyd.tenant_id', %s, false)", (TENANT,))

        event1 = "1" * 64
        record1 = record_digest(TENANT, 1, event1, None)
        cur.execute(
            "INSERT INTO evidence_ledger "
            "(tenant_id,sequence,evidence_id,event_id,event_type,execution_id,actor,capability,operation," 
            "idempotency_key,event_digest,previous_record_digest,record_digest,created_at) "
            "VALUES (%s,1,%s,%s,%s,%s,%s,%s,%s,%s,%s,NULL,%s,now())",
            (TENANT, "ev-1", "event-1", "execution.completed", EXECUTION_ID, "ci", "execute", "run", "idem-1", event1, record1),
        )

        event2 = "2" * 64
        record2 = record_digest(TENANT, 2, event2, record1)
        cur.execute(
            "INSERT INTO evidence_ledger "
            "(tenant_id,sequence,evidence_id,event_id,event_type,execution_id,actor,capability,operation," 
            "idempotency_key,event_digest,previous_record_digest,record_digest,created_at) "
            "VALUES (%s,2,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())",
            (TENANT, "ev-2", "event-2", "execution.completed", EXECUTION_ID, "ci", "execute", "run", "idem-2", event2, record1, record2),
        )

        cur.execute(
            "INSERT INTO verification_evidence "
            "(verification_id,tenant_id,subject_digest,evidence_digest,verifier_id,verifier_version,result,reason,verification_digest) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            ("verify-1", TENANT, event2, record2, "tinyd-replay-verifier", "1.0.0", "VERIFIED", "chain verified", "3" * 64),
        )

        cur.execute(
            "SELECT sequence,event_digest,record_digest,previous_record_digest "
            "FROM evidence_ledger WHERE tenant_id=%s AND execution_id=%s ORDER BY sequence",
            (TENANT, EXECUTION_ID),
        )
        rows = cur.fetchall()
        assert len(rows) == 2

        previous = None
        for sequence, event_digest, stored_record, stored_previous in rows:
            assert stored_previous == previous
            assert stored_record == record_digest(TENANT, sequence, event_digest, stored_previous)
            previous = stored_record

        cur.execute(
            "SELECT result,evidence_digest FROM verification_evidence "
            "WHERE verification_id='verify-1' AND tenant_id=%s",
            (TENANT,),
        )
        assert cur.fetchone() == ("VERIFIED", record2)

    conn.rollback()
