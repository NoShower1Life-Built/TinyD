from __future__ import annotations

import hashlib
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SECRET_KEY = re.compile(r"(authorization|token|secret|password|api[_-]?key|cookie|credential)", re.I)
BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*")
TOKEN_LIKE = re.compile(r"\b(sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9]{20,})\b")


def redact(value: Any, key: str = "") -> Any:
    """Redact likely credentials recursively before writing an export."""
    if SECRET_KEY.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(k): redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return TOKEN_LIKE.sub("[REDACTED_TOKEN]", BEARER.sub("Bearer [REDACTED]", value))
    return value


def read_jsonl(paths: Iterable[Path]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in paths:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"{path}:{line_number}: invalid JSONL: {exc}") from exc
                if not isinstance(record, dict):
                    raise ValueError(f"{path}:{line_number}: each JSONL record must be an object")
                records.append(record)
    return records


def validate_record(record: dict[str, Any]) -> None:
    required = ("trace_id", "event_type", "timestamp", "service")
    missing = [name for name in required if not record.get(name)]
    if missing:
        raise ValueError(f"record missing required fields: {', '.join(missing)}")
    try:
        datetime.fromisoformat(str(record["timestamp"]).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"invalid RFC3339 timestamp: {record['timestamp']}") from exc


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(redact(data), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def export_bundle(records: list[dict[str, Any]], trace_id: str, out_dir: Path, zip_output: bool = False) -> dict[str, Any]:
    selected = [r for r in records if r.get("trace_id") == trace_id]
    for record in selected:
        validate_record(record)
    selected.sort(key=lambda r: (str(r["timestamp"]), str(r.get("event_id", ""))))
    safe = [redact(r) for r in selected]

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "trace_id.txt").write_text(trace_id + "\n", encoding="utf-8")
    _write_json(out_dir / "kafka_chain.json", {
        "trace_id": trace_id,
        "events": [r for r in safe if r.get("topic") or str(r.get("event_type", "")).upper() in {
            "REQUEST", "SCHEDULED", "ASSIGNED", "EXECUTING", "COMPLETED", "RESULT", "FAILED"
        }],
        "note": "Only records supplied by the runtime are included. No missing events are synthesized."
    })
    _write_json(out_dir / "redis_events.json", {
        "trace_id": trace_id,
        "events": [r for r in safe if str(r.get("system", "")).lower() == "redis"
                   or str(r.get("event_type", "")).upper().startswith(("LEASE_", "IDEMPOTENCY_"))]
    })

    prompt_lines = []
    for r in safe:
        if any(k in r for k in ("prompt", "response", "model_response", "tools_called")):
            prompt_lines.append(json.dumps(r, sort_keys=True))
    (out_dir / "prompt_response.log").write_text("\n".join(prompt_lines) + ("\n" if prompt_lines else ""), encoding="utf-8")

    worker_lines = []
    for r in safe:
        et = str(r.get("event_type", "")).upper()
        if r.get("worker_id") or r.get("tool_name") or et in {"EXECUTING", "TOOL_CALL", "TOOL_RESULT", "COMPLETED", "FAILED"}:
            worker_lines.append(json.dumps(r, sort_keys=True))
    (out_dir / "worker_execution.log").write_text("\n".join(worker_lines) + ("\n" if worker_lines else ""), encoding="utf-8")

    event_types = [str(r.get("event_type", "")).upper() for r in selected]
    required_types = {"REQUEST", "SCHEDULED", "EXECUTING"}
    missing_types = sorted(required_types - set(event_types))
    has_terminal = any(t in {"RESULT", "COMPLETED", "FAILED"} for t in event_types)
    completeness = {
        "record_count": len(selected),
        "missing_trace": len(selected) == 0,
        "missing_event_types": missing_types,
        "missing_terminal_event": not has_terminal,
        "assessment": "NO_DATA" if not selected else ("INCOMPLETE" if missing_types or not has_terminal else "TRACE_PRESENT_REQUIRES_REVIEW")
    }

    manifest = {
        "format": "tinyd-evidence-v1",
        "trace_id": trace_id,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "completeness": completeness,
        "artifacts": {}
    }
    for path in sorted(out_dir.iterdir()):
        if path.is_file() and path.name != "manifest.json":
            manifest["artifacts"][path.name] = {
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "bytes": path.stat().st_size
            }
    _write_json(out_dir / "manifest.json", manifest)

    if zip_output:
        archive = out_dir.with_suffix(".zip")
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(out_dir.iterdir()):
                if path.is_file():
                    zf.write(path, arcname=path.name)
    return manifest
