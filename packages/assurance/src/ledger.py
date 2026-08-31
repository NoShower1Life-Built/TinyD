from __future__ import annotations

from dataclasses import dataclass
from typing import Dict
import hashlib
import json

from contracts import EvidenceReceipt
from events import EventEnvelope, SENSITIVE_KEYS


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    tenant_id: str
    sequence: int
    event_digest: str
    previous_digest: str | None
    record_digest: str


def _contains_sensitive(value: object) -> bool:
    if isinstance(value, dict):
        return any(str(k).lower() in SENSITIVE_KEYS or _contains_sensitive(v) for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return any(_contains_sensitive(v) for v in value)
    return False


class InMemoryEvidenceLedger:
    """Reference contract implementation; PostgreSQL is the production ledger."""
    def __init__(self) -> None:
        self._records: Dict[str, list[EvidenceRecord]] = {}
        self._idempotency: Dict[tuple[str, str], EvidenceReceipt] = {}
        self._idempotency_digest: Dict[tuple[str, str], str] = {}

    def append(self, event: EventEnvelope) -> EvidenceReceipt:
        if not event.tenant_id or not event.event_id:
            raise ValueError("tenant_id and event_id are required")
        if _contains_sensitive(event.payload):
            raise ValueError("secret-bearing payload rejected at evidence boundary")
        if not event.verify_integrity():
            raise ValueError("event integrity verification failed")
        key = (event.tenant_id, event.idempotency_key or event.event_id)
        event_digest = event.integrity_digest
        existing = self._idempotency.get(key)
        if existing:
            if self._idempotency_digest[key] != event_digest:
                raise ValueError("idempotency key reused for different event")
            return existing
        chain = self._records.setdefault(event.tenant_id, [])
        sequence = len(chain) + 1
        previous = chain[-1].record_digest if chain else None
        body = {"tenant_id": event.tenant_id, "sequence": sequence,
                "event_digest": event_digest, "previous_digest": previous}
        record_digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        evidence_id = hashlib.sha256(f"{event.tenant_id}:{event.event_id}".encode()).hexdigest()
        record = EvidenceRecord(evidence_id, event.tenant_id, sequence, event_digest, previous, record_digest)
        chain.append(record)
        receipt = EvidenceReceipt(evidence_id, record_digest, sequence)
        self._idempotency[key] = receipt
        self._idempotency_digest[key] = event_digest
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
