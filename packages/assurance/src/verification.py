from __future__ import annotations
import hashlib, json
from typing import Sequence
from contracts import VerificationResult
from events import EventEnvelope

class IndependentEvidenceVerifier:
    verifier_id = "tinyd-evidence-verifier"
    verifier_version = "1.0.0"
    def verify(self, event: EventEnvelope) -> VerificationResult:
        ok = event.verify_integrity()
        reason = "integrity verified" if ok else "integrity mismatch"
        body = {"subject_digest": event.integrity_digest, "result": "VERIFIED" if ok else "FAILED", "verifier_id": self.verifier_id, "verifier_version": self.verifier_version, "reason": reason}
        verification_digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return VerificationResult(hashlib.sha256((event.event_id + self.verifier_version).encode()).hexdigest(), event.integrity_digest, body["result"], self.verifier_id, self.verifier_version, verification_digest, reason)

class DeterministicReplayVerifier:
    verifier_id = "tinyd-replay-verifier"
    verifier_version = "1.0.0"
    def replay(self, execution_id: str, events: Sequence[EventEnvelope]) -> VerificationResult:
        selected = [e for e in events if e.execution_id == execution_id]
        if not selected:
            raise ValueError("execution has no events")
        ids = [e.event_id for e in selected]
        valid = len(ids) == len(set(ids)) and all(e.verify_integrity() for e in selected)
        previous = None
        for index, event in enumerate(selected):
            if index == 0:
                if event.parent_event_id is not None:
                    valid = False
                    break
            elif event.parent_event_id != previous:
                valid = False
                break
            previous = event.event_id
        material = [e.integrity_digest for e in selected]
        replay_digest = hashlib.sha256(json.dumps(material, separators=(",", ":")).encode()).hexdigest()
        result = "VERIFIED" if valid else "FAILED"
        verification_digest = hashlib.sha256(f"{execution_id}:{replay_digest}:{result}".encode()).hexdigest()
        return VerificationResult(hashlib.sha256((execution_id + self.verifier_version).encode()).hexdigest(), replay_digest, result, self.verifier_id, self.verifier_version, verification_digest, "deterministic replay comparison")
