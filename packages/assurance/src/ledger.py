from __future__ import annotations

from dataclasses import dataclass
from typing import Dict
import hashlib
import json

from contracts import EvidenceReceipt
from events import EventEnvelope


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    tenant_id: str
    sequence: int
    event_digest: str
    previous_digest: str | None
    record_digest: str


class InMemoryEvidenceLedger:
    """Reference implementation of the ledger contract; persistence belongs in PostgreSQL."""
    def __init__(self) -> None:
        self._records: Dict[str, list[EvidenceRecord]] = {}
        self._idempotency: Dict[tuple[str, str], EvidenceReceipt] = {}

    def append(self, event: EventEnvelope) -> EvidenceReceipt:
        if not event.tenant_id or not event.event_id:
            raise ValueError("tenant_id and event_id are required")
        if not event.verify_integrity():
            raise ValueError("event integrity verification failed")
        key = (event.tenant_id, event.idempotency_key or event.event_id)
        existing = self._idempotency.get(key)
        if existing:
            return existing
        chain = self._records.setdefault(event.tenant_id, [])
        sequence = len(chain) + 1
        previous = chain[-1].record_digest if chain else None
        body = {"tenant_id": event.tenant_id, "sequence": sequence,
                "event_digest": event.integrity_digest, "previous_digest": previous}
        record_digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        evidence_id = hashlib.sha256(f"{event.tenant_id}:{event.event_id}".encode()).hexdigest()
        record = EvidenceRecord(evidence_id, event.tenant_id, sequence, event.integrity_digest, previous, record_digest)
        chain.append(record)
        receipt = EvidenceReceipt(evidence_id, record_digest, sequence)
        self._idempotency[key] = receipt
        return receipt

    def verify_chain(self, tenant_id: str) -> bool:
        chain = self._records.get(tenant_id, [])
        previous = None
        for expected_sequence, record in enumerate(chain, 1):
            if record.sequence != expected_sequence or record.previous_digest != previous:
                return False
            body = {"tenant_id": record.tenant_id, "sequence": record.sequence,
                    "event_digest": record.event_digest, "previous_digest": record.previous_digest}
            expected = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            if expected != record.record_digest:
                return False
            previous = record.record_digest
        return True
