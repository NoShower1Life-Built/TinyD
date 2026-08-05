import hashlib

class VerificationEngine:
    def hash_events(self, payload: str) -> str:
        return hashlib.sha256(payload.encode()).hexdigest()
