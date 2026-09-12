from __future__ import annotations

import pytest

from packages.runtime.src.event_mapping import MAPPING_VERSION, EventMappingError, get_mapping


@pytest.mark.parametrize(
    ("event_type", "aggregate_type", "identity"),
    [
        ("workflow.requested", "workflow", ("workflow",)),
        ("workflow.replayed", "workflow", ("workflow",)),
        ("marketplace.package.installed", "marketplace_package", ("package_id", "version")),
        ("marketplace.usage.recorded", "marketplace_usage", ("package_id",)),
        ("billing.webhook.received", "billing", ("tenant_id",)),
        ("billing.customer.linked", "billing", ("tenant_id",)),
    ],
)
def test_legacy_mapping_is_explicit_and_versioned(event_type, aggregate_type, identity):
    mapping = get_mapping(event_type)

    assert MAPPING_VERSION == 1
    assert mapping.aggregate_type == aggregate_type
    assert mapping.identity_fields == identity


def test_mapping_identity_reads_top_level_fields():
    mapping = get_mapping("marketplace.package.installed")

    assert mapping.identity({"package_id": "pkg-a", "version": "1.2.3"}) == "pkg-a\x1f1.2.3"


def test_mapping_identity_reads_payload_fields():
    mapping = get_mapping("workflow.requested")

    assert mapping.identity({"payload": {"workflow": "deploy"}}) == "deploy"


def test_mapping_identity_rejects_missing_required_field():
    mapping = get_mapping("marketplace.package.installed")

    with pytest.raises(EventMappingError, match="package_id"):
        mapping.identity({"version": "1.2.3"})


def test_unknown_event_type_is_not_mappable():
    with pytest.raises(EventMappingError, match="unregistered event type"):
        get_mapping("not.registered")
