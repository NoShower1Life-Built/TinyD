from __future__ import annotations

from dataclasses import dataclass
import hashlib


@dataclass(frozen=True)
class TrustKey:
    signer_id: str
    key_version: str
    algorithm: str
    public_material: str
    revoked: bool = False


class TrustRoot:
    def __init__(self, keys: tuple[TrustKey, ...]) -> None:
        self._keys = {(k.signer_id, k.key_version): k for k in keys}

    def resolve(self, signer_id: str, key_version: str) -> TrustKey:
        key = self._keys.get((signer_id, key_version))
        if key is None or key.revoked:
            raise ValueError("untrusted or revoked signing key")
        return key


class DigestArtifactAttestor:
    def __init__(self, trust_root: TrustRoot) -> None:
        self._trust_root = trust_root

    def attest(self, artifact_digest: str, signer_id: str, key_version: str) -> dict[str, str]:
        if len(artifact_digest) != 64 or any(c not in "0123456789abcdef" for c in artifact_digest):
            raise ValueError("artifact_digest must be a SHA-256 hex digest")
        key = self._trust_root.resolve(signer_id, key_version)
        # Reference attestation binds the artifact to the trusted key metadata.
        material = f"{artifact_digest}:{key.signer_id}:{key.key_version}:{key.algorithm}:{key.public_material}"
        return {"artifact_digest": artifact_digest,
                "attestation_digest": hashlib.sha256(material.encode()).hexdigest(),
                "signer_id": key.signer_id, "key_version": key.key_version,
                "algorithm": key.algorithm}
