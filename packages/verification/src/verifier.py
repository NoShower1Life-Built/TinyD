from __future__ import annotations

import hashlib

from events import EventEnvelope


class VerificationEngine:
    """Compatibility facade over canonical event integrity verification."""

    verifier_id = "tinyd-verification-engine"
    verifier_version = "1.1.0"

    def hash_events(self, payload: str) -> str:
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def verify_event(self, event: EventEnvelope) -> bool:
        return event.verify_integrity()
