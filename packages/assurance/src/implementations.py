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
    subject_id: str
    relationship: str
    target_id: str
    evidence_digest: str


class EvidenceBackedOwnershipRegistry:
    ALLOWED = frozenset({"AUTHORED_BY", "CONTRIBUTED_BY", "LICENSED_UNDER", "ASSIGNED_BY", "ACQUIRED_UNDER", "DERIVED_FROM", "ATTESTED_BY"})

    def __init__(self) -> None:
        self._records: dict[tuple[str, str, str], OwnershipRecord] = {}

    def record(self, subject_id: str, relationship: str, target_id: str) -> OwnershipRecord:
        if relationship not in self.ALLOWED:
            raise ValueError(f"unsupported ownership relationship: {relationship}")
        material = {"subject_id": subject_id, "relationship": relationship, "target_id": target_id}
        evidence_digest = hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        record = OwnershipRecord(subject_id, relationship, target_id, evidence_digest)
        self._records[(subject_id, relationship, target_id)] = record
        return record

    def get(self, subject_id: str, relationship: str, target_id: str) -> OwnershipRecord:
        return self._records[(subject_id, relationship, target_id)]
