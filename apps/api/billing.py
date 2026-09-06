from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request


def create_checkout_session(*, tenant_id: str, package: dict, success_url: str, cancel_url: str) -> dict:
    secret = os.environ.get("STRIPE_SECRET_KEY")
    configured_price = package.get("billing", {}).get("stripe_price_id")
    if configured_price and str(configured_price).startswith("${") and str(configured_price).endswith("}"):
        configured_price = os.environ.get(str(configured_price)[2:-1])
    price_id = configured_price
    if not secret or not price_id:
        raise RuntimeError("Stripe billing is not configured for this package")

    fields = {
        "mode": "subscription" if package.get("billing", {}).get("interval") else "payment",
        "line_items[0][price]": price_id,
        "line_items[0][quantity]": "1",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "client_reference_id": tenant_id,
        "metadata[tenant_id]": tenant_id,
        "metadata[package_id]": package["id"],
        "metadata[package_version]": package["version"],
    }
    if fields["mode"] == "subscription":
        fields["subscription_data[metadata][tenant_id]"] = tenant_id
        fields["subscription_data[metadata][package_id]"] = package["id"]

    request = urllib.request.Request(
        "https://api.stripe.com/v1/checkout/sessions",
        data=urllib.parse.urlencode(fields).encode(),
        headers={"Authorization": f"Bearer {secret}", "Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode())
    except Exception as exc:
        raise RuntimeError(f"Stripe checkout request failed: {exc}") from exc
