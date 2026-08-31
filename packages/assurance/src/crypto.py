from __future__ import annotations

from dataclasses import dataclass
import base64
import hashlib

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from contracts import Attestation


@dataclass(frozen=True)
class TrustKey:
    signer_id: str
    key_version: str
    algorithm: str
    public_key_b64: str
    revoked: bool = False

    def public_key(self) -> Ed25519PublicKey:
        if self.algorithm != "Ed25519": raise ValueError("unsupported signing algorithm")
        return Ed25519PublicKey.from_public_bytes(base64.b64decode(self.public_key_b64))


class TrustRoot:
    def __init__(self, keys: tuple[TrustKey, ...]): self._keys = {(k.signer_id, k.key_version): k for k in keys}
    def resolve(self, signer_id: str, key_version: str) -> TrustKey:
        key = self._keys.get((signer_id, key_version))
        if key is None or key.revoked: raise ValueError("untrusted or revoked signing key")
        return key
    def verify(self, signer_id: str, key_version: str, message: bytes, signature_b64: str) -> bool:
        try:
            self.resolve(signer_id, key_version).public_key().verify(base64.b64decode(signature_b64), message); return True
        except (InvalidSignature, ValueError): return False


class DigestArtifactAttestor:
    def __init__(self, signer_id: str, key_version: str, private_key: Ed25519PrivateKey):
        self.signer_id, self.key_version, self.private_key = signer_id, key_version, private_key
    def attest(self, artifact_digest: str) -> Attestation:
        if len(artifact_digest) != 64 or any(c not in "0123456789abcdef" for c in artifact_digest):
            raise ValueError("artifact_digest must be a SHA-256 hex digest")
        message = f"tinyd-artifact-v1:{artifact_digest}".encode(); signature = base64.b64encode(self.private_key.sign(message)).decode()
        return Attestation(artifact_digest, hashlib.sha256(message + signature.encode()).hexdigest(), self.signer_id, self.key_version, "Ed25519", signature)
