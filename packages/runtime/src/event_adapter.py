from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from packages.contracts.src.envelope import EventEnvelope
from packages.runtime.src.event_mapping import MAPPING_VERSION, EventMappingError, get_mapping


TENANT_NAMESPACE = uuid5(NAMESPACE_URL, "https://tinyd.dev/namespaces/tenant/v1")
EVENT_NAMESPACE = uuid5(NAMESPACE_URL, "https://tinyd.dev/namespaces/event/v1")
AGGREGATE_NAMESPACE = uuid5(NAMESPACE_URL, "https://tinyd.dev/namespaces/aggregate/v1")


class LegacyEventAdapterError(ValueError):
    """Raised when a legacy event cannot be converted safely."""


class LegacyEventAdapter:
    """Pure deterministic adapter from legacy event dictionaries to EventEnvelope."""

    producer = "tinyd.legacy-event-adapter"

    @staticmethod
    def _required_text(event: dict[str, Any], field: str) -> str:
        value = event.get(field)
        if value is None or str(value).strip() == "":
            raise LegacyEventAdapterError(f"legacy event requires {field!r}")
        return str(value).strip()

    @staticmethod
    def _uuid(value: Any, field: str) -> UUID:
        if isinstance(value, UUID):
            return value
        try:
            return UUID(str(value).strip())
        except (AttributeError, ValueError, TypeError) as exc:
            raise LegacyEventAdapterError(f"{field} must be a valid UUID") from exc

    @staticmethod
    def _deterministic_uuid(namespace: UUID, value: str, field: str) -> UUID:
        if not value.strip():
            raise LegacyEventAdapterError(f"{field} cannot be empty")
        return uuid5(namespace, value.strip())

    @classmethod
    def _tenant_id(cls, value: Any) -> tuple[UUID, str]:
        raw = cls._required_text({"tenant_id": value}, "tenant_id")
        try:
            return UUID(raw), raw
        except ValueError:
            return cls._deterministic_uuid(TENANT_NAMESPACE, raw, "tenant_id"), raw

    @classmethod
    def _event_id(cls, value: Any) -> tuple[UUID, str]:
        raw = cls._required_text({"id": value}, "id")
        try:
            return UUID(raw), raw
        except ValueError:
            return cls._deterministic_uuid(EVENT_NAMESPACE, raw, "id"), raw

    @staticmethod
    def _timestamp(value: Any) -> datetime:
        if value is None:
            return datetime.now(timezone.utc)
        if isinstance(value, datetime):
            result = value
        else:
            try:
                result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            except ValueError as exc:
                raise LegacyEventAdapterError("occurred_at must be ISO-8601") from exc
        if result.tzinfo is None:
            raise LegacyEventAdapterError("occurred_at must include timezone information")
        return result.astimezone(timezone.utc)

    @staticmethod
    def _payload(event: dict[str, Any]) -> dict[str, Any]:
        return dict(event.get("payload", event)) if isinstance(event.get("payload", event), dict) else {
            "value": event.get("payload")
        }

    @classmethod
    def adapt(
        cls,
        event: dict[str, Any],
        *,
        authenticated_tenant_id: UUID | str | None = None,
    ) -> EventEnvelope:
        if not isinstance(event, dict):
            raise LegacyEventAdapterError("legacy event must be an object")

        event_type = cls._required_text(event, "type")
        mapping = get_mapping(event_type)
        tenant_uuid, legacy_tenant_id = cls._tenant_id(event.get("tenant_id"))

        if authenticated_tenant_id is not None:
            auth_uuid = cls._uuid(authenticated_tenant_id, "authenticated_tenant_id")
            if auth_uuid != tenant_uuid:
                raise LegacyEventAdapterError("legacy tenant_id does not match authenticated tenant")
            tenant_uuid = auth_uuid

        event_uuid, legacy_event_id = cls._event_id(event.get("id"))
        aggregate_identity = mapping.identity(event)
        aggregate_uuid = cls._deterministic_uuid(
            AGGREGATE_NAMESPACE,
            f"v{MAPPING_VERSION}\x00{tenant_uuid}\x00{mapping.aggregate_type}\x00{aggregate_identity}",
            "aggregate identity",
        )

        agent_value = event.get("agent_id")
        if agent_value is None and isinstance(event.get("payload"), dict):
            agent_value = event["payload"].get("agent_id")
        if agent_value is None:
            raise LegacyEventAdapterError("legacy event requires agent_id")
        agent_uuid = cls._uuid(agent_value, "agent_id")

        def optional_uuid(field: str) -> UUID | None:
            value = event.get(field)
            if value is None and isinstance(event.get("payload"), dict):
                value = event["payload"].get(field)
            return None if value is None else cls._uuid(value, field)

        correlation_uuid = optional_uuid("correlation_id") or event_uuid
        payload = cls._payload(event)
        metadata = dict(event.get("metadata", {})) if isinstance(event.get("metadata"), dict) else {}
        metadata.update(
            {
                "source": "legacy_event_adapter",
                "adapter_version": MAPPING_VERSION,
                "legacy_event_id": legacy_event_id,
                "legacy_tenant_id": legacy_tenant_id,
                "aggregate_mapping": mapping.identity_label,
            }
        )

        return EventEnvelope(
            event_id=event_uuid,
            event_type=mapping.event_type.value,
            event_version=mapping.event_type and 1,
            occurred_at=cls._timestamp(event.get("occurred_at", event.get("timestamp"))),
            tenant_id=tenant_uuid,
            agent_id=agent_uuid,
            conversation_id=optional_uuid("conversation_id"),
            run_id=optional_uuid("run_id"),
            task_id=optional_uuid("task_id"),
            step_id=optional_uuid("step_id"),
            correlation_id=correlation_uuid,
            causation_id=optional_uuid("causation_id"),
            aggregate_type=mapping.aggregate_type,
            aggregate_id=aggregate_uuid,
            sequence=int(event.get("sequence", 1)),
            producer=cls.producer,
            payload=payload,
            metadata=metadata,
            integrity={"previous_digest": None, "digest": ""},
        )
