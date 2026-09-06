from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_DIR = ROOT / "packages" / "marketplace" / "registry"


def _files() -> list[Path]:
    return sorted(REGISTRY_DIR.glob("*.json")) if REGISTRY_DIR.exists() else []


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"invalid package manifest: {path.name}")
    return value


def list_packages(query: str = "", category: str = "") -> list[dict[str, Any]]:
    q = query.strip().lower()
    c = category.strip().lower()
    result = []
    for path in _files():
        package = _load(path)
        haystack = json.dumps(package, sort_keys=True).lower()
        if q and q not in haystack:
            continue
        if c and str(package.get("type", "")).lower() != c:
            continue
        result.append(package)
    return result


def get_package(package_id: str, version: str | None = None) -> dict[str, Any] | None:
    matches = [p for p in list_packages() if p.get("id") == package_id]
    if version:
        matches = [p for p in matches if p.get("version") == version]
    return matches[0] if matches else None


def manifest_digest(package: dict[str, Any]) -> str:
    canonical = json.dumps(package, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()
