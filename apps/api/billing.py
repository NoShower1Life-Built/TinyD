from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import urllib.parse
import urllib.request


def _secret() -> str:
    secret = os.environ.get("STRIPE_SECRET_KEY")
    if not secret:
        raise RuntimeError("STRIPE_SECRET_KEY is not configured")
    return secret


def _post(path: str, fields: dict[str, str]) -> dict:
    request = urllib.request.Request(
        f"https://api.stripe.com{path}",
        data=urllib.parse.urlencode(fields).encode(),
        headers={"Authorization": f"Bearer {_secret()}", "Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode())
    except Exception as exc:
        raise RuntimeError(f"Stripe request failed: {exc}") from exc


def create_checkout_session(*, tenant_id: str, package: dict, success_url: str, cancel_url: str) -> dict:
    configured_price = package.get("billing", {}).get("stripe_price_id")
    if configured_price and str(configured_price).startswith("${") and str(configured_price).endswith("}"):
        configured_price = os.environ.get(str(configured_price)[2:-1])
    if not configured_price:
        raise RuntimeError("Stripe price is not configured for this package")
    mode = "subscription" if package.get("billing", {}).get("interval") else "payment"
    fields = {"mode": mode, "line_items[0][price]": configured_price, "line_items[0][quantity]": "1", "success_url": success_url, "cancel_url": cancel_url, "client_reference_id": tenant_id, "customer_creation": "always" if mode == "payment" else "if_required", "metadata[tenant_id]": tenant_id, "metadata[package_id]": package["id"], "metadata[package_version]": package["version"]}
    if mode == "subscription":
        fields["subscription_data[metadata][tenant_id]"] = tenant_id
        fields["subscription_data[metadata][package_id]"] = package["id"]
    return _post("/v1/checkout/sessions", fields)


def report_meter_event(*, meter_event_name: str, customer_id: str, value: int, identifier: str) -> dict:
    return _post("/v1/billing/meter_events", {"event_name": meter_event_name, "payload[value]": str(value), "payload[stripe_customer_id]": customer_id, "identifier": identifier})


def verify_webhook_signature(payload: bytes, signature: str | None, tolerance: int = 300) -> dict:
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET")
    if not secret or not signature:
        raise RuntimeError("Stripe webhook verification is not configured")
    parts: dict[str, list[str]] = {}
    for item in signature.split(","):
        key, separator, value = item.partition("=")
        if separator and key and value:
            parts.setdefault(key, []).append(value)
    try:
        timestamp = int(parts.get("t", [""])[0])
    except (TypeError, ValueError) as exc:
        raise RuntimeError("invalid Stripe webhook signature") from exc
    if abs(int(time.time()) - timestamp) > tolerance:
        raise RuntimeError("Stripe webhook timestamp outside tolerance")
    try:
        signed = f"{timestamp}.".encode() + payload
        payload_text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError("invalid Stripe webhook payload") from exc
    expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, candidate) for candidate in parts.get("v1", [])):
        raise RuntimeError("invalid Stripe webhook signature")
    try:
        data = json.loads(payload_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("invalid Stripe webhook payload") from exc
    if not isinstance(data, dict):
        raise RuntimeError("invalid Stripe webhook payload")
    return data
