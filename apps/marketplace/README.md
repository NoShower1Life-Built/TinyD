# TinyD Marketplace

The marketplace UI is now a client of the TinyD control-plane API rather than a local product dataset.

## Live integration

- `GET /v1/marketplace/packages` — repository-backed package catalog
- `GET /v1/marketplace/packages/{id}` — manifest plus deterministic SHA-256 digest
- `POST /v1/marketplace/packages/{id}/install` — authenticated tenant installation with verification gate
- `POST /v1/marketplace/usage` — tenant-scoped usage ledger and optional Stripe meter event
- `POST /v1/marketplace/billing/checkout` — Stripe Checkout session creation
- `POST /v1/marketplace/billing/webhook` — signed Stripe webhook ingestion and tenant/customer linking

## Registry

Canonical package manifests live under `packages/marketplace/registry/*.json`. The API loads those manifests at runtime; the browser does not contain package records.

## Authentication

Marketplace installation, usage, billing, and runtime execution require a bearer token. Tokens are supplied as SHA-256 hashes through `TINYD_TENANT_TOKENS`, for example:

`{"<sha256-token>":{"tenant_id":"tenant_demo","scopes":["marketplace:install","usage:write","billing:write","executions:write","events:read"]}}`

This is the current control-plane boundary. Production deployment should place it behind the canonical OIDC/SAML identity layer as that subsystem is hardened.

## Stripe

Set `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET` in the runtime secret store. Paid package manifests reference Stripe Price IDs through environment placeholders such as `${STRIPE_PRICE_INCIDENT_RESPONSE}`. Metered packages may declare `stripe_meter_event_name` and usage is reported to Stripe when the tenant has a linked Stripe customer from a verified webhook.

No Stripe secret, tenant token, or customer identifier is committed to the repository.
