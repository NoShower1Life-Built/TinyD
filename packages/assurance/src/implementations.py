from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from events import EventEnvelope


class CanonicalIntegrityVerifier:
    def verify(self, event: EventEnvelope) -> bool:
        return event.verify_integrity()


@dataclass(frozen=True)
class OwnershipRecord:
    tenant_id: str
    subject_id: str
    relationship: str
    target_id: str
    evidence_digest: str


class EvidenceBackedOwnershipRegistry:
    ALLOWED = frozenset({"AUTHORED_BY", "CONTRIBUTED_BY", "LICENSED_UNDER", "ASSIGNED_BY", "ACQUIRED_UNDER", "DERIVED_FROM", "ATTESTED_BY"})

    def __init__(self) -> None:
        self._records: dict[tuple[str, str, str, str], OwnershipRecord] = {}

    def record(self, tenant_id: str, subject_id: str, relationship: str, target_id: str) -> OwnershipRecord:
        if not tenant_id or relationship not in self.ALLOWED:
            raise ValueError("tenant_id and a supported ownership relationship are required")
        key = (tenant_id, subject_id, relationship, target_id)
        material = {"tenant_id": tenant_id, "subject_id": subject_id, "relationship": relationship, "target_id": target_id}
        evidence_digest = hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        record = OwnershipRecord(*key, evidence_digest)
        existing = self._records.get(key)
        if existing and existing.evidence_digest != evidence_digest:
            raise ValueError("ownership record conflict")
        self._records.setdefault(key, record)
        return self._records[key]

    def get(self, tenant_id: str, subject_id: str, relationship: str, target_id: str) -> OwnershipRecord:
        return self._records[(tenant_id, subject_id, relationship, target_id)]
