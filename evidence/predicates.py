from __future__ import annotations

from typing import Any


def evaluate(predicate: dict[str, Any], evidence_payload: dict[str, Any]) -> bool:
    """Evaluate the intentionally small canonical predicate vocabulary."""
    op = predicate.get("op")
    field = predicate.get("field")
    actual = evidence_payload.get(field)
    if op == "equals": return actual == predicate.get("value")
    if op == "exists": return field in evidence_payload
    if op == "in": return actual in predicate.get("values", [])
    raise ValueError(f"unsupported predicate operator: {op}")
