from __future__ import annotations

import hashlib
import json
from pathlib import Path
from threading import Lock

from .types import EvidenceRecord


class EvidenceLedger:
    """Append-only JSONL ledger with deterministic evidence IDs."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def evidence_id(requirement_id: str, execution_id: str, source_revision: str, payload: dict) -> str:
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        raw = f"{requirement_id}:{execution_id}:{source_revision}:{canonical}".encode()
        return "ev-" + hashlib.sha256(raw).hexdigest()[:24]

    def append(self, record: EvidenceRecord) -> EvidenceRecord:
        expected = self.evidence_id(record.requirement_id, record.execution_id, record.source_revision, record.payload)
        if record.evidence_id != expected:
            raise ValueError("evidence_id does not match canonical evidence content")
        line = json.dumps(record.as_dict(), sort_keys=True, separators=(",", ":"))
        with self._lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        return record

    def records(self) -> list[EvidenceRecord]:
        if not self.path.exists():
            return []
        result=[]
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                data=json.loads(line)
                result.append(EvidenceRecord(data["evidenceId"],data["requirementId"],data["executionId"],data["sourceRevision"],data["kind"],data["payload"],data["capturedAt"]))
        return result
