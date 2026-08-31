"""Read-only adapter from TinyD authoritative projections to Scoreboard.

The adapter intentionally has no persistence and cannot create assurance truth.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Mapping

from .projection import AssuranceProjection, AssuranceRequirement, project


class ProjectionSourceError(RuntimeError):
    pass


class AssuranceProjectionAdapter:
    def __init__(self, source: Callable[[str, str], Mapping[str, Any]]):
        self._source = source

    def project(self, requirement: AssuranceRequirement, *, now: datetime | None = None) -> AssuranceProjection:
        data = self._source(requirement.tenant_id, requirement.requirement_id)
        if data.get("tenant_id") != requirement.tenant_id:
            raise ProjectionSourceError("authoritative projection tenant mismatch")

        return project(
            requirement,
            implementation=data.get("implementation"),
            test=data.get("test"),
            execution=data.get("execution"),
            evidence=list(data.get("evidence", [])),
            provenance=list(data.get("provenance", [])),
            verification=list(data.get("verification", [])),
            replay=data.get("replay"),
            trust_root=data.get("trust_root"),
            now=now,
        )
