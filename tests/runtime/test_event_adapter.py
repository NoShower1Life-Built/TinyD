from __future__ import annotations

from uuid import UUID

import pytest

from packages.runtime.src.event_adapter import LegacyEventAdapter, LegacyEventAdapterError

TENANT = "tenant-alpha"
AGENT = "2d2d8f47-8dc5-4df5-8d3d-7c8f7ef4c7c4"
RUN = "8b3c1b8f-3a1f-4dcb-8a86-0db2d18f44c0"


def legacy_event(**overrides):
    event = {
        "id": "evt_001",
        "type": "run.requested",
        "tenant_id": TENANT,
        "agent_id": AGENT,
        "run_id": RUN,
        "correlation_id": "7b0b6d8e-9f1e-4b15-91e7-48e3c4fd9a20",
        "occurred_at": "2026-09-11T20:00:00Z",
        "payload": {"prompt": "build the plan"},
    }
    event.update(overrides)
    return event


def test_adaptation_is_deterministic():
    first = LegacyEventAdapter.adapt(legacy_event())
    second = LegacyEventAdapter.adapt(legacy_event())

    assert first == second
    assert first.event_id == LegacyEventAdapter.adapt(legacy_event()).event_id
    assert first.tenant_id == LegacyEventAdapter.adapt(legacy_event()).tenant_id
    assert first.aggregate_id == second.aggregate_id


def test_non_uuid_tenant_is_stably_mapped_and_provenance_preserved():
    envelope = LegacyEventAdapter.adapt(legacy_event())

    assert isinstance(envelope.tenant_id, UUID)
    assert envelope.metadata["legacy_tenant_id"] == TENANT
    assert envelope.metadata["adapter_version"] == 1


def test_valid_uuid_tenant_is_preserved():
    tenant = "a4f4bbf4-bf70-4d93-a2c8-4c1cc8bdbf54"
    envelope = LegacyEventAdapter.adapt(legacy_event(tenant_id=tenant))

    assert envelope.tenant_id == UUID(tenant)
    assert envelope.metadata["legacy_tenant_id"] == tenant


def test_event_id_is_deterministic_when_legacy_id_is_not_uuid():
    first = LegacyEventAdapter.adapt(legacy_event(id="evt_same"))
    second = LegacyEventAdapter.adapt(legacy_event(id="evt_same"))
    different = LegacyEventAdapter.adapt(legacy_event(id="evt_other"))

    assert first.event_id == second.event_id
    assert first.event_id != different.event_id
    assert first.metadata["legacy_event_id"] == "evt_same"


def test_unknown_event_type_is_rejected():
    with pytest.raises(LegacyEventAdapterError, match="unregistered event type"):
        LegacyEventAdapter.adapt(legacy_event(type="unknown.event"))


def test_missing_aggregate_identity_is_rejected():
    with pytest.raises(LegacyEventAdapterError, match="requires aggregate identity"):
        LegacyEventAdapter.adapt(legacy_event(run_id=None))


def test_missing_agent_id_is_rejected():
    with pytest.raises(LegacyEventAdapterError, match="requires agent_id"):
        LegacyEventAdapter.adapt(legacy_event(agent_id=None))


def test_authenticated_tenant_cannot_be_overridden():
    authenticated = "a4f4bbf4-bf70-4d93-a2c8-4c1cc8bdbf54"

    with pytest.raises(LegacyEventAdapterError, match="does not match authenticated tenant"):
        LegacyEventAdapter.adapt(
            legacy_event(tenant_id="another-tenant"),
            authenticated_tenant_id=authenticated,
        )


def test_authenticated_matching_uuid_tenant_is_accepted():
    tenant = "a4f4bbf4-bf70-4d93-a2c8-4c1cc8bdbf54"
    envelope = LegacyEventAdapter.adapt(
        legacy_event(tenant_id=tenant),
        authenticated_tenant_id=tenant,
    )

    assert envelope.tenant_id == UUID(tenant)


def test_timezone_is_required_for_explicit_timestamp():
    with pytest.raises(LegacyEventAdapterError, match="timezone"):
        LegacyEventAdapter.adapt(legacy_event(occurred_at="2026-09-11T20:00:00"))
