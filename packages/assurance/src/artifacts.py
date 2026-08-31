from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Iterable


@dataclass(frozen=True)
class ArtifactRecord:
    artifact_digest: str
    media_type: str
    sbom_digest: str | None = None


@dataclass(frozen=True)
class LicenseEvidence:
    artifact_digest: str
    component_id: str
    license_expression: str
    evidence_digest: str


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sbom_digest(sbom: dict) -> str:
    return sha256_bytes(json.dumps(sbom, sort_keys=True, separators=(",", ":")).encode())


def license_evidence(artifact_digest: str, component_id: str, license_expression: str) -> LicenseEvidence:
    material = {"artifact_digest": artifact_digest, "component_id": component_id,
                "license_expression": license_expression}
    digest = sha256_bytes(json.dumps(material, sort_keys=True, separators=(",", ":")).encode())
    return LicenseEvidence(artifact_digest, component_id, license_expression, digest)
